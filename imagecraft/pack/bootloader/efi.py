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
partitions are formatted. ``diskutil.format_device`` later embeds these
files into their filesystems via ``mke2fs``/``mkfs.vfat``, so no mounts or
loop devices are needed to install the bootloader.
"""

import tempfile
from pathlib import Path, PurePosixPath
from uuid import UUID

from craft_cli import emit
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.pack.bootloader.config import render_early_cfg
from imagecraft.pack.bootloader.const import CORE_EFI_MODULES, ArchSpec, get_arch_spec
from imagecraft.pack.bootloader.fs import resilient_copy, safe_copytree
from imagecraft.pack.bootloader.mkimage import GrubMkimage
from imagecraft.pack.bootloader.models import EfiInstallResult, EfiTier


def write_esp_stub(
    target_cfg: Path, search_uuid: UUID | str, *, boot_prefix: str = "/boot/grub"
) -> Path:
    """Render and write an early search stub grub.cfg to target_cfg.

    :param target_cfg: Target path for the early configuration stub.
    :param search_uuid: UUID of the filesystem holding the GRUB configuration
        (the root filesystem, or the dedicated ``/boot`` partition when one
        exists).
    :param boot_prefix: Path of the GRUB directory relative to the searched
        filesystem's root.
    :return: The path written.
    """
    target_cfg.parent.mkdir(parents=True, exist_ok=True)
    target_cfg.write_text(render_early_cfg(search_uuid, boot_prefix=boot_prefix))
    return target_cfg


class EfiInstaller:
    """Installs GRUB/shim EFI bootloader files into an ESP prime directory.

    Implements a 3-tier resolution sequence, from most to least preferred:

    1. **Signed**: uses signed shim + signed GRUB already present in the
       staged rootfs (installed there via ``shim-signed``/``grub-efi-*-signed``
       apt packages during the parts lifecycle).
    2. **Unsigned prebuilt**: uses a prebuilt monolithic (unsigned) GRUB EFI
       binary from ``grub-efi-*`` packages.
    3. **Fallback build**: assembles a standalone EFI binary locally with the
       host's ``grub-mkimage``, embedding the early search stub.
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
        mkimage: GrubMkimage | None = None,
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
            ``/boot`` partition's filesystem, if any. The early search stub
            searches this UUID (with a ``/grub`` prefix) instead of the root
            filesystem's.
        :param mkimage: Optional GrubMkimage instance (mainly for tests).
        """
        self.root_dir = root_dir
        self.esp_dir = esp_dir
        self.root_uuid = str(root_uuid)
        self.arch = arch
        self.boot_dir = boot_dir if boot_dir is not None else root_dir / "boot"
        self.search_uuid = str(boot_uuid) if boot_uuid is not None else str(root_uuid)
        self.boot_prefix = "/grub" if boot_uuid is not None else "/boot/grub"
        self.spec: ArchSpec = get_arch_spec(arch)
        self._mkimage = mkimage

    @property
    def mkimage(self) -> GrubMkimage:
        """Get or lazily initialize the GrubMkimage instance."""
        if self._mkimage is None:
            self._mkimage = GrubMkimage(root_dir=self.root_dir)
        return self._mkimage

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

    def deploy_early_stubs(self) -> list[Path]:
        """Write the early search stub grub.cfg to /EFI/BOOT/ and /EFI/ubuntu/ on the ESP."""
        boot_cfg = self.esp_dir / "EFI" / "BOOT" / "grub.cfg"
        u_cfg = self.esp_dir / "EFI" / "ubuntu" / "grub.cfg"
        write_esp_stub(boot_cfg, self.search_uuid, boot_prefix=self.boot_prefix)
        write_esp_stub(u_cfg, self.search_uuid, boot_prefix=self.boot_prefix)
        return [boot_cfg, u_cfg]

    def install_signed(self) -> EfiInstallResult | None:
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

        installed: list[Path] = []
        primary_boot = boot_dir / f"BOOT{efi_suf}.EFI"
        installed.append(resilient_copy(shim, primary_boot))
        installed.append(resilient_copy(grub, boot_dir / f"grub{bin_suf}.efi"))
        installed.append(resilient_copy(shim, u_dir / f"shim{bin_suf}.efi"))
        installed.append(resilient_copy(grub, u_dir / f"grub{bin_suf}.efi"))

        if mm := self._find_file(f"usr/lib/shim/mm{bin_suf}.efi"):
            installed.append(resilient_copy(mm, boot_dir / f"mm{bin_suf}.efi"))
            installed.append(resilient_copy(mm, u_dir / f"mm{bin_suf}.efi"))

        if fb := self._find_file(f"usr/lib/shim/fb{bin_suf}.efi"):
            installed.append(resilient_copy(fb, boot_dir / f"fb{bin_suf}.efi"))
            installed.append(resilient_copy(fb, u_dir / f"fb{bin_suf}.efi"))

        if csv_file := self._find_file(f"usr/lib/shim/BOOT{efi_suf}.CSV"):
            installed.append(resilient_copy(csv_file, u_dir / f"BOOT{efi_suf}.CSV"))

        installed.extend(self.deploy_early_stubs())

        return EfiInstallResult(
            tier=EfiTier.SIGNED,
            installed_files=installed,
            modules_installed=False,
            boot_efi_binary=primary_boot,
        )

    def install_unsigned_prebuilt(self) -> EfiInstallResult | None:
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

        installed: list[Path] = []
        primary_boot = boot_dir / f"BOOT{efi_suf}.EFI"
        installed.append(resilient_copy(prebuilt, primary_boot))
        installed.append(resilient_copy(prebuilt, u_dir / f"grub{bin_suf}.efi"))

        modules_copied = False
        if modules_dir := self._find_dir(f"usr/lib/grub/{mod_dir_name}"):
            safe_copytree(modules_dir, self.boot_dir / "grub" / mod_dir_name)
            modules_copied = True

        installed.extend(self.deploy_early_stubs())

        return EfiInstallResult(
            tier=EfiTier.UNSIGNED_PREBUILT,
            installed_files=installed,
            modules_installed=modules_copied,
            boot_efi_binary=primary_boot,
        )

    def install_fallback_build(self) -> EfiInstallResult:
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

        boot_dir = self.esp_dir / "EFI" / "BOOT"
        u_dir = self.esp_dir / "EFI" / "ubuntu"
        boot_dir.mkdir(parents=True, exist_ok=True)
        u_dir.mkdir(parents=True, exist_ok=True)

        primary_boot = boot_dir / f"BOOT{efi_suf}.EFI"

        with tempfile.TemporaryDirectory(prefix="imagecraft-grub-efi-") as tmpdir:
            temp_cfg_path = Path(tmpdir) / "early.cfg"
            temp_cfg_path.write_text(
                render_early_cfg(self.search_uuid, boot_prefix=self.boot_prefix)
            )

            self.mkimage.run(
                grub_format=efi_fmt,
                output=primary_boot,
                prefix=PurePosixPath("/EFI/ubuntu"),
                config=temp_cfg_path,
                modules=CORE_EFI_MODULES,
                directory=modules_dir,
            )

        installed: list[Path] = [primary_boot]
        installed.append(resilient_copy(primary_boot, u_dir / f"grub{bin_suf}.efi"))

        safe_copytree(modules_dir, self.boot_dir / "grub" / mod_dir_name)

        installed.extend(self.deploy_early_stubs())

        return EfiInstallResult(
            tier=EfiTier.FALLBACK_BUILD,
            installed_files=installed,
            modules_installed=True,
            boot_efi_binary=primary_boot,
        )

    def install(self) -> EfiInstallResult:
        """Execute the 3-tier EFI bootloader resolution and installation sequence."""
        if result := self.install_signed():
            emit.debug("Installed signed EFI bootloader (secure boot capable)")
            return result

        if result := self.install_unsigned_prebuilt():
            emit.debug("Installed unsigned prebuilt EFI bootloader")
            return result

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
    mkimage: GrubMkimage | None = None,
) -> EfiInstallResult:
    """Install the EFI bootloader into esp_dir/root_dir prime directories.

    :param root_dir: Prime directory of the root filesystem partition.
    :param esp_dir: Prime directory of the EFI System Partition.
    :param root_uuid: UUID that will be assigned to the root filesystem.
    :param arch: Target architecture.
    :param boot_dir: Prime directory that corresponds to ``/boot``. Defaults
        to ``root_dir / "boot"`` when ``/boot`` isn't a dedicated partition.
    :param boot_uuid: UUID that will be assigned to the dedicated ``/boot``
        partition's filesystem, if any.
    :param mkimage: Optional GrubMkimage instance (mainly for tests).
    :return: EfiInstallResult detailing the installed tier and files.
    """
    installer = EfiInstaller(
        root_dir=root_dir,
        esp_dir=esp_dir,
        root_uuid=root_uuid,
        arch=arch,
        boot_dir=boot_dir,
        boot_uuid=boot_uuid,
        mkimage=mkimage,
    )
    return installer.install()
