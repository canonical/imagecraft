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

"""Bootloader installation via prime-directory staging and GRUB's own tools.

Files are staged directly into partition prime directories before
formatting, so ``diskutil.format_device`` embeds them via
``mke2fs -d``/``mcopy``. No loop devices are needed.
"""

from imagecraft.pack.bootloader.installer import (
    BootloaderInstaller,
    find_boot_structure_item,
    find_esp_structure_item,
    find_root_structure_item,
)
from imagecraft.pack.bootloader.models import BootMethod, EfiTier

__all__ = [
    "BootMethod",
    "BootloaderInstaller",
    "EfiTier",
    "find_boot_structure_item",
    "find_esp_structure_item",
    "find_root_structure_item",
]
