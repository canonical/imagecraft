# This file is part of imagecraft.
#
# Copyright 2023-2025 Canonical Ltd.
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
"""Data models for Imagecraft."""

from imagecraft.models.project import (
    Project,
    Platform,
    VolumeFilesystemsModel,
    get_partition_name,
)
from imagecraft.models.metadata import ImageMetadata, VolumeMetadata

from imagecraft.models.volume import (
    BaseVolume,
    FileSystem,
    GPTStructureItem,
    GPTVolume,
    MBRVolume,
    PartitionSchema,
    Role,
    Volume,
    is_bios_boot_partition,
)
from imagecraft.models.grammar import get_grammar_aware_volume_keywords

__all__ = [
    "BaseVolume",
    "FileSystem",
    "ImageMetadata",
    "GPTStructureItem",
    "GPTVolume",
    "MBRVolume",
    "PartitionSchema",
    "Platform",
    "Project",
    "Role",
    "VolumeMetadata",
    "Volume",
    "VolumeFilesystemsModel",
    "get_grammar_aware_volume_keywords",
    "get_partition_name",
    "is_bios_boot_partition",
]
