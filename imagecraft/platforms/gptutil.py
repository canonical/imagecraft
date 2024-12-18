# Copyright 2022-2024 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For further info, check https://github.com/canonical/imagecraft

"""Disk related utility functions."""

import json
import pathlib
import re
import uuid
from collections import OrderedDict
from enum import Enum
from typing import Any, Literal

from craft_application.models.base import CraftBaseModel
from craft_cli import CraftError, emit
from pydantic import field_validator

from imagecraft import utils

# Supported Sector Sizes

SUPPORTED_SECTOR_SIZES = [512]
GPT_FOOTER_SECTORS = 33


class GptType(Enum):
    """Supported GUID Partition types."""

    LINUX_DATA = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
    WINDOWS_BASIC = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
    EFI_SYSTEM = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
    BIOS_BOOT = "21686148-6449-6E6F-744E-656564454649"


class GptModel(CraftBaseModel):
    """Base model for GPT disk classes."""


class GptHeader(GptModel):
    """Gpt Header information for sfdisk."""

    label: Literal["gpt"] = "gpt"
    label_id: str | None = None
    unit: Literal["sectors"] = "sectors"

    @field_validator("label_id")
    @classmethod
    def _validate_label_id(cls, label_id: str) -> str:
        """Validate label-id to be a valid UUID."""
        try:
            valid_uuid = uuid.UUID(label_id)
        except TypeError as exc:
            raise ValueError("The supplied UUID is not valid") from exc

        return str(valid_uuid).upper()


class GptPartition(GptModel):
    """Gpt Partition information for sfdisk."""

    start: int
    size: int

    """https://en.wikipedia.org/wiki/GUID_Partition_Table#Partition_type_GUIDs"""
    type: str
    uuid: str | None = None
    name: str | None = None

    @field_validator("type", "uuid")
    @classmethod
    def _validate_type(cls, val: str) -> str:
        """Validate type to be a valid UUID."""
        try:
            valid_uuid = uuid.UUID(val)
        except TypeError as exc:
            raise ValueError("The supplied UUID is not valid") from exc

        return str(valid_uuid).upper()


class MbrHeader(GptModel):
    """Mbr Header information for sfdisk."""

    label: Literal["dos"] = "dos"
    unit: Literal["sectors"] = "sectors"


class MbrPartition(GptModel):
    """Mbr Partition information for sfdisk."""

    start: int
    size: int
    type: str

    @field_validator("type")
    @classmethod
    def _validate_type(cls, val: str) -> str:
        """Validate type to be a valid MBR type."""
        regex = re.compile("[a-fA-F0-9]{2}")
        if regex.match(val) is None:
            raise ValueError("The supplied MBR partition type string is invalid")

        return str(val).upper()


class GptDisk(GptModel):
    """Gpt Disk definition for sfdisk.

    Note that the order of partitions is relevant.
    The partitions in this dictionary will be added as entries into the GPT in
    the same order.
    This order must correspond to ascending partition start sector.
    That is, the order of the actual partition contents on the disk.
    """

    header_lines: GptHeader
    partitions: OrderedDict[str, GptPartition]

    def total_sectors(self) -> int:
        """Get this disk's sector count."""
        last_partition = list(self.partitions.values())[-1]
        return last_partition.start + last_partition.size + GPT_FOOTER_SECTORS


class MbrDisk(GptModel):
    """Gpt Disk definition for sfdisk."""

    header_lines: MbrHeader
    partitions: dict[str, MbrPartition]


class DiskLayout(GptModel):
    """Complete disk layout for sfdisk."""

    gptdisk: GptDisk
    hybridmbrdisk: MbrDisk | None = None


# pylint: disable=no-member


def _create_sfdisk_lines(
    header: dict[str, str], parts: dict[str, dict[str, str]]
) -> list[str]:
    """Create sfdisk command lines.

    :param header: Dictionary with sfdisk header lines.
    :param parts: Dictionary of partitions, each with attributes.
    """
    # The complete list of lines to go on stdin for sfdisk
    # See the 'header lines' and 'unnamed field format' in the
    # sfdisk docs  https://man7.org/linux/man-pages/man8/sfdisk.8.html
    stdin_lines: list[str] = []

    for key, value in header.items():
        stdin_lines.append(f"{key}: {value}\n")

    for entry in parts.values():
        stdin_lines.append(  # noqa: PERF401
            ", ".join([f"{key}={value}" for key, value in entry.items()]) + "\n"
        )

    stdin_lines.append("write\n")

    return stdin_lines


