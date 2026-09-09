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

"""Architecture specs, GRUB module lists, and on-disk offsets for the bootloader package."""

from dataclasses import dataclass
from typing import Final

from craft_platforms import DebianArchitecture


@dataclass(frozen=True)
class ArchSpec:
    """GRUB naming and target conventions for a single architecture."""

    efi_suffix: str
    """Suffix used in the EFI removable-media fallback binary (e.g. ``X64`` -> ``BOOTX64.EFI``)."""

    bin_suffix: str
    """Suffix used in GRUB/shim package binary names (e.g. ``x64`` -> ``grubx64.efi``)."""

    efi_format: str
    """``grub-mkimage``/module directory name for the EFI target (e.g. ``x86_64-efi``)."""

    signed_dir: str
    """Directory name under ``usr/lib/grub`` holding signed EFI binaries."""

    non_efi_format: str | None
    """``grub-mkimage``/module directory name for the non-EFI target, or None if unsupported."""


# GRUB naming conventions per Debian architecture. Only amd64 has a non-EFI
# (BIOS) target wired up in this package; see bios.py for details.
ARCH_SPECS: Final[dict[DebianArchitecture, ArchSpec]] = {
    DebianArchitecture.AMD64: ArchSpec(
        efi_suffix="X64",
        bin_suffix="x64",
        efi_format="x86_64-efi",
        signed_dir="x86_64-efi-signed",
        non_efi_format="i386-pc",
    ),
    DebianArchitecture.ARM64: ArchSpec(
        efi_suffix="AA64",
        bin_suffix="aa64",
        efi_format="arm64-efi",
        signed_dir="arm64-efi-signed",
        non_efi_format=None,
    ),
    DebianArchitecture.ARMHF: ArchSpec(
        efi_suffix="ARM",
        bin_suffix="arm",
        efi_format="arm-efi",
        signed_dir="arm-efi-signed",
        non_efi_format=None,
    ),
    DebianArchitecture.RISCV64: ArchSpec(
        efi_suffix="RISCV64",
        bin_suffix="riscv64",
        efi_format="riscv64-efi",
        signed_dir="riscv64-efi-signed",
        non_efi_format=None,
    ),
    DebianArchitecture.I386: ArchSpec(
        efi_suffix="IA32",
        bin_suffix="ia32",
        efi_format="i386-efi",
        signed_dir="i386-efi-signed",
        non_efi_format="i386-pc",
    ),
}


def get_arch_spec(arch: DebianArchitecture | str) -> ArchSpec:
    """Retrieve the GRUB architecture spec for the given architecture.

    :param arch: Target architecture as a DebianArchitecture enum or string.
    :raises ValueError: If the architecture is not supported.
    """
    try:
        key = arch if isinstance(arch, DebianArchitecture) else DebianArchitecture(arch)
    except ValueError:
        key = None
    if key is None or key not in ARCH_SPECS:
        supported = ", ".join(sorted(a.value for a in ARCH_SPECS))
        raise ValueError(
            f"Unsupported architecture {arch!r} for GRUB installation. "
            f"Supported architectures: {supported}"
        )
    return ARCH_SPECS[key]


# GRUB core modules embedded via grub-mkimage.
CORE_EFI_MODULES: Final[list[str]] = [
    "part_gpt",
    "part_msdos",
    "fat",
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
    "efi_gop",
    "all_video",
]

CORE_BIOS_MODULES: Final[list[str]] = [
    "biosdisk",
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

# ext2/3/4 superblock offsets.
# See https://www.kernel.org/doc/html/latest/filesystems/ext4/dynamic.html#the-superblock
DEFAULT_SECTOR_SIZE: Final = 512
EXT4_SUPERBLOCK_OFFSET: Final = 1024
EXT4_MAGIC_OFFSET: Final = 0x38
EXT4_MAGIC: Final = b"\x53\xef"
EXT4_UUID_OFFSET: Final = 104
EXT4_UUID_BYTES: Final = 16
