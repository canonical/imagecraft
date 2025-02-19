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
from pathlib import Path
from typing import Any

from craft_cli import CraftError, emit

from imagecraft.models import Volume
from imagecraft.pack import diskutil
from imagecraft.subprocesses import run

# Supported Sector Sizes

SUPPORTED_SECTOR_SIZES = [512]


# pylint: disable=no-member


def _create_sfdisk_lines(
    header: dict[str, str], partitions: list[dict[str, str]]
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
        fields = []
        for key, value in entry.items():
            if value is None:
                fields.append(key)
            else:
                fields.append(f"{key}={value}")
        stdin_lines.append(", ".join(fields))

    stdin_lines.append("write")

    return stdin_lines


def create_gpt_layout(  # pylint: disable=too-many-branches
    *,
    imagepath: Path,
    sector_size: int,
    layout: Volume,
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

    header = {
        "label": layout.volume_schema.value,
        "unit": "sectors",
        "sector-size": sector_size,
    }
    partitions = []
    for structure_item in layout.structure:
        partition = {
            "name": f'"{structure_item.name}"',
            "size": diskutil.convert_bytes_to_sectors(
                byte_count=structure_item.size,
                sector_size=sector_size,
            ),
            "type": structure_item.structure_type.value,
        }
        if structure_item.role == "system-boot":
            partition["bootable"] = None
        if structure_item.id:
            partition["uuid"] = structure_item.id
        partitions.append(partition)
    stdin_lines = "\n".join(_create_sfdisk_lines(header, partitions))

    emit.debug(f"Stdin (sfdisk):\n{stdin_lines}")
    run(
        "sfdisk",
        imagepath,
        input=stdin_lines,
    )


def _get_partition_table(imagepath: Path) -> dict[str, Any]:
    """Return a dict representing the complete partition table."""
    return json.loads(run("sfdisk", "--json", imagepath))["partitiontable"]  # type: ignore[no-any-return]


def primary_gpt_sector_count(*, imagepath: Path) -> int:
    """Extract which sector the data starts.

    :param imagepath: Path to image file.
    """
    # This is the start of the usable GPT sectors after the header
    # so we know every sector before this is part of the header.
    return int(_get_partition_table(imagepath)["firstlba"])


def extract_primary_gpt(*, imagepath: Path, sector_size: int, headerpath: Path) -> None:
    """Extract the header sectors.

    :param imagepath: Path to image file.
    :param sector_size: Sector size in bytes.
    :param headerpath: Path to header file for writing.
    """
    count = primary_gpt_sector_count(imagepath=imagepath)

    # Sectors start at zero, so the total is the count to copy
    run(
        "dd",
        f"if={str(imagepath)}",
        f"of={str(headerpath)}",
        f"bs={sector_size}",
        f"count={count}",
    )


def backup_gpt_sector_start(*, imagepath: Path) -> int:
    """Extract which sector the data starts.

    :param imagepath: Path to image file.
    """
    # This is the end of the usable GPT sectors before the footer
    # so we know every sector after this is the footer.
    return int(_get_partition_table(imagepath)["lastlba"]) + 1


def extract_backup_gpt(*, imagepath: Path, sector_size: int, footerpath: Path) -> None:
    """Extract the footer sectors.

    :param imagepath: Path to image file.
    :param sector_size: Sector size in bytes.
    :param footerpath: Path to footer file for writing.
    """
    start = backup_gpt_sector_start(imagepath=imagepath)

    # Sectors start at zero, so the total is the count to copy
    run(
        "dd",
        f"if={str(imagepath)}",
        f"of={str(footerpath)}",
        f"bs={sector_size}",
        f"skip={start}",
    )
