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

"""Volume configuration pydantic model."""

import collections
import enum
import re
import typing
import uuid
from typing import Literal, Self, cast

from craft_application.models import (
    CraftBaseModel,
)
from craft_application.models.constraints import (
    UniqueList,
    get_validator_by_regex,
)
from craft_parts.utils.partition_utils import VALID_PARTITION_REGEX
from pydantic import (
    BeforeValidator,
    ByteSize,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

# Avoid matches on substrings when validating Volume/Structure names.
PARTITION_COMPILED_STRICT_REGEX = re.compile(
    r"^" + VALID_PARTITION_REGEX.pattern + r"$", re.ASCII
)

VOLUME_NAME_COMPILED_REGEX = PARTITION_COMPILED_STRICT_REGEX
STRUCTURE_NAME_COMPILED_REGEX = PARTITION_COMPILED_STRICT_REGEX
STRUCTURE_SIZE_COMPILED_REGEX = re.compile(r"^(?P<size>\d+)\s*(?P<unit>[M,G]{0,1})$")

GPT_NAME_MAX_LENGTH = 36

VOLUME_INVALID_MSG = (
    "volume names must only contain lowercase letters, numbers, "
    "and hyphens, and may not begin or end with a hyphen."
)

SIZE_INVALID_MSG = "size must be expressed in bytes, optionally with M or G unit."

StructureName = typing.Annotated[
    str,
    StringConstraints(
        max_length=GPT_NAME_MAX_LENGTH, pattern=STRUCTURE_NAME_COMPILED_REGEX
    ),
]


def _validate_structure_size(value: str) -> str:
    """Validate and convert the structure size.

    The Volume specification does not respect the IEC 80000-13 Standard:
    M means MiB (2^20) in the Volume spec. (means 10^2 in the standard).
    So this validation converts the unit before the conversion to the ByteSize
    type (respecting the IEC 80000-13 Standard).
    """
    value = str(value)
    match = STRUCTURE_SIZE_COMPILED_REGEX.match(value)

    if not match:
        raise ValueError(SIZE_INVALID_MSG)

    # convert M/G to MiB/GiB
    unit: str = ""
    unit_matched = match.group("unit")
    if unit_matched == "M":
        unit = "MiB"
    elif unit_matched == "G":
        unit = "GiB"

    return match.group("size") + unit


StructureSize = typing.Annotated[
    ByteSize,
    BeforeValidator(_validate_structure_size),
]


VolumeName = typing.Annotated[
    str,
    BeforeValidator(
        get_validator_by_regex(VOLUME_NAME_COMPILED_REGEX, VOLUME_INVALID_MSG)
    ),
    StringConstraints(pattern=VOLUME_NAME_COMPILED_REGEX),
]


class GptType(str, enum.Enum):
    """Supported GUID Partition types."""

    LINUX_DATA = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
    WINDOWS_BASIC = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
    EFI_SYSTEM = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
    BIOS_BOOT = "21686148-6449-6E6F-744E-656564454649"


class FileSystem(enum.Enum):
    """Supported filesystem types."""

    EXT4 = "ext4"
    EXT3 = "ext3"
    FAT16 = "fat16"
    VFAT = "vfat"


class Role(str, enum.Enum):
    """Role describes the role of given structure."""

    SYSTEM_DATA = "system-data"
    SYSTEM_BOOT = "system-boot"


class StructureItem(CraftBaseModel):
    """Structure item of the image."""

    name: StructureName
    id: uuid.UUID | None = None
    role: Role
    structure_type: GptType = Field(alias="type")
    size: StructureSize
    filesystem: FileSystem
    filesystem_label: str | None = None

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if type(other) is type(self):
            return self.name == cast(StructureItem, other).name

        return False

    @model_validator(mode="after")
    def _set_default_filesystem_label(self) -> Self:
        if not self.filesystem_label:
            self.filesystem_label = self.name
        return self


class PartitionSchema(str, enum.Enum):
    """Supported partition schemas."""

    GPT = "gpt"


StructureList = UniqueList[StructureItem]


class Volume(CraftBaseModel):
    """Volume defining properties of the image."""

    volume_schema: Literal[PartitionSchema.GPT] = Field(alias="schema")
    structure: StructureList = Field(min_length=1)

    @field_validator("structure", mode="after")
    @classmethod
    def _validate_structure(cls, value: StructureList) -> StructureList:
        fs_labels: list[str] = [str(v.filesystem_label) for v in value]
        fs_labels_set = set(fs_labels)

        if len(fs_labels_set) == len(fs_labels):
            return value

        dupes = [
            item
            for item, count in collections.Counter(fs_labels).items()
            if count > 1 and item != ""
        ]
        raise ValueError(f"Duplicate filesystem labels: {dupes}")
