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
from pathlib import Path
from uuid import UUID

from craft_cli import emit
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models.volume import (
    GPTVolume,
    HybridVolume,
    MBRVolume,
    PartitionSchema,
)
from imagecraft.pack import gptutil, mbrutil
from imagecraft.pack.bootloader.chrootenv import (
    require_chroot_binary,
    run_checked,
)
from imagecraft.pack.bootloader.const import (
    CORE_BIOS_MODULES,
    get_arch_spec,
    render_early_cfg,
)
from imagecraft.pack.chroot import Mount, build_prime_chroot
from imagecraft.utils.mount import ExtFuseMount

_CHROOT_BIOS_WORK_DIR = "/tmp/grub-bios"  # noqa: S108


def _install_boot_code_in_chroot(
    *,
    grub_format: str,
    mkimage_path: str,
    boot_prefix: str,
    early_cfg_content: str,
    device_map_content: str,
    image_path: str,
    modules: list[str],
) -> str:
    """Run grub-mkimage and grub-bios-setup inside the chrooted rootfs.

    Executing the rootfs's own binaries in a chroot ensures the target's ELF
    interpreter and libraries are used regardless of the build host.

    Must be a top-level function so it can be pickled into the chroot child
    process. Returns the tools' combined output.
    """
    work_dir = Path(_CHROOT_BIOS_WORK_DIR)
    work_dir.mkdir(parents=True, exist_ok=True)
    early_cfg = work_dir / "early.cfg"
    early_cfg.write_text(early_cfg_content)
    device_map = work_dir / "device.map"
    device_map.write_text(device_map_content)
    mod_dir = f"/usr/lib/grub/{grub_format}"
    core_img = Path(f"{mod_dir}/core.img")
    output: list[str] = []
    try:
        proc = run_checked(
            [
                mkimage_path,
                "-d",
                mod_dir,
                "-O",
                grub_format,
                "-o",
                str(core_img),
                "-p",
                boot_prefix,
                "-c",
                str(early_cfg),
                *modules,
            ]
        )
        output.append(proc.stdout + proc.stderr)
        proc = run_checked(
            [
                f"{mod_dir}/grub-bios-setup",
                "--skip-fs-probe",
                "-m",
                str(device_map),
                "-d",
                mod_dir,
                image_path,
            ]
        )
        output.append(proc.stdout + proc.stderr)
    finally:
        # These live inside the disk image's filesystem; don't leak them.
        core_img.unlink(missing_ok=True)
        shutil.rmtree(work_dir, ignore_errors=True)
    return "".join(output).strip()


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
        self.search_uuid = str(boot_uuid or root_uuid)
        self.boot_prefix = "/grub" if boot_uuid else "/boot/grub"

    def _root_partition_offset(self) -> int:
        """Return the byte offset of the root (system-data) partition in the image."""
        item = self.volume.root_partition
        # Guaranteed by the BIOS boot-method resolution.
        assert item is not None  # noqa: S101
        # GPT items may declare an explicit partition number; MBR items are
        # numbered by structure order. Mirrors
        # ImageService._get_partition_numbers: with more than four MBR
        # entries, slot 4 is the synthesized extended container and logical
        # partitions are numbered from 5.
        structure_index = next(
            i for i, entry in enumerate(self.volume.structure) if entry is item
        )
        if (
            self.volume.volume_schema == PartitionSchema.MBR
            and len(self.volume.structure) > mbrutil.MAX_PRIMARY_SLOTS
            and structure_index >= mbrutil.PRIMARY_SLOTS_WITH_EXTENDED
        ):
            part_num = structure_index + 2
        else:
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

        resolved_image = self.image_path.resolve()
        image_rel = str(resolved_image).lstrip("/")

        with ExtFuseMount(
            self.image_path, offset=self._root_partition_offset(), fakeroot=True
        ) as mnt:
            # grub-bios-setup resolves its -d directory through
            # /proc/self/mountinfo, where this fuse mount appears as "/" once
            # chrooted into. The image file itself must exist at its host
            # path inside the chroot so the device map reference resolves.
            chroot_image = mnt / image_rel
            missing_parents: list[Path] = []
            parent = chroot_image.parent
            while not parent.exists():
                missing_parents.append(parent)
                parent = parent.parent
            chroot_image.parent.mkdir(parents=True, exist_ok=True)
            chroot_image.touch()
            chroot = build_prime_chroot(
                mnt,
                extra_mounts=[
                    Mount(
                        fstype=None,
                        src=str(resolved_image),
                        relative_mountpoint=f"/{image_rel}",
                        options=["--bind"],
                    )
                ],
            )
            try:
                output = chroot.execute(
                    target=_install_boot_code_in_chroot,
                    grub_format=self.grub_format,
                    mkimage_path=f"/{mkimage_rel}",
                    boot_prefix=self.boot_prefix,
                    early_cfg_content=render_early_cfg(
                        self.search_uuid, boot_prefix=self.boot_prefix
                    ),
                    device_map_content=f"(hd0)\t{resolved_image}\n",
                    image_path=str(resolved_image),
                    modules=modules,
                )
            finally:
                chroot_image.unlink(missing_ok=True)
                if missing_parents:
                    shutil.rmtree(missing_parents[-1], ignore_errors=True)
        if output:
            emit.debug(output)
