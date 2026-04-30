# Copyright 2026 Canonical Ltd.
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

"""Utility functions for MBR-formatted disks."""

import subprocess
from pathlib import Path
from typing import Any

from craft_cli import emit

from imagecraft.errors import MBRPartitionError
from imagecraft.models.volume import MBRVolume, Role
from imagecraft.pack import diskutil

SECTOR_SIZE_512 = 512

SUPPORTED_SECTOR_SIZES = (SECTOR_SIZE_512,)

# The first 1 MiB is reserved for the MBR and alignment padding, matching
# the convention used for GPT images so sector offsets are consistent.
_MBR_RESERVED_SECTORS = 2048
MBR_RESERVED_SIZE: int = _MBR_RESERVED_SECTORS * SECTOR_SIZE_512

# MBR supports 4 primary partition slots. When more than 4 partitions are
# needed, slot 4 is used for an extended container and the remaining entries
# become logical partitions. Each logical partition carries a 1 MiB EBR.
_MAX_PRIMARY_SLOTS = 4
_PRIMARY_SLOTS_WITH_EXTENDED = 3
_EBR_OVERHEAD_SECTORS = 2048


def _create_sfdisk_lines(
    partitions: list[dict[str, Any]],
) -> list[str]:
    """Create sfdisk command lines for an MBR partition table.

    :param partitions: List of partition attribute dicts.
    """
    stdin_lines: list[str] = [
        "label: dos",
        "unit: sectors",
    ]
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


def _create_mbr_layout(
    *,
    imagepath: Path,
    sector_size: int,
    layout: MBRVolume,
) -> None:
    """Write the MBR partition table to an image file.

    :param imagepath: Path to image file.
    :param sector_size: Sector size in bytes.
    :param layout: Disk layout to create.
    :raises MBRPartitionError: If the sector size is unsupported or sfdisk fails.
    """
    if sector_size not in SUPPORTED_SECTOR_SIZES:
        supported_sizes = ", ".join(str(size) for size in SUPPORTED_SECTOR_SIZES)
        raise MBRPartitionError(
            f"Unsupported disk sector size: {sector_size}",
            details=f"Supported sector sizes: {supported_sizes}",
            resolution="Use a supported sector size for the volume.",
        )

    structure = layout.structure

    if len(structure) > _MAX_PRIMARY_SLOTS:
        primary_items = structure[:_PRIMARY_SLOTS_WITH_EXTENDED]
        logical_items = structure[_PRIMARY_SLOTS_WITH_EXTENDED:]
        boot_in_logicals = [
            item for item in logical_items if item.role == Role.SYSTEM_BOOT.value
        ]
        if boot_in_logicals:
            names = ", ".join(item.name for item in boot_in_logicals)
            raise MBRPartitionError(
                "A system-boot partition must be within the first "
                f"{_PRIMARY_SLOTS_WITH_EXTENDED} partitions when an extended "
                "partition is required.",
                details=f"Offending partitions: {names}",
                resolution=f"Move {names} to one of the first "
                f"{_PRIMARY_SLOTS_WITH_EXTENDED} partition slots.",
            )
    else:
        primary_items = structure
        logical_items = []

    partitions: list[dict[str, str | None]] = []
    start = _MBR_RESERVED_SECTORS
    for structure_item in primary_items:
        sectors = diskutil.bytes_to_sectors(structure_item.size, sector_size)
        partition: dict[str, str | None] = {
            "start": str(start),
            "size": str(sectors),
            "type": structure_item.structure_type.value,
        }
        if structure_item.role == Role.SYSTEM_BOOT.value:
            partition["bootable"] = None
        partitions.append(partition)
        start += sectors

    if logical_items:
        ext_sectors = sum(
            _EBR_OVERHEAD_SECTORS + diskutil.bytes_to_sectors(item.size, sector_size)
            for item in logical_items
        )
        partitions.append({"start": str(start), "size": str(ext_sectors), "type": "05"})
        logical_start = start + _EBR_OVERHEAD_SECTORS
        for logical in logical_items:
            logical_sectors = diskutil.bytes_to_sectors(logical.size, sector_size)
            logical_entry: dict[str, str | None] = {
                "start": str(logical_start),
                "size": str(logical_sectors),
                "type": logical.structure_type.value,
            }
            if logical.role == Role.SYSTEM_BOOT.value:
                logical_entry["bootable"] = None
            partitions.append(logical_entry)
            logical_start += logical_sectors + _EBR_OVERHEAD_SECTORS

    stdin_lines: str = "\n".join(_create_sfdisk_lines(partitions))
    emit.trace(f"Stdin for sfdisk:\n{stdin_lines}")
    emit.progress("Partitioning the image")
    emit.debug(f"Running command: {['sfdisk', str(imagepath)]}")
    try:
        subprocess.run(
            ["sfdisk", str(imagepath)],
            input=stdin_lines,
            text=True,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise MBRPartitionError(
            "sfdisk failed to write the MBR partition table.",
            details=e.stderr.strip() or None,
        ) from e


def get_image_size(sector_size: int, layout: MBRVolume) -> int:
    """Determine the necessary image size in bytes for an MBR layout."""
    image_bytes = MBR_RESERVED_SIZE
    needs_extended = len(layout.structure) > _MAX_PRIMARY_SLOTS
    for i, structure_item in enumerate(layout.structure):
        image_bytes += diskutil.align_to_sectors(structure_item.size, sector_size)
        if needs_extended and i >= _PRIMARY_SLOTS_WITH_EXTENDED:
            image_bytes += _EBR_OVERHEAD_SECTORS * sector_size
    return image_bytes


def create_empty_mbr_image(
    imagepath: Path,
    sector_size: int,
    layout: MBRVolume,
) -> None:
    """Create a zeroed image file with an MBR partition table, but no filesystems or data.

    :param imagepath: Path to image file.
    :param sector_size: Sector size in bytes.
    :param layout: Disk layout to create.
    """
    image_bytes = get_image_size(sector_size=sector_size, layout=layout)
    disk_size = diskutil.DiskSize(bytesize=image_bytes, sector_size=sector_size)
    emit.debug("Creating an empty image")
    emit.trace(f"Image size: {image_bytes} bytes")

    diskutil.create_zero_image(imagepath=imagepath, disk_size=disk_size)
    _create_mbr_layout(imagepath=imagepath, sector_size=sector_size, layout=layout)


def verify_partition_tables(imagepath: Path) -> None:
    """Verify the integrity of the MBR partition table.

    :raises MBRPartitionError: If a problem is detected with the partition table.
    """
    try:
        sfdisk_stderr = subprocess.run(
            ["sfdisk", "--json", str(imagepath)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        ).stderr.strip()
    except subprocess.CalledProcessError as e:
        raise MBRPartitionError(
            "sfdisk failed to read the MBR partition table.",
            details=e.stderr.strip() or None,
        ) from e
    if sfdisk_stderr:
        raise MBRPartitionError(
            "There may be a problem with the partition table of the generated disk image.",
            details=sfdisk_stderr,
        )
