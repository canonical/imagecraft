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

"""EFI bootloader installation with 3-tier fallback resolution.

All paths written here are prime directories (``root_dir`` for the rootfs
partition, ``esp_dir`` for the EFI System Partition), staged *before* the
partitions are formatted and embedded by ``diskutil.format_device``.
"""

import shutil
from pathlib import Path
from uuid import UUID

from craft_cli import emit
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.pack.bootloader.chrootenv import (
    build_prime_chroot,
    find_chroot_binary,
    run_checked,
)
from imagecraft.pack.bootloader.config import render_early_cfg
from imagecraft.pack.bootloader.const import CORE_EFI_MODULES, ArchSpec, get_arch_spec
from imagecraft.pack.bootloader.models import EfiTier

_CHROOT_EFI_WORK_DIR = "/tmp/grub-efi"  # noqa: S108


def _build_efi_image_in_chroot(
    *,
    mkimage: str,
    efi_format: str,
    prefix: str,
    early_cfg_content: str,
    modules: list[str],
    output: str,
) -> None:
    """Build a standalone GRUB EFI binary inside the chroot.

    Must be a top-level function so it can be pickled into the chroot child
    process.

    :raises errors.BootloaderError: If grub-mkimage fails.
    """
    work_dir = Path(_CHROOT_EFI_WORK_DIR)
    work_dir.mkdir(parents=True, exist_ok=True)
    early_cfg = work_dir / "early.cfg"
    early_cfg.write_text(early_cfg_content)
    run_checked(
        [
            mkimage,
            "-d",
            f"/usr/lib/grub/{efi_format}",
            "-O",
            efi_format,
            "-o",
            output,
            "-p",
            prefix,
            "-c",
            str(early_cfg),
            *modules,
        ]
    )


def write_esp_stub(
    target_cfg: Path, search_uuid: UUID | str, *, boot_prefix: str = "/boot/grub"
) -> None:
    """Write an early search stub grub.cfg to target_cfg.

    :param search_uuid: UUID of the filesystem holding the GRUB configuration
        (the root filesystem, or the dedicated ``/boot`` partition when one
        exists).
    :param boot_prefix: Path of the GRUB directory relative to the searched
        filesystem's root.
    """
    target_cfg.parent.mkdir(parents=True, exist_ok=True)
    target_cfg.write_text(render_early_cfg(search_uuid, boot_prefix=boot_prefix))


