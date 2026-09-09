# Copyright 2026 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Non-EFI (legacy BIOS) bootloader installation.

GRUB's own ``grub-mkimage`` and ``grub-bios-setup`` do the work, operating on
the formatted disk image with its root partition mounted read-write via
``fuse2fs``. The FUSE mount is required because ``grub-bios-setup`` resolves
its ``-d`` directory to a device through ``/proc/self/mountinfo``; a plain
directory has no resolvable backing device in unprivileged containers, but a
fuse2fs mount resolves to the image file, which the generated device map
translates to ``(hd0)``.
"""

import shutil
import tempfile
from pathlib import Path
from uuid import UUID

from craft_cli import emit
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models.volume import GPTVolume, HybridVolume, MBRVolume
from imagecraft.pack import gptutil
from imagecraft.pack.bootloader.chrootenv import (
    require_chroot_binary,
    run_checked,
)
from imagecraft.pack.bootloader.const import (
    CORE_BIOS_MODULES,
    get_arch_spec,
    render_early_cfg,
)
from imagecraft.utils.mount import ExtFuseMount


def _run_logged(cmd: list[str]) -> None:
    """Run a GRUB tool, forwarding its output to the craft log."""
    proc = run_checked(cmd)
    if output := (proc.stdout + proc.stderr).strip():
        emit.debug(output)


class PCBiosInstaller:
    """Installs the PC BIOS (``i386-pc``) bootloader using GRUB's own tools.

    Only architectures with a non-EFI target in ``ARCH_SPECS`` (currently
    amd64/i386's ``i386-pc``) are supported.
    """

    def __init__(
        self,
        *,
        image_path: Path,
        root_dir: Path,
        root_uuid: UUID | str,
        arch: DebianArchitecture,
        volume: GPTVolume | MBRVolume | HybridVolume,
        boot_uuid: UUID | str | None = None,
    ) -> None:
        """Initialize the non-EFI bootloader installer.

        :param image_path: Path to the raw, partitioned disk image file.
        :param root_dir: Prime directory of the root filesystem partition
            (used to check that the guest rootfs has the needed GRUB modules
            and tools).
        :param root_uuid: UUID assigned to the root filesystem.
        :param arch: Target architecture.
        :param volume: The volume layout used to partition the image.
        :param boot_uuid: UUID assigned to the dedicated ``/boot``
            partition's filesystem, if any.
        :raises errors.BootloaderError: If the architecture has no non-EFI
            GRUB target.
        """
        spec = get_arch_spec(arch)
        if spec.non_efi_format is None:
            raise errors.BootloaderError(
                f"Architecture {arch.value} has no non-EFI GRUB target"
            )
        self.image_path = image_path
        self.root_dir = root_dir
        self.volume = volume
        self.grub_format = spec.non_efi_format
        self.search_uuid = str(boot_uuid) if boot_uuid is not None else str(root_uuid)
        self.boot_prefix = "/grub" if boot_uuid is not None else "/boot/grub"

    def _root_partition_offset(self) -> int:
        """Return the byte offset of the root (system-data) partition in the image."""
        item = self.volume.root_partition
        # Guaranteed by the BIOS boot-method resolution.
        assert item is not None  # noqa: S101
        # GPT items may declare an explicit partition number; MBR items are
        # always numbered by structure order.
        structure_index = next(
            i for i, entry in enumerate(self.volume.structure) if entry is item
        )
        part_num = getattr(item, "number", None) or (structure_index + 1)
        return (
            gptutil.get_partition_sector_offset_by_number(self.image_path, part_num)
            * gptutil.SECTOR_SIZE_512
        )

    def install(self) -> None:
        """Build core.img and install the BIOS boot code into the disk image.

        Assumes :func:`~imagecraft.pack.bootloader.chrootenv.stage_grub_modules` has already been called during
        the pre-format staging phase.

        :raises errors.BootloaderToolsMissingError: If GRUB modules or tools
            aren't present in the staged rootfs, or fuse2fs isn't available
            on the host.
        """
        mod_dir_rel = f"usr/lib/grub/{self.grub_format}"
        mod_dir = self.root_dir / mod_dir_rel
        if not mod_dir.is_dir():
            raise errors.BootloaderToolsMissingError(
                f"GRUB BIOS modules directory not found: {mod_dir}"
            )
        if not (mod_dir / "boot.img").is_file():
            raise errors.BootloaderToolsMissingError(
                f"GRUB stage 1 boot.img not found: {mod_dir / 'boot.img'}"
            )
        if not (mod_dir / "grub-bios-setup").is_file():
            raise errors.BootloaderToolsMissingError(
                f"grub-bios-setup not found in the staged rootfs: {mod_dir_rel}",
                resolution="Install the grub-pc-bin package in the image.",
            )
        mkimage_rel = require_chroot_binary(self.root_dir, "grub-mkimage")
        if shutil.which("fuse2fs") is None:
            raise errors.BootloaderToolsMissingError(
                "fuse2fs not found on the build host",
                resolution="Install the fuse2fs package on the build host.",
            )

        modules = [m for m in CORE_BIOS_MODULES if (mod_dir / f"{m}.mod").is_file()]

        with tempfile.TemporaryDirectory(prefix="imagecraft-grub-bios-") as workdir:
            work = Path(workdir)
            early_cfg = work / "early.cfg"
            early_cfg.write_text(
                render_early_cfg(self.search_uuid, boot_prefix=self.boot_prefix)
            )
            device_map = work / "device.map"
            device_map.write_text(f"(hd0)\t{self.image_path.resolve()}\n")

            with ExtFuseMount(
                self.image_path, offset=self._root_partition_offset(), fakeroot=True
            ) as mnt:
                mnt_mod_dir = mnt / mod_dir_rel
                core_img = mnt_mod_dir / "core.img"
                _run_logged(
                    [
                        str(mnt / mkimage_rel),
                        "-d",
                        str(mnt_mod_dir),
                        "-O",
                        self.grub_format,
                        "-o",
                        str(core_img),
                        "-p",
                        self.boot_prefix,
                        "-c",
                        str(early_cfg),
                        *modules,
                    ]
                )
                try:
                    _run_logged(
                        [
                            str(mnt_mod_dir / "grub-bios-setup"),
                            "--skip-fs-probe",
                            "-m",
                            str(device_map),
                            "-d",
                            str(mnt_mod_dir),
                            str(self.image_path.resolve()),
                        ]
                    )
                finally:
                    core_img.unlink(missing_ok=True)
