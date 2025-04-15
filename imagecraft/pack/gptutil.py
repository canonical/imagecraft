# Copyright 2025 Canonical Ltd.
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

"""Utility functions for GPT-formatted disks."""

import json
import subprocess
from pathlib import Path
from typing import Any, cast

from craft_cli import CraftError, emit

from imagecraft.models import Role, Volume
from imagecraft.pack import diskutil
from imagecraft.subprocesses import run

# pylint: disable=no-member

SECTOR_SIZE_512 = 512
SECTOR_SIZE_4K = 4096

SUPPORTED_SECTOR_SIZES = (SECTOR_SIZE_512,)


def _create_sfdisk_lines(
    header: dict[str, str], partitions: list[dict[str, Any]]
) -> list[str]:
    """Create sfdisk command lines.

    :param header: Dictionary with sfdisk header lines.
    :param parts: Dictionary of partitions, each with attributes.
    """
    # The complete list of lines to go on stdin for sfdisk
    # See the 'header lines' and 'named fields format' in the
    # sfdisk docs  https://man7.org/linux/man-pages/man8/sfdisk.8.html
    stdin_lines: list[str] = []

    for key, value in header.items():
        stdin_lines.append(f"{key}: {value}")

    for entry in partitions:
        fields: list[str] = []
        for key, value in entry.items():
            if value is None:
                fields.append(key)
            else:
                fields.append(f"{key}={value}")
        stdin_lines.append(", ".join(fields))

    stdin_lines.append("write")

    return stdin_lines


def _create_gpt_layout(
    *,
    imagepath: Path,
    sector_size: int,
    layout: Volume,
) -> None:
    """Partition image.

    :param imagepath: Path to image file.
    :param sector_size: Sector size in bytes.
    :param layout: Disk layout to create.
    :raises CalledProcessError: If sfdisk fails.
    """
    if sector_size not in SUPPORTED_SECTOR_SIZES:
        raise CraftError(f"Unsupported disk sector size: {sector_size}")

    header: dict[str, str] = {
        "label": layout.volume_schema.value,
        "unit": "sectors",
        "sector-size": str(sector_size),
    }
    partitions: list[dict[str, str | None]] = []
    # Manage start position to avoid sfdisk automatic 1MiB alignment
    start = NON_MBR_START_OFFSET
    for structure_item in layout.structure:
        sectors = diskutil.bytes_to_sectors(
            structure_item.size,
            sector_size,
        )
        partition: dict[str, str | None] = {
            "start": str(start),
            "name": f'"{structure_item.name}"',
            "size": str(sectors),
            "type": structure_item.structure_type.value,
        }
        if structure_item.role == Role.SYSTEM_BOOT.value:
            partition["bootable"] = None
        if structure_item.id:
            partition["uuid"] = str(structure_item.id)
        partitions.append(partition)
        start += sectors
    stdin_lines: str = "\n".join(_create_sfdisk_lines(header, partitions))

    emit.trace(f"Stdin for sfdisk:\n{stdin_lines}")
    emit.message("Partition the image")
    run("sfdisk", imagepath, input=stdin_lines)


# Count of sectors needed to store the GPT header
PARTITION_HEADER_SECTORS: int = 1


def gpt_partition_entries_sectors(sector_size: int) -> int:
    """Get GPT entries section sectors count."""
    partition_entries_sectors = 32

    if sector_size == SECTOR_SIZE_4K:
        partition_entries_sectors = 4

    return partition_entries_sectors


def secondary_gpt_sectors(sector_size: int) -> int:
    """Get backup GPT table sectors count."""
    return PARTITION_HEADER_SECTORS + gpt_partition_entries_sectors(sector_size) + 1


def secondary_partition_table_size(sector_size: int) -> int:
    """Get GPT secondary partition table size."""
    return (secondary_gpt_sectors(sector_size=sector_size)) * sector_size


NON_MBR_START_OFFSET: int = 2048
# NON_MBR_START_OFFSET is the minimum start offset of the first non-MBR structure
# respected by sfdisk
PARTITION_RESERVED_SIZE: int = NON_MBR_START_OFFSET * SECTOR_SIZE_512


def image_size(sector_size: int, layout: Volume) -> int:
    """Determine necessary image size in bytes."""
    # For now be conservative and replicate safe behavior of reserving the
    # first 1MiB of the image for partition table. This must be adapted when
    # handling MBR or hybrid MBR+GPT cases.
    image_bytes = PARTITION_RESERVED_SIZE
    for structure_item in layout.structure:
        image_bytes += diskutil.align_to_sectors(structure_item.size, sector_size)
    image_bytes += secondary_partition_table_size(sector_size=sector_size)

    return image_bytes


def create_empty_gpt_image(
    imagepath: Path,
    sector_size: int,
    layout: Volume,
) -> None:
    """Create a zeroed image file with a GPT partition table, but no filesystems or data.

    :param imagepath: Path to image file.
    :param sector_size: Sector size in bytes.
    :param layout: Disk layout to create.
    """
    image_bytes = image_size(sector_size=sector_size, layout=layout)
    disk_size = diskutil.DiskSize(bytesize=image_bytes, sector_size=sector_size)
    emit.debug("Creating an empty image")
    emit.trace(f"Image size: {image_bytes} bytes")

    diskutil.create_zero_image(imagepath=imagepath, disk_size=disk_size)

    # Create partition table
    _create_gpt_layout(
        imagepath=imagepath,
        sector_size=sector_size,
        layout=layout,
    )


def _get_partition_table(imagepath: Path) -> dict[str, Any]:
    """Return a dict representing the complete partition table.

    :raises CalledProcessError: If sfdisk fails.
    """
    return json.loads(run("sfdisk", "--json", imagepath).stdout)["partitiontable"]  # type: ignore[no-any-return]


def _get_partition_info(imagepath: Path, partname: str) -> dict[str, Any]:
    """Return a dict representing info about the partition named by partname.

    :raises CalledProcessError: If sfdisk fails.
    """
    for partition in _get_partition_table(imagepath)["partitions"]:
        if partition["name"] == partname:
            return cast(dict[str, Any], partition)
    raise CraftError(f"No partition named {partname} in {imagepath}")


def get_partition_sector_offset(imagepath: Path, partname: str) -> int:
    """Return the start sector (offset) for the partition indicated by partname.

    :raises CalledProcessError: If sfdisk fails.
    """
    return cast(int, _get_partition_info(imagepath, partname)["start"])


def verify_partition_tables(imagepath: Path) -> None:
    """Verify the integrity of the partition tables (main and backup).

    :raises CraftError: If a problem is detected with the partition table.
    :raises CalledProcessError: If the partition table is very broken, sfdisk may not be
    able to read it at all and may actually return nonzero.
    """
    # I couldn't find any utility that would exit nonzero when partition table
    # inconsistencies were located.  This implementation is brittle - a proper
    # replacement implementation would be to read the bytes in the primary and backup
    # headers and compare them.  The compare isn't 1:1, the sections are reordered in
    # the backup header.
    # https://en.wikipedia.org/wiki/GUID_Partition_Table
    sfdisk_stderr = run(
        "sfdisk",
        "--json",
        imagepath,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    ).stderr.strip()
    if sfdisk_stderr:
        raise CraftError(
            "There may be a problem with the partition table of the generated disk image.",
            details=sfdisk_stderr,
        )
