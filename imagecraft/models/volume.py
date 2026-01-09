# This file is part of imagecraft.
#
# Copyright 2025-2026 Canonical Ltd.
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
from collections.abc import Collection
from typing import Annotated, Literal, Self, cast

from craft_application.models import (
    CraftBaseModel,
)
from craft_application.models.constraints import (
    get_validator_by_regex,
)
from craft_application.util import humanize_list
from craft_parts.utils.partition_utils import VALID_PARTITION_REGEX
from pydantic import (
    AfterValidator,
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
    """Linux filesystem in a GPT schema."""

    WINDOWS_BASIC = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
    """Microsoft basic data partition in a GPT schema."""

    EFI_SYSTEM = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
    """EFI system partition in a GPT schema."""

    BIOS_BOOT = "21686148-6449-6E6F-744E-656564454649"
    """BIOS boot partition in a GPT schema."""


class FileSystem(enum.Enum):
    """Supported filesystem types."""

    EXT4 = "ext4"
    """The ext4 filesystem."""

    EXT3 = "ext3"
    """The ext3 filesystem."""

    FAT16 = "fat16"
    """The FAT16 filesystem."""

    VFAT = "vfat"
    """The VFAT filesystem."""


class Role(str, enum.Enum):
    """Role describes the purpose of a given partition."""

    SYSTEM_DATA = "system-data"
    """The partition stores the image's primary operating system data."""

    SYSTEM_BOOT = "system-boot"
    """The partition stores the image's boot assets."""


class StructureItem(CraftBaseModel):
    """Structure item of the image."""

    name: StructureName = Field(
        description="The name of the partition.",
        examples=["efi", "rootfs"],
    )
    """The name of the partition.

    The name must:

    - Be unique to the volume
    - Contain only lower case letters and hyphens
    - Contain at least one letter
    - Not start or end with a hyphen
    - Not exceed 36 characters

    The name is interpreted as a UTF-16 encoded string.
    """

    id: uuid.UUID | None = Field(
        default=None,
        description="The partition's unique identifier.",
        examples=[
            "6F8C47A6-1C2D-4B35-8B1E-9DE3C4E9E3FF",
            "E3B0C442-98FC-1FC0-9B42-9AC7E5BD4B35",
        ],
    )
    """The partition's unique identifier.

    The identifier must be a unique 32-digit hexadecimal number in the GPT UUID format.
    """

    role: Role = Field(
        description="The partition's purpose in the image.",
        examples=["system-data", "system-boot"],
    )

    structure_type: GptType = Field(
        alias="type",
        description="The type of the partition.",
        examples=[
            "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
            "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7",
        ],
    )
    """The type of the partition.

    For GPT partitions, the value must be the standard 32-digit hexadecimal number
    associated with the type.

    This is distinct from the ``structure.<partition>.id`` key, which is unique among
    all partitions, regardless of type.
    """

    size: StructureSize = Field(
        description="The size of the partition, in bytes.",
        examples=["256M", "6G"],
    )
    """The size of the partition, in bytes.

    You can append an ``M`` or a ``G`` to the size to specify the unit in mebibytes or
    gibibytes, respectively.
    """

    filesystem: FileSystem = Field(
        description="The filesystem of the partition.",
        examples=["ext4", "fat16"],
    )
    """The filesystem of the partition."""

    filesystem_label: str | None = Field(
        default=None,
        description="A human-readable name to assign the partition.",
        examples=["EFI System", "writable"],
    )
    """A human-readable name to assign the partition.

    If unset, the label will default to the value of ``structure.<partition>.name``.
    Labels must be unique to their volume.
    """

    partition_number: int | None = Field(
        default=None,
        description="(Optional) The partition number for this partition.",
        ge=1,  # GPT partitions are numbered 1-128
        le=129,
    )
    """The partition number for this partition.

    If unset, partitions will start at 1 and be read in list order. If set, all
    other partitions must also explicitly set their partition number as unique integers.
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


def _validate_structure_items_partition_numbers(
    structures: Collection[StructureItem],
) -> Collection[StructureItem]:
    partition_numbers = {structure.partition_number for structure in structures}

    # This could be loosened, but it would require us to generate these partition
    # numbers ourselves in a deterministic manner. This is complex since it would mean
    # that adding a numbered partition could change the partition numbers of other
    # partitions.
    if None in partition_numbers:
        if len(partition_numbers) > 1:
            unnumbered_partitions = humanize_list(
                [
                    structure.name
                    for structure in structures
                    if structure.partition_number is None
                ],
                conjunction="and",
            )
            raise ValueError(
                "all partition numbers must be explicitly declared to use non-sequential "
                f"partition numbers in a volume. (Not numbered: {unnumbered_partitions})"
            )
        return structures

    if len(partition_numbers) < len(structures):
        number_map: dict[int | None, list[str]] = {}
        for structure in structures:
            number_map.setdefault(structure.partition_number, []).append(structure.name)
        duplicate_partition_numbers = {
            number: names for number, names in number_map.items() if len(names) > 1
        }
        duplicate_messages = [
            f"partition-number {number} shared by {humanize_list(names, 'and', sort=False)}"
            for number, names in duplicate_partition_numbers.items()
        ]
        raise ValueError(
            f"duplicate partition numbers ({', '.join(duplicate_messages)})"
        )

    return structures


StructureList = Annotated[
    list[StructureItem],
    AfterValidator(_validate_structure_items_partition_numbers),
]


class Volume(CraftBaseModel):
    """Volume defining properties of the image."""

    volume_schema: Literal[PartitionSchema.GPT] = Field(
        alias="schema",
        description="The partitioning schema of the image.",
        examples=["gpt"],
    )
    """The partitioning schema of the image.

    Imagecraft currently supports GUID partition tables (GPT).
    """

    structure: StructureList = Field(
        min_length=1,
        description="The partitions that comprise the image.",
        examples=[
            "[{name: efi, type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B, filesystem: vfat, role: system-boot, filesystem-label: EFI System, size: 256M}, {name: rootfs, type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4, filesystem: ext4, filesystem-label: writable, role: system-data, size: 6G}]"
        ],
    )
    """The partitions that comprise the image.

    Each entry in the ``structure`` list represents a disk partition in the final
    image.
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
