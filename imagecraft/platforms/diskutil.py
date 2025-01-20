# This file is part of imagecraft.
#
# # Copyright 2025 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


"""Disk related utility functions and data structures."""

import enum


class FileSystem(enum.Enum):
    """Supported filesystem types."""

    EXT4 = "ext4"
    EXT3 = "ext3"
    FAT16 = "fat16"
    VFAT = "vfat"
