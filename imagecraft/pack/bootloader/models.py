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

"""Shared enums for the bootloader installation package."""

import enum


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
    """Standalone EFI binary assembled locally with grub-mkimage."""
