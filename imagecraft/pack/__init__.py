# This file is part of imagecraft.
#
# Copyright 2025 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Packing-related utilities for Imagecraft."""

from imagecraft.pack.diskutil import (
    bytes_to_sectors,
    create_zero_image,
    format_populate_partition,
    inject_partition_into_image,
)
from imagecraft.pack.gptutil import (
    SUPPORTED_SECTOR_SIZES,
    create_empty_gpt_image,
    get_partition_sector_offset,
)

from imagecraft.pack.grubutil import setup_grub
from imagecraft.pack.image import Image

__all__ = [
    "bytes_to_sectors",
    "create_zero_image",
    "format_populate_partition",
    "inject_partition_into_image",
    "SUPPORTED_SECTOR_SIZES",
    "create_empty_gpt_image",
    "get_partition_sector_offset",
    "setup_grub",
    "Image",
]
