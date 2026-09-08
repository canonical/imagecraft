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

"""Result types for the bootloader installation package."""

import enum
from dataclasses import dataclass, field
from pathlib import Path


class BootMethod(str, enum.Enum):
    """The resolved boot method for a target image."""

    EFI = "efi"
    """Boot via a UEFI System Partition, using the 3-tier EFI installer."""

    BIOS = "bios"
    """Boot via legacy BIOS, patching Sector 0/core.img directly."""

    NONE = "none"
    """No bootloader could be installed (unsupported arch/schema, or no boot partition)."""


class EfiTier(str, enum.Enum):
    """Resolution tier used to install the EFI bootloader."""

    SIGNED = "signed"
    """Signed shim + signed GRUB (secure boot capable)."""

    UNSIGNED_PREBUILT = "unsigned_prebuilt"
    """Prebuilt monolithic (unsigned) GRUB EFI binary."""

    FALLBACK_BUILD = "fallback_build"
    """Standalone EFI binary assembled locally with grub-mkimage."""


@dataclass
class EfiInstallResult:
    """Result summary of an EFI installation operation."""

    tier: EfiTier
    boot_efi_binary: Path
    installed_files: list[Path] = field(default_factory=list)
    modules_installed: bool = False


@dataclass
class NonEfiInstallResult:
    """Result summary of a non-EFI (BIOS) bootloader installation operation."""

    format: str
    core_img_size_bytes: int
    installed_files: list[Path] = field(default_factory=list)
    modules_installed: bool = False


@dataclass
class RootfsConfigResult:
    """Result summary of root filesystem configuration (fstab + grub.cfg)."""

    grub_cfg_path: Path
    grub_cfg_rendered: bool
    fstab_path: Path
    fstab_updated: bool
    vmlinuz: str
    initrd: str


@dataclass
class BootloaderResult:
    """Overall result of a bootloader preparation or installation phase."""

    boot_method: BootMethod
    rootfs_result: RootfsConfigResult | None = None
    efi_result: EfiInstallResult | None = None
    non_efi_result: NonEfiInstallResult | None = None