def create_gpt_layout(  # pylint: disable=too-many-branches
    *,
    imagepath: pathlib.Path,
    sector_size: int,
    layout: DiskLayout,
) -> None:
    """Partition image.

    :param imagepath: Path to image file.
    :param sector_size: Sector size in bytes.
    :param layout: Disk layout to create.
    """
    # There is no way today to specify the sector size when using
    # sfdisk (or any other variants) directly on an image file as
    # the block device is not present without a loopback mount. We
    # cannot use loopback devices on unprivileged containers, and
    # even with the latter enabled, loopback control is not
    # namespaced and therefore not elegant or safe to use.
    if sector_size not in SUPPORTED_SECTOR_SIZES:
        raise CraftError(f"Unsupported disk sector size: {sector_size}")

    gptdisk = layout.gptdisk.model_dump(by_alias=True, exclude_none=True, mode="json")

    stdin_lines = _create_sfdisk_lines(gptdisk["header-lines"], gptdisk["partitions"])

    emit.debug(f'Stdin (sfdisk): {" ".join(stdin_lines)}')
    utils.cmd("sfdisk", imagepath, _in=stdin_lines)

    # Process hybrid layout (if present)
    stdin_lines = []

    if layout.hybridmbrdisk is not None:
        hybrid_mbrdisk = layout.hybridmbrdisk.model_dump(
            by_alias=True, exclude_none=True, mode="json"
        )

        stdin_lines = _create_sfdisk_lines(
            hybrid_mbrdisk["header-lines"], hybrid_mbrdisk["partitions"]
        )

        emit.debug(f'Stdin (sfdisk): {" ".join(stdin_lines)}')
        utils.cmd("sfdisk", "--label-nested=mbr", imagepath, _in=stdin_lines)


def _get_partition_table(imagepath: pathlib.Path) -> dict[str, Any]:
    """Return a dict representing the complete partition table."""
    return json.loads(utils.cmd("sfdisk", "--json", imagepath))["partitiontable"]  # type: ignore[no-any-return]


def primary_gpt_sector_count(*, imagepath: pathlib.Path) -> int:
    """Extract which sector the data starts.

    :param imagepath: Path to image file.
    """
    # This is the start of the usable GPT sectors after the header
    # so we know every sector before this is part of the header.
    return int(_get_partition_table(imagepath)["firstlba"])


def extract_primary_gpt(
    *, imagepath: pathlib.Path, sector_size: int, headerpath: pathlib.Path
) -> None:
    """Extract the header sectors.

    :param imagepath: Path to image file.
    :param sector_size: Sector size in bytes.
    :param headerpath: Path to header file for writing.
    """
    count = primary_gpt_sector_count(imagepath=imagepath)

    # Sectors start at zero, so the total is the count to copy
    utils.cmd(
        "dd",
        f"if={str(imagepath)}",
        f"of={str(headerpath)}",
        f"bs={sector_size}",
        f"count={count}",
    )


def backup_gpt_sector_start(*, imagepath: pathlib.Path) -> int:
    """Extract which sector the data starts.

    :param imagepath: Path to image file.
    """
    # This is the end of the usable GPT sectors before the footer
    # so we know every sector after this is the footer.
    return int(_get_partition_table(imagepath)["lastlba"]) + 1


def extract_backup_gpt(
    *, imagepath: pathlib.Path, sector_size: int, footerpath: pathlib.Path
) -> None:
    """Extract the footer sectors.

    :param imagepath: Path to image file.
    :param sector_size: Sector size in bytes.
    :param footerpath: Path to footer file for writing.
    """
    start = backup_gpt_sector_start(imagepath=imagepath)

    # Sectors start at zero, so the total is the count to copy
    utils.cmd(
        "dd",
        f"if={str(imagepath)}",
        f"of={str(footerpath)}",
        f"bs={sector_size}",
        f"skip={start}",
    )
