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

"""Shared constants, enums, and the early-config renderer for the bootloader package."""

import enum
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from craft_platforms import DebianArchitecture


class BootMethod(str, enum.Enum):
    """The resolved boot method for a target image."""

    EFI = "efi"
    """Boot via a UEFI System Partition, using the 3-tier EFI installer."""

    BIOS = "bios"
    """Boot via legacy BIOS, using grub-bios-setup."""

    NONE = "none"
    """No bootloader to install (unsupported arch/schema or no boot partition)."""


class EfiTier(str, enum.Enum):
    """Resolution tier used to install the EFI bootloader."""

    SIGNED = "signed"
    """Signed shim + signed GRUB (secure boot capable)."""

    UNSIGNED_PREBUILT = "unsigned_prebuilt"
    """Prebuilt monolithic (unsigned) GRUB EFI binary."""

    FALLBACK_BUILD = "fallback_build"
    """Standalone EFI binary assembled with grub-mkimage."""


def render_early_cfg(
    search_uuid: UUID | str, *, boot_prefix: str = "/boot/grub"
) -> str:
    """Render the early GRUB search stub configuration.

    :param search_uuid: UUID of the filesystem holding the GRUB configuration
        (the root filesystem, or the dedicated ``/boot`` partition when one
        exists).
    :param boot_prefix: Path of the GRUB directory relative to the searched
        filesystem's root (``/boot/grub``, or ``/grub`` when ``/boot`` is a
        dedicated partition).
    """
    return (
        f"search.fs_uuid {search_uuid} root\n"
        f"set prefix=($root)'{boot_prefix}'\n"
        "configfile $prefix/grub.cfg\n"
    )


@dataclass(frozen=True)
class ArchSpec:
    """GRUB naming and target conventions for a single architecture."""

    efi_suffix: str
    """Suffix used in the EFI removable-media binary (e.g. ``X64`` -> ``BOOTX64.EFI``)."""

    bin_suffix: str
    """Suffix used in GRUB/shim package binary names (e.g. ``x64`` -> ``grubx64.efi``)."""

    efi_format: str
    """GRUB target name for EFI (e.g. ``x86_64-efi``); also its module directory name."""

    non_efi_format: str | None = None
    """GRUB target name for non-EFI (e.g. ``i386-pc``), or None if unsupported."""

    @property
    def signed_dir(self) -> str:
        """Directory name under ``usr/lib/grub`` holding signed EFI binaries."""
        return f"{self.efi_format}-signed"


# GRUB naming conventions per Debian architecture. Only amd64/i386 have a
# non-EFI (BIOS) target.
ARCH_SPECS: Final[dict[DebianArchitecture, ArchSpec]] = {
    DebianArchitecture.AMD64: ArchSpec(
        efi_suffix="X64",
        bin_suffix="x64",
        efi_format="x86_64-efi",
        non_efi_format="i386-pc",
    ),
    DebianArchitecture.ARM64: ArchSpec(
        efi_suffix="AA64",
        bin_suffix="aa64",
        efi_format="arm64-efi",
    ),
    DebianArchitecture.ARMHF: ArchSpec(
        efi_suffix="ARM",
        bin_suffix="arm",
        efi_format="arm-efi",
    ),
    DebianArchitecture.RISCV64: ArchSpec(
        efi_suffix="RISCV64",
        bin_suffix="riscv64",
        efi_format="riscv64-efi",
    ),
    DebianArchitecture.I386: ArchSpec(
        efi_suffix="IA32",
        bin_suffix="ia32",
        efi_format="i386-efi",
        non_efi_format="i386-pc",
    ),
}


def get_arch_spec(arch: DebianArchitecture | str) -> ArchSpec:
    """Retrieve the GRUB architecture spec for the given architecture.

    :raises ValueError: If the architecture is not supported.
    """
    try:
        key = arch if isinstance(arch, DebianArchitecture) else DebianArchitecture(arch)
    except ValueError:
        key = None
    if key is not None and (spec := ARCH_SPECS.get(key)):
        return spec
    supported = ", ".join(sorted(a.value for a in ARCH_SPECS))
    raise ValueError(
        f"Unsupported architecture {arch!r} for GRUB installation. "
        f"Supported architectures: {supported}"
    )


# GRUB core modules embedded via grub-mkimage.
_COMMON_GRUB_MODULES: Final[list[str]] = [
    "part_gpt",
    "part_msdos",
    "ext2",
    "normal",
    "search",
    "search_fs_uuid",
    "configfile",
    "echo",
    "test",
    "linux",
    "gzio",
    "serial",
    "terminal",
    "font",
    "gfxterm",
    "gettext",
    "reboot",
]

CORE_EFI_MODULES: Final[list[str]] = [
    *_COMMON_GRUB_MODULES,
    "fat",
    "efi_gop",
    "all_video",
]

CORE_BIOS_MODULES: Final[list[str]] = [
    "biosdisk",
    *_COMMON_GRUB_MODULES,
]
