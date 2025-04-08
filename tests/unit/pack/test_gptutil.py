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

from subprocess import CompletedProcess

import pytest
from craft_cli.errors import CraftError
from imagecraft.models import Volume
from imagecraft.pack import diskutil, gptutil


@pytest.fixture
def volume():
    return Volume(
        schema="gpt",  # pyright: ignore[reportArgumentType]
        structure=[  # pyright: ignore[reportArgumentType]
            {
                "name": "efi",
                "role": "system-boot",
                "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                "filesystem": "vfat",
                "size": "6G",
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
                "size": "0",
                "filesystem-label": "writable",
            },
        ],
    )


@pytest.mark.parametrize(
    ("header", "partitions", "expected"),
    [
        (
            {
                "label": "gpt",
                "unit": "sectors",
                "sector-size": "512",
            },
            [
                {
                    "name": "efi",
                    "size": 524288,
                    "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                    "bootable": None,
                },
                {
                    "name": "rootfs",
                    "size": 2097152,
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "uuid": "6fa819a0-a35a-487a-82d4-a86d1a46b2bb",
                },
            ],
            [
                "label: gpt",
                "unit: sectors",
                "sector-size: 512",
                "name=efi, size=524288, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, bootable",
                "name=rootfs, size=2097152, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, uuid=6fa819a0-a35a-487a-82d4-a86d1a46b2bb",
                "write",
            ],
        ),
    ],
)
def test_create_sfdisk_lines(header, partitions, expected):
    actual = gptutil._create_sfdisk_lines(header, partitions)
    assert actual == expected


def test_create_gpt_layout_unsupported_sector_size(tmp_path, volume):
    with pytest.raises(CraftError) as e:
        gptutil._create_gpt_layout(
            imagepath=tmp_path,
            sector_size=1024,
            layout=volume,
        )
    assert "Unsupported disk sector size: 1024" in str(e)


def test_create_empty_gpt_image(mocker, volume, tmp_path):
    imagepath = tmp_path / "image.img"
    create_gpt_layout = mocker.patch(
        "imagecraft.pack.gptutil._create_gpt_layout", autospec=True
    )
    create_zero_image = mocker.patch(
        "imagecraft.pack.diskutil.create_zero_image", autospec=True
    )

    gptutil.create_empty_gpt_image(imagepath, 512, volume)

    create_gpt_layout.assert_called_with(
        imagepath=imagepath,
        sector_size=512,
        layout=volume,
    )
    bytesize = 2048 * 512 + 34 * 512 + 6 * 1024**3 + 20 * 1024**2
    # partition reserved size +
    # partition table size +
    # partition 1 size +
    # partition 2 size
    create_zero_image.assert_called_with(
        imagepath=imagepath,
        disk_size=diskutil.DiskSize(bytesize=bytesize, sector_size=512),
    )


def test_get_partition_sector_offset(mocker, tmp_path):
    fake_result = CompletedProcess(
        args=[],
        returncode=0,
        stdout="""
{
   "partitiontable": {
      "label": "gpt",
      "id": "F6A132C0-C3D2-4B91-AAB1-02219B9C01BE",
      "device": "example/packt/pc.img",
      "unit": "sectors",
      "firstlba": 2048,
      "lastlba": 13111262,
      "sectorsize": 512,
      "partitions": [
         {
            "node": "example/packt/pc.img1",
            "start": 2048,
            "size": 524288,
            "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
            "uuid": "62D4F0BD-753E-46D0-A74A-38A843AC6105",
            "name": "efi"
         },{
            "node": "example/packt/pc.img2",
            "start": 526336,
            "size": 12582912,
            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
            "uuid": "56788A40-9BAC-410D-863F-97A66797AD49",
            "name": "rootfs"
         }
      ]
   }
}
        """,
    )
    mocker.patch(
        "imagecraft.pack.gptutil.subprocess.run",
        autospec=True,
        side_effect=[fake_result],
    )

    assert gptutil.get_partition_sector_offset(tmp_path, "rootfs") == 526336


def test_verify_partition_tables(mocker, tmp_path):
    fake_result = CompletedProcess(
        args=[],
        returncode=0,
        stdout="",
        stderr="The backup GPT table is corrupt, but the primary appears OK, so that will be used.",
    )
    mocker.patch(
        "imagecraft.pack.gptutil.subprocess.run",
        autospec=True,
        side_effect=[fake_result],
    )
    with pytest.raises(CraftError) as e:
        gptutil.verify_partition_tables(tmp_path)
    assert (
        str(e.value)
        == "There may be a problem with the partition table of the generated disk image."
    )
    assert (
        e.value.details
        == "The backup GPT table is corrupt, but the primary appears OK, so that will be used."
    )
