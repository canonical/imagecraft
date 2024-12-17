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

from craft_application.models import CraftBaseModel
from pydantic import Field


class VolumeContent(CraftBaseModel):
    """VolumeContent defines the contents of the structure."""

    source: str
    target: str


class Structure(CraftBaseModel):
    """Structure of the image."""

    name: str = ""
    filesystem_label: str = ""
    offset: str = ""
    offset_write: str = ""
    min_size: str = ""
    size: str = ""
    type_: str = Field(alias="type")
    role: str = ""
    id: str = ""
    filesystem: str = ""
    content: list[VolumeContent] | None = None


class Volume(CraftBaseModel):
    """Volume defining properties of the image."""

    schema_: str = Field(alias="schema")
    bootloader: str
    id: str = ""
    structure: list[Structure] | None = None
    _name: str
