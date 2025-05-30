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

MIB = 1 << 20  # 1 MiB (2^20)
GIB = 1 << 30  # 1 GiB (2^30)

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

    The Volumes specification supports the following values for size:
    - <bytes>
    - <bytes/2^20>M
    - <bytes/2^30>G

    Validate the unit and convert it to a multiplier applied to the numerical value.
    """
    value = str(value)
    match = STRUCTURE_SIZE_COMPILED_REGEX.match(value)

    if not match:
        raise ValueError(SIZE_INVALID_MSG)

    size = int(match.group("size"))
    unit = match.group("unit")

    # convert M/G to MiB/GiB
    if unit == "M":
        size = size * MIB
    elif unit == "G":
        size = size * GIB

    return str(size)


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
    """The identifier for Linux filesystems in a GPT schema."""

    WINDOWS_BASIC = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
    """The identifier for Microsoft basic data partitions in a GPT schema."""

    EFI_SYSTEM = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
    """The identifier for EFI system partitions in a GPT schema."""

    BIOS_BOOT = "21686148-6449-6E6F-744E-656564454649"
    """The identifier for BIOS boot partitions in a GPT schema."""


class FileSystem(enum.Enum):
    """Supported filesystem types."""

    EXT4 = "ext4"
    """A journaling file system for Linux platforms."""

    EXT3 = "ext3"
    """A journaling file system for Linux platforms. The predecessor to ext4."""

    FAT16 = "fat16"
    """A legacy DOS/Windows filesystem."""

    VFAT = "vfat"
    """An extension of the FAT file system allowing for more complex filenames."""


class Role(str, enum.Enum):
    """The role of a given structure."""

    SYSTEM_DATA = "system-data"
    """Denotes that the partition contains the image's primary operating system data."""

    SYSTEM_BOOT = "system-boot"
    """Denotes that the partition contains the image's boot assets."""


class StructureItem(CraftBaseModel):
    """Structure item of the image."""

    name: StructureName = Field(
        description="The name of the partition.",
        examples=["efi", "rootfs"],
    )
    """The name of the partition.

    The name must:

    * contain only lower case letters and hyphens
    * contain at least one letter
    * not start or end with a hyphen
    * not exceed 36 characters in the UTF-16 character set

    """

    id: uuid.UUID | None = Field(
        default=None,
        description="The partition's unique GPT identifier (UUID).",
        examples=[
            "6F8C47A6-1C2D-4B35-8B1E-9DE3C4E9E3FF",
            "E3B0C442-98FC-1FC0-9B42-9AC7E5BD4B35",
        ],
    )

    role: Role = Field(
        description="The partition's function within the image.",
        examples=["system-data", "system-boot"],
    )

    structure_type: GptType = Field(
        alias="type",
        description="The partition's type identifier (GUID).",
        examples=[
            "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
            "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
        ],
    )

    size: StructureSize = Field(
        description="The size of the structure item.",
        examples=["256M", "6G"],
    )
    """The size of the partition expressed in bytes.

    The size can be appended with a "G" or "M" to denote the unit as gibibytes or
    mebibytes, respectively.
    """

    filesystem: FileSystem = Field(
        description="The filesystem type used by the partition.",
        examples=["ext4", "fat16"],
    )
    """The filesystem type used by the partition.

    This key should be set in accordance with the partition's purpose. For example, you
    may use fat16 for your EFI system partition and ext4 for your root filesystem.
    """

    filesystem_label: str | None = Field(
        default=None,
        description="A human-readable name to assign the partition.",
        examples=["EFI System", "writable"],
    )
    """A human-readable name to assign the partition.

    If unset, the label will default to the name of the parent structure item. Labels
    must be unique to their volume.
    """

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
    """The GUID partition table (GPT) schema."""


StructureList = UniqueList[StructureItem]


class Volume(CraftBaseModel):
    """Volume defining properties of the image."""

    volume_schema: Literal[PartitionSchema.GPT] = Field(
        alias="schema",
        description="The partitioning schema used by the image.",
        examples=["gpt"],
    )
    """The partitioning schema used by the image.

    Imagecraft currently supports GUID partition tables (GPT).
    """

    structure: StructureList = Field(
        min_length=1,
        description="The list of partitions that comprise the image.",
        examples=[
            "[{name: efi, type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B, filesystem: vfat, role: system-boot, filesystem-label: EFI System, size: 256M}, {name: rootfs, type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4, filesystem: ext4, filesystem-label: writable, role: system-data, size: 6G}]"
        ],
    )
    """The list of partitions that comprise the image.

    Valid Imagecraft projects must contain at least one partition.
    """

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
