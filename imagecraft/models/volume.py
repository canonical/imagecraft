# This file is part of imagecraft.
#
# Copyright 2023 Canonical Ltd.
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

"""Volume configuration pydantic model."""

import enum

from craft_application.models import CraftBaseModel
from pydantic import Field

from imagecraft.platforms.gptutil import GptType


class VolumeContent(CraftBaseModel):
    """VolumeContent defines the contents of the structure."""

    source: str
    target: str


class Role(enum.Enum):
    """Role describes the role of given structure."""

    UNSPECIFIED = ""
    MBR = "mbr"
    SYSTEM_DATA = "system-data"
    SYSTEM_BOOT = "system-boot"


class PartitionSchema(enum.Enum):
    """Supported partition schemas."""

    MBR = "mbr"
    GPT = "gpt"


class StructureItem(CraftBaseModel):
    """Structure item of the image."""

    name: str = ""
    filesystem_label: str = ""
    offset: str = ""
    offset_write: str = ""
    min_size: str = ""
    size: str = ""
    type_: GptType = Field(alias="type")
    role: Role
    id: str = ""
    filesystem: str = ""
    content: list[VolumeContent] | None = None


class Volume(CraftBaseModel):
    """Volume defining properties of the image."""

    schema_: PartitionSchema = Field(default=PartitionSchema.GPT, alias="schema")
    bootloader: str
    id: str = ""
    structure: list[StructureItem] | None = None
    _name: str

    def data_structure(self) -> StructureItem | None:
        """Get the structure defining the partition holding the main operating system data."""
        if self.structure is None:
            return None
        for s in self.structure:
            if s.role == Role.SYSTEM_DATA:
                return s
        return None

    @property
    def name(self) -> str:
        """Name of the volume."""
        return self._name
