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

from pathlib import Path

import pytest
from imagecraft.models import GPTVolume
from imagecraft.pack.image import Image


@pytest.mark.usefixtures("new_dir")
class TestImage:
    @pytest.mark.parametrize(
        ("volume_data", "has_data_partition"),
        [
            (
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                    ],
                },
                False,
            ),
            (
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                    ],
                },
                True,
            ),
            (
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                        {
                            "name": "rootfs2",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "rootfs2",
                        },
                    ],
                },
                True,
            ),
        ],
    )
    def test_has_data_partition(
        self,
        volume_data: dict,
        new_dir: Path,
        has_data_partition: bool,  # noqa: FBT001
    ):
        volume = GPTVolume.unmarshal(volume_data)
        disk_path = Path(new_dir, "pc.img")
        disk_path.touch(exist_ok=True)
        image = Image(
            volume=volume,
            disk_path=disk_path,
        )

        assert image.has_data_partition == has_data_partition

    @pytest.mark.parametrize(
        ("volume_data", "has_boot_partition"),
        [
            (
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                    ],
                },
                True,
            ),
            (
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                        {
                            "name": "efi2",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                    ],
                },
                True,
            ),
            (
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                    ],
                },
                False,
            ),
        ],
    )
    def test_has_boot_partition(
        self,
        volume_data: dict,
        new_dir: Path,
        has_boot_partition: bool,  # noqa: FBT001
    ):
        volume = GPTVolume.unmarshal(volume_data)
        disk_path = Path(new_dir, "pc.img")
        disk_path.touch(exist_ok=True)
        image = Image(
            volume=volume,
            disk_path=disk_path,
        )

        assert image.has_boot_partition == has_boot_partition