class EfiInstaller:
    """Installs GRUB/shim EFI bootloader files into an ESP prime directory.

    Implements a 3-tier resolution sequence, from most to least preferred:

    1. **Signed**: uses signed shim + signed GRUB already present in the
       staged rootfs (installed there via ``shim-signed``/``grub-efi-*-signed``
       apt packages during the parts lifecycle).
    2. **Unsigned prebuilt**: uses a prebuilt monolithic (unsigned) GRUB EFI
       binary from ``grub-efi-*`` packages.
    3. **Fallback build**: assembles a standalone EFI binary with the guest
       rootfs's own ``grub-mkimage`` (run in a chroot), embedding the early
       search stub.
    """

    def __init__(
        self,
        *,
        root_dir: Path,
        esp_dir: Path,
        root_uuid: UUID | str,
        arch: DebianArchitecture,
        boot_dir: Path | None = None,
        boot_uuid: UUID | str | None = None,
    ) -> None:
        """Initialize the EFI installer.

        :param root_dir: Prime directory of the root filesystem partition.
        :param esp_dir: Prime directory of the EFI System Partition.
        :param root_uuid: UUID that will be assigned to the root filesystem.
        :param arch: Target architecture.
        :param boot_dir: Prime directory that corresponds to ``/boot``.
            Defaults to ``root_dir / "boot"`` when ``/boot`` isn't a
            dedicated partition.
        :param boot_uuid: UUID that will be assigned to the dedicated
            ``/boot`` partition's filesystem, if any.
        """
        self.root_dir = root_dir
        self.esp_dir = esp_dir
        self.root_uuid = str(root_uuid)
        self.arch = arch
        self.boot_dir = boot_dir if boot_dir is not None else root_dir / "boot"
        self.search_uuid = str(boot_uuid) if boot_uuid is not None else str(root_uuid)
        self.boot_prefix = "/grub" if boot_uuid is not None else "/boot/grub"
        self.spec: ArchSpec = get_arch_spec(arch)

    def _find_file(self, *rel_paths: str) -> Path | None:
        """Return the first existing file among candidate paths relative to root_dir."""
        for rel in rel_paths:
            candidate = self.root_dir / rel
            if candidate.is_file():
                return candidate
        return None

    def _find_dir(self, *rel_paths: str) -> Path | None:
        """Return the first existing directory among candidate paths relative to root_dir."""
        for rel in rel_paths:
            candidate = self.root_dir / rel
            if candidate.is_dir():
                return candidate
        return None

    def deploy_early_stubs(self) -> None:
        """Write the early search stub grub.cfg to /EFI/BOOT/ and /EFI/ubuntu/ on the ESP."""
        boot_cfg = self.esp_dir / "EFI" / "BOOT" / "grub.cfg"
        u_cfg = self.esp_dir / "EFI" / "ubuntu" / "grub.cfg"
        write_esp_stub(boot_cfg, self.search_uuid, boot_prefix=self.boot_prefix)
        write_esp_stub(u_cfg, self.search_uuid, boot_prefix=self.boot_prefix)

    def install_signed(self) -> EfiTier | None:
        """Attempt Tier 1: install signed shim and signed GRUB binaries."""
        bin_suf = self.spec.bin_suffix
        efi_suf = self.spec.efi_suffix
        signed_dir = self.spec.signed_dir

        shim = self._find_file(
            f"usr/lib/shim/shim{bin_suf}.efi.signed.latest",
            f"usr/lib/shim/shim{bin_suf}.efi.signed",
            f"usr/lib/shim/shim{bin_suf}.efi",
        )
        grub = self._find_file(
            f"usr/lib/grub/{signed_dir}/grub{bin_suf}.efi.signed",
            f"usr/lib/grub/{signed_dir}/grub{bin_suf}.efi",
        )
        if not shim or not grub:
            return None

        boot_dir = self.esp_dir / "EFI" / "BOOT"
        u_dir = self.esp_dir / "EFI" / "ubuntu"
        boot_dir.mkdir(parents=True, exist_ok=True)
        u_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(shim, boot_dir / f"BOOT{efi_suf}.EFI")
        shutil.copy2(grub, boot_dir / f"grub{bin_suf}.efi")
        shutil.copy2(shim, u_dir / f"shim{bin_suf}.efi")
        shutil.copy2(grub, u_dir / f"grub{bin_suf}.efi")

        if mm := self._find_file(f"usr/lib/shim/mm{bin_suf}.efi"):
            shutil.copy2(mm, boot_dir / f"mm{bin_suf}.efi")
            shutil.copy2(mm, u_dir / f"mm{bin_suf}.efi")

        if fb := self._find_file(f"usr/lib/shim/fb{bin_suf}.efi"):
            shutil.copy2(fb, boot_dir / f"fb{bin_suf}.efi")
            shutil.copy2(fb, u_dir / f"fb{bin_suf}.efi")

        if csv_file := self._find_file(f"usr/lib/shim/BOOT{efi_suf}.CSV"):
            shutil.copy2(csv_file, u_dir / f"BOOT{efi_suf}.CSV")

        self.deploy_early_stubs()

        return EfiTier.SIGNED

    def install_unsigned_prebuilt(self) -> EfiTier | None:
        """Attempt Tier 2: install an unsigned prebuilt monolithic GRUB binary."""
        bin_suf = self.spec.bin_suffix
        efi_suf = self.spec.efi_suffix
        mod_dir_name = self.spec.efi_format

        prebuilt = self._find_file(
            f"usr/lib/grub/{mod_dir_name}/monolithic/grub{bin_suf}.efi",
            f"usr/lib/grub/{mod_dir_name}/grub{bin_suf}.efi",
        )
        if not prebuilt:
            return None

        boot_dir = self.esp_dir / "EFI" / "BOOT"
        u_dir = self.esp_dir / "EFI" / "ubuntu"
        boot_dir.mkdir(parents=True, exist_ok=True)
        u_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(prebuilt, boot_dir / f"BOOT{efi_suf}.EFI")
        shutil.copy2(prebuilt, u_dir / f"grub{bin_suf}.efi")

        if modules_dir := self._find_dir(f"usr/lib/grub/{mod_dir_name}"):
            shutil.copytree(
                modules_dir, self.boot_dir / "grub" / mod_dir_name, dirs_exist_ok=True
            )

        self.deploy_early_stubs()

        return EfiTier.UNSIGNED_PREBUILT

    def install_fallback_build(self) -> EfiTier:
        """Attempt Tier 3: build a standalone EFI binary using grub-mkimage.

        :raises errors.BootloaderToolsMissingError: If the GRUB modules
            directory for this architecture isn't present in the staged
            rootfs.
        """
        bin_suf = self.spec.bin_suffix
        efi_suf = self.spec.efi_suffix
        efi_fmt = self.spec.efi_format
        mod_dir_name = self.spec.efi_format

        modules_dir = self._find_dir(f"usr/lib/grub/{mod_dir_name}")
        if not modules_dir:
            raise errors.BootloaderToolsMissingError(
                f"GRUB modules directory not found in rootfs: usr/lib/grub/{mod_dir_name}"
            )
        mkimage = find_chroot_binary(self.root_dir, "grub-mkimage")

        boot_dir = self.esp_dir / "EFI" / "BOOT"
        u_dir = self.esp_dir / "EFI" / "ubuntu"
        boot_dir.mkdir(parents=True, exist_ok=True)
        u_dir.mkdir(parents=True, exist_ok=True)

        primary_boot = boot_dir / f"BOOT{efi_suf}.EFI"

        chroot_output = f"{_CHROOT_EFI_WORK_DIR}/core.efi"
        chroot = build_prime_chroot(self.root_dir)
        try:
            chroot.execute(
                target=_build_efi_image_in_chroot,
                mkimage=mkimage,
                efi_format=efi_fmt,
                prefix="/EFI/ubuntu",
                early_cfg_content=render_early_cfg(
                    self.search_uuid, boot_prefix=self.boot_prefix
                ),
                modules=[
                    m for m in CORE_EFI_MODULES if (modules_dir / f"{m}.mod").is_file()
                ],
                output=chroot_output,
            )
            shutil.copy2(self.root_dir / chroot_output.lstrip("/"), primary_boot)
        finally:
            # This runs pre-format, so the chroot's working directory must
            # not leak into the image.
            shutil.rmtree(
                self.root_dir / _CHROOT_EFI_WORK_DIR.lstrip("/"), ignore_errors=True
            )

        shutil.copy2(primary_boot, u_dir / f"grub{bin_suf}.efi")

        shutil.copytree(
            modules_dir, self.boot_dir / "grub" / mod_dir_name, dirs_exist_ok=True
        )

        self.deploy_early_stubs()

        return EfiTier.FALLBACK_BUILD

    def install(self) -> EfiTier:
        """Execute the 3-tier EFI bootloader resolution and installation sequence."""
        if tier := self.install_signed():
            emit.debug("Installed signed EFI bootloader (secure boot capable)")
            return tier

        if tier := self.install_unsigned_prebuilt():
            emit.debug("Installed unsigned prebuilt EFI bootloader")
            return tier

        emit.debug("Building standalone EFI bootloader with grub-mkimage")
        return self.install_fallback_build()


def install_efi(
    *,
    root_dir: Path,
    esp_dir: Path,
    root_uuid: UUID | str,
    arch: DebianArchitecture,
    boot_dir: Path | None = None,
    boot_uuid: UUID | str | None = None,
) -> EfiTier:
    """Install the EFI bootloader into esp_dir/root_dir prime directories.

    :return: The resolution tier that was installed. See
        :class:`EfiInstaller` for parameter details.
    """
    installer = EfiInstaller(
        root_dir=root_dir,
        esp_dir=esp_dir,
        root_uuid=root_uuid,
        arch=arch,
        boot_dir=boot_dir,
        boot_uuid=boot_uuid,
    )
    return installer.install()
