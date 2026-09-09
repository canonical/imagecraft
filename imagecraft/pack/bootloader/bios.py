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

"""Non-EFI (legacy BIOS) bootloader installation via an in-chroot GRUB setup.

Runs GRUB's own tooling (``grub-mkimage`` and ``grub-bios-setup``) inside a
chroot rooted at the root partition's prime directory, with the raw disk
image bind-mounted into the chroot at ``/dev/image``. ``grub-bios-setup``
then writes ``boot.img`` to Sector 0 and embeds ``core.img`` into the
post-MBR gap (MBR) or BIOS Boot partition (GPT) itself, so no custom
byte-level patching or loop devices are needed.
"""

from pathlib import Path
from uuid import UUID

from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.pack.bootloader.chrootenv import (
    CHROOT_IMAGE_DEVICE,
    build_prime_chroot,
    find_chroot_binary,
    run_checked,
)
from imagecraft.pack.bootloader.config import render_early_cfg
from imagecraft.pack.bootloader.const import CORE_BIOS_MODULES, get_arch_spec
from imagecraft.pack.bootloader.fs import safe_copytree
from imagecraft.pack.bootloader.models import NonEfiInstallResult

_CHROOT_WORK_DIR = "/tmp/grub-bios"  # noqa: S108


def _bios_mod_dir(root_dir: Path, grub_format: str) -> Path:
    """Return the path to the rootfs's installed GRUB module directory."""
    return root_dir / "usr" / "lib" / "grub" / grub_format


def stage_non_efi_modules(
    root_dir: Path, boot_dir: Path | None = None, *, grub_format: str
) -> Path:
    """Stage BIOS GRUB runtime modules into the ``/boot`` prime directory.

    Must be called *before* the partitions are formatted (unlike the rest of
    this module, which writes to the raw image file after formatting), since
    it writes into a prime directory that ``diskutil.format_device`` will
    later embed via ``mke2fs -d``.

    :param root_dir: Prime directory of the root filesystem partition (used
        to locate the rootfs's installed GRUB modules).
    :param boot_dir: Prime directory that corresponds to ``/boot``. Defaults
        to ``root_dir / "boot"`` when ``/boot`` isn't a dedicated partition.
    :param grub_format: GRUB non-EFI target format (e.g. ``i386-pc``), from
        the architecture's :class:`~imagecraft.pack.bootloader.const.ArchSpec`.
    :return: The directory the modules were copied into.
    :raises errors.BootloaderToolsMissingError: If the GRUB BIOS modules
        directory isn't present in the staged rootfs.
    """
    mod_dir = _bios_mod_dir(root_dir, grub_format)
    if not mod_dir.is_dir():
        raise errors.BootloaderToolsMissingError(
            f"GRUB BIOS modules directory not found: {mod_dir}"
        )

    effective_boot_dir = boot_dir if boot_dir is not None else root_dir / "boot"
    target_mod_dir = effective_boot_dir / "grub" / grub_format
    safe_copytree(mod_dir, target_mod_dir)
    return target_mod_dir


def _install_boot_code_in_chroot(
    *,
    early_cfg_content: str,
    modules: list[str],
    mkimage: str,
    bios_setup: str,
    grub_format: str,
) -> None:
    """Build core.img and write the BIOS boot code to /dev/image.

    Runs entirely inside the chroot. Must be a top-level function so it can
    be pickled into the chroot child process.

    :param early_cfg_content: Rendered early GRUB config content.
    :param modules: GRUB modules to embed in core.img.
    :param mkimage: In-chroot path to grub-mkimage.
    :param bios_setup: In-chroot path to grub-bios-setup.
    :param grub_format: GRUB non-EFI target format (e.g. ``i386-pc``).
    :raises errors.BootloaderError: If any GRUB command fails.
    """
    mod_dir = f"/usr/lib/grub/{grub_format}"
    work_dir = Path(_CHROOT_WORK_DIR)
    work_dir.mkdir(parents=True, exist_ok=True)
    early_cfg = work_dir / "early.cfg"
    early_cfg.write_text(early_cfg_content)
    device_map = work_dir / "device.map"
    device_map.write_text(f"(hd0)\t{CHROOT_IMAGE_DEVICE}\n")

    core_img = f"{mod_dir}/core.img"
    commands = [
        [
            mkimage,
            "-d",
            mod_dir,
            "-O",
            grub_format,
            "-o",
            core_img,
            "-p",
            "/boot/grub",
            "-c",
            str(early_cfg),
            *modules,
        ],
        [
            bios_setup,
            "--skip-fs-probe",
            "-m",
            str(device_map),
            "-d",
            mod_dir,
            CHROOT_IMAGE_DEVICE,
        ],
    ]
    for cmd in commands:
        run_checked(cmd)


