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

"""Zero-mount bootloader installation.

Replaces the previous loop-device + chroot based ``grubutil`` module. Files
are staged directly into partition prime directories before formatting, and
BIOS boot code is patched directly into the raw disk image bytes, so no
mounts or loop devices are needed to install GRUB.
"""

from imagecraft.pack.bootloader.installer import (
    BootloaderInstaller,
    find_boot_structure_item,
    find_esp_structure_item,
    find_root_structure_item,
)
from imagecraft.pack.bootloader.models import (
    BootloaderResult,
    BootMethod,
    EfiInstallResult,
    EfiTier,
    NonEfiInstallResult,
    RootfsConfigResult,
)

__all__ = [
    "BootMethod",
    "BootloaderInstaller",
    "BootloaderResult",
    "EfiInstallResult",
    "EfiTier",
    "NonEfiInstallResult",
    "RootfsConfigResult",
    "find_boot_structure_item",
    "find_esp_structure_item",
    "find_root_structure_item",
]
