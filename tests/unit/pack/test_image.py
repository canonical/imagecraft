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
from subprocess import CompletedProcess
from typing import Any
from unittest.mock import call

import pytest
from imagecraft.models import Volume
from imagecraft.pack.image import Image


def run(cmd: str, *args: Any, **kwargs: Any) -> CompletedProcess[str]:
    if "--json" in args:
        return CompletedProcess(
            args=[cmd, *args],
            returncode=0,
            stdout="""
{
   "loopdevices": [
      {
         "name": "/dev/loop99",
         "back-file": "pc.img"
      }
    ]
}
""",
        )
    if "--find" in args:
        return CompletedProcess(args=[cmd, *args], returncode=0, stdout="loop99")

    return CompletedProcess(args=[cmd, *args], returncode=0, stdout="")


@pytest.mark.usefixtures("new_dir")
class TestImage:
    def test_loopdev(self, mocker, new_dir: Path):
        mock_run = mocker.patch("imagecraft.pack.image.run", side_effect=run)

        volume = Volume.unmarshal(
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
            }
        )
        disk_path = Path(new_dir, "pc.img")
        disk_path.touch(exist_ok=True)
        image = Image(
            volume=volume,
            disk_path=disk_path,
        )
        with image.attach_loopdev() as loop_dev:
            assert loop_dev == "loop99"

        assert mock_run.mock_calls == [
            call("losetup", "--find", "--show", "--partscan", disk_path),
            call("losetup", "--json"),
            call("losetup", "-d", "/dev/loop99"),
        ]

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
        volume = Volume.unmarshal(volume_data)
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
        volume = Volume.unmarshal(volume_data)
        disk_path = Path(new_dir, "pc.img")
        disk_path.touch(exist_ok=True)
        image = Image(
            volume=volume,
            disk_path=disk_path,
        )

        assert image.has_boot_partition == has_boot_partition