class NonEfiInstaller:
    """Installs the BIOS (non-EFI) bootloader using in-chroot GRUB tools.

    Only architectures with a non-EFI target in ``ARCH_SPECS`` (currently
    amd64/i386's ``i386-pc``) are supported; arm64/armhf/riscv64 always boot
    via EFI.
    """

    def __init__(
        self,
        *,
        image_path: Path,
        root_dir: Path,
        root_uuid: UUID | str,
        arch: DebianArchitecture,
    ) -> None:
        """Initialize the non-EFI bootloader installer.

        :param image_path: Path to the raw, partitioned disk image file.
        :param root_dir: Prime directory of the root filesystem partition.
            Used as the chroot root; GRUB modules and tools come from here.
        :param root_uuid: UUID assigned to the root filesystem.
        :param arch: Target architecture.
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
        self.root_uuid = str(root_uuid)
        self.grub_format = spec.non_efi_format

    def install(self) -> NonEfiInstallResult:
        """Build core.img and install the BIOS boot code into the disk image.

        Assumes :func:`stage_non_efi_modules` has already been called during
        the pre-format staging phase to place GRUB runtime modules into the
        boot partition's prime directory.

        :raises errors.BootloaderToolsMissingError: If GRUB modules, boot.img,
            or the GRUB tools themselves aren't present in the staged rootfs.
        """
        mod_dir = _bios_mod_dir(self.root_dir, self.grub_format)
        if not mod_dir.is_dir():
            raise errors.BootloaderToolsMissingError(
                f"GRUB BIOS modules directory not found: {mod_dir}"
            )
        boot_img_file = mod_dir / "boot.img"
        if not boot_img_file.is_file():
            raise errors.BootloaderToolsMissingError(
                f"GRUB stage 1 boot.img not found: {boot_img_file}"
            )
        mkimage = find_chroot_binary(self.root_dir, "grub-mkimage")
        bios_setup = find_chroot_binary(self.root_dir, "grub-bios-setup")

        modules = [m for m in CORE_BIOS_MODULES if (mod_dir / f"{m}.mod").is_file()]

        chroot = build_prime_chroot(self.root_dir, image_path=self.image_path)
        chroot.execute(
            target=_install_boot_code_in_chroot,
            early_cfg_content=render_early_cfg(self.root_uuid),
            modules=modules,
            mkimage=mkimage,
            bios_setup=bios_setup,
            grub_format=self.grub_format,
        )

        core_img = mod_dir / "core.img"
        return NonEfiInstallResult(
            format=self.grub_format,
            core_img_size_bytes=core_img.stat().st_size if core_img.is_file() else 0,
            installed_files=[core_img] if core_img.is_file() else [],
            modules_installed=True,
        )


def install_non_efi(
    *,
    image_path: Path,
    root_dir: Path,
    root_uuid: UUID | str,
    arch: DebianArchitecture,
) -> NonEfiInstallResult:
    """Install the BIOS bootloader into a raw disk image.

    :param image_path: Path to the raw, partitioned disk image file.
    :param root_dir: Prime directory of the root filesystem partition.
    :param root_uuid: UUID assigned to the root filesystem.
    :param arch: Target architecture.
    :return: NonEfiInstallResult.
    """
    installer = NonEfiInstaller(
        image_path=image_path,
        root_dir=root_dir,
        root_uuid=root_uuid,
        arch=arch,
    )
    return installer.install()
