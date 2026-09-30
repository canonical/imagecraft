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

"""Integration tests for mbrutil — exercises real sfdisk calls."""

import json
import subprocess
from pathlib import Path

import pytest
from imagecraft.models.volume import MBRVolume
from imagecraft.pack import mbrutil

_VOLUME_SINGLE = {
    "schema": "mbr",
    "structure": [
        {
            "name": "rootfs",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "2G",
        },
    ],
}

_VOLUME_SINGLE_SFDISK_EXPECTED = {
    "label": "dos",
    "device": "disk.img",
    "unit": "sectors",
    "sectorsize": 512,
    "partitions": [
        {"node": "disk.img1", "start": 2048, "size": 4194304, "type": "83"},
    ],
}

_VOLUME_TWO_PARTS = {
    "schema": "mbr",
    "structure": [
        {
            "name": "ubuntu-seed",
            "role": "system-boot",
            "type": "0C",
            "filesystem": "vfat",
            "size": "256M",
        },
        {
            "name": "rootfs",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "1G",
        },
    ],
}

_VOLUME_TWO_PARTS_SFDISK_EXPECTED = {
    "label": "dos",
    "device": "disk.img",
    "unit": "sectors",
    "sectorsize": 512,
    "partitions": [
        {
            "node": "disk.img1",
            "start": 2048,
            "size": 524288,
            "type": "c",
            "bootable": True,
        },
        {"node": "disk.img2", "start": 526336, "size": 2097152, "type": "83"},
    ],
}

_VOLUME_FOUR_PARTS = {
    "schema": "mbr",
    "structure": [
        {
            "name": "boot",
            "role": "system-boot",
            "type": "0C",
            "filesystem": "vfat",
            "size": "128M",
        },
        {
            "name": "swap",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "256M",
        },
        {
            "name": "home",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "512M",
        },
        {
            "name": "rootfs",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "1G",
        },
    ],
}

_VOLUME_FOUR_PARTS_SFDISK_EXPECTED = {
    "label": "dos",
    "device": "disk.img",
    "unit": "sectors",
    "sectorsize": 512,
    "partitions": [
        {
            "node": "disk.img1",
            "start": 2048,
            "size": 262144,
            "type": "c",
            "bootable": True,
        },
        {"node": "disk.img2", "start": 264192, "size": 524288, "type": "83"},
        {"node": "disk.img3", "start": 788480, "size": 1048576, "type": "83"},
        {"node": "disk.img4", "start": 1837056, "size": 2097152, "type": "83"},
    ],
}

# Matches ubuntu-26.04-preinstalled-desktop-arm64+raspi.img
_VOLUME_RASPI = {
    "schema": "mbr",
    "structure": [
        {
            "name": "system-boot",
            "role": "system-boot",
            "type": "0C",
            "filesystem": "vfat",
            "size": 1048576 * 512,
        },
        {
            "name": "writable",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": 17524144 * 512,
        },
    ],
}

_VOLUME_RASPI_SFDISK_EXPECTED = {
    "label": "dos",
    "device": "disk.img",
    "unit": "sectors",
    "sectorsize": 512,
    "partitions": [
        {
            "node": "disk.img1",
            "start": 2048,
            "size": 1048576,
            "type": "c",
            "bootable": True,
        },
        {"node": "disk.img2", "start": 1050624, "size": 17524144, "type": "83"},
    ],
}

# Matches ubuntu-core-24-arm64+raspi.img
_VOLUME_CORE_RASPI = {
    "schema": "mbr",
    "structure": [
        {
            "name": "ubuntu-seed",
            "role": "system-seed",
            "type": "0C",
            "filesystem": "vfat",
            "size": 2457600 * 512,
        },
    ],
}

_VOLUME_CORE_RASPI_SFDISK_EXPECTED = {
    "label": "dos",
    "device": "disk.img",
    "unit": "sectors",
    "sectorsize": 512,
    "partitions": [
        {"node": "disk.img1", "start": 2048, "size": 2457600, "type": "c"},
    ],
}

_VOLUME_EXTENDED = {
    "schema": "mbr",
    "structure": [
        {
            "name": "boot",
            "role": "system-boot",
            "type": "0C",
            "filesystem": "vfat",
            "size": "10M",
        },
        {
            "name": "linux1",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "10M",
        },
        {
            "name": "linux2",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "10M",
        },
        {
            "name": "logical1",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "10M",
        },
        {
            "name": "logical2",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "10M",
        },
    ],
}

_VOLUME_EXTENDED_SFDISK_EXPECTED = {
    "label": "dos",
    "device": "disk.img",
    "unit": "sectors",
    "sectorsize": 512,
    "partitions": [
        {
            "node": "disk.img1",
            "start": 2048,
            "size": 20480,
            "type": "c",
            "bootable": True,
        },
        {"node": "disk.img2", "start": 22528, "size": 20480, "type": "83"},
        {"node": "disk.img3", "start": 43008, "size": 20480, "type": "83"},
        {"node": "disk.img4", "start": 63488, "size": 45056, "type": "5"},
        {"node": "disk.img5", "start": 65536, "size": 20480, "type": "83"},
        {"node": "disk.img6", "start": 88064, "size": 20480, "type": "83"},
    ],
}


def _read_partition_table(imagepath: Path) -> dict:
    result = subprocess.run(
        ["sfdisk", "--json", str(imagepath)],
        capture_output=True,
        text=True,
        check=True,
    )
    table = json.loads(result.stdout)["partitiontable"]
    table.pop("id", None)  # Gets randomly generated by sfdisk.
    return table


@pytest.mark.parametrize(
    ("volume_spec", "expected"),
    [
        pytest.param(
            _VOLUME_SINGLE, _VOLUME_SINGLE_SFDISK_EXPECTED, id="single-partition"
        ),
        pytest.param(
            _VOLUME_TWO_PARTS,
            _VOLUME_TWO_PARTS_SFDISK_EXPECTED,
            id="two-partitions-with-bootable",
        ),
        pytest.param(
            _VOLUME_FOUR_PARTS, _VOLUME_FOUR_PARTS_SFDISK_EXPECTED, id="four-partitions"
        ),
        pytest.param(_VOLUME_RASPI, _VOLUME_RASPI_SFDISK_EXPECTED, id="ubuntu-raspi"),
        pytest.param(
            _VOLUME_CORE_RASPI,
            _VOLUME_CORE_RASPI_SFDISK_EXPECTED,
            id="ubuntu-core-raspi",
        ),
        pytest.param(
            _VOLUME_EXTENDED, _VOLUME_EXTENDED_SFDISK_EXPECTED, id="extended-partitions"
        ),
    ],
)
def test_create_empty_mbr_image(new_dir, volume_spec, expected):
    layout = MBRVolume.unmarshal(volume_spec)
    imagepath = Path("disk.img")

    mbrutil.create_empty_mbr_image(imagepath, 512, layout)

    assert imagepath.exists()
    assert imagepath.stat().st_size == mbrutil.get_image_size(512, layout)
    assert _read_partition_table(imagepath) == expected
