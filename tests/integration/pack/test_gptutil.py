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

import pathlib

import pytest
from imagecraft.models import GPTVolume
from imagecraft.pack import gptutil
from imagecraft.pack.gptutil import SECTOR_SIZE_512

EFI_PARTITION_SIZE_BYTES = 32 * (1024**2)  # 32 MiB
BOOT_PARTITION_SIZE_BYTES = 20 * (1024**2)  # 20 MiB
ROOTFS_PARTITION_SIZE_BYTES = 128 * (1024**2)  # 128 MiB


@pytest.fixture
def layout():
    return GPTVolume.unmarshal(
        {
            "schema": "gpt",
            "structure": [
                {
                    "name": "efi",
                    "role": "system-boot",
                    "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                    "filesystem": "vfat",
                    "size": "32M",
                    "filesystem-label": "",
                },
                {
                    "name": "boot",
                    "role": "system-boot",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "fat16",
                    "size": "20M",
                },
                {
                    "name": "rootfs",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "id": "6fa819a0-a35a-487a-82d4-a86d1a46b2bb",
                    "filesystem": "ext4",
                    "size": "128M",
                    "filesystem-label": "writable",
                },
            ],
        }
    )


@pytest.fixture
def image(tmp_path, request: pytest.FixtureRequest, layout: GPTVolume):
    image_path = tmp_path / "empty.img"
    gptutil.create_empty_gpt_image(image_path, SECTOR_SIZE_512, layout)
    return image_path


def test_get_partition_size_sectors(tmp_path, layout: GPTVolume, image: pathlib.Path):
    """Check that the partition's size is what's expected."""
    assert (
        gptutil.get_partition_size_sectors(image, "efi")
        == EFI_PARTITION_SIZE_BYTES // SECTOR_SIZE_512
    )
    assert (
        gptutil.get_partition_size_sectors(image, "boot")
        == BOOT_PARTITION_SIZE_BYTES // SECTOR_SIZE_512
    )
    assert (
        gptutil.get_partition_size_sectors(image, "rootfs")
        == ROOTFS_PARTITION_SIZE_BYTES // SECTOR_SIZE_512
    )
