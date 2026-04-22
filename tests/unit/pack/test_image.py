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
        mock_wait = mocker.patch("imagecraft.pack.image.wait_for_loopdev_partitions")

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
        mock_wait.assert_called_once_with("loop99", [1])

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


class TestWaitForLoopdevPartitions:
    """Tests for the wait_for_loopdev_partitions helper."""

    def test_empty_partition_list_returns_immediately(self, mocker):
        """No waiting when there are no partitions to check."""
        from imagecraft.pack.image import wait_for_loopdev_partitions

        mock_run = mocker.patch("imagecraft.pack.image.run")
        mock_sleep = mocker.patch("time.sleep")

        wait_for_loopdev_partitions("/dev/loop0", [])

        mock_run.assert_not_called()
        mock_sleep.assert_not_called()

    def test_waits_until_partitions_appear(self, mocker, tmp_path):
        """Polls until partition device nodes exist."""
        from imagecraft.pack.image import wait_for_loopdev_partitions

        mocker.patch("imagecraft.pack.image.run")

        part1 = tmp_path / "loop0p1"
        part2 = tmp_path / "loop0p2"

        # Simulate partition nodes appearing after two poll cycles.
        call_count = 0

        def fake_exists(self: Path) -> bool:
            nonlocal call_count
            call_count += 1
            # Make nodes appear on the third check (after first poll cycle)
            return call_count > 4

        mocker.patch.object(Path, "exists", fake_exists)
        mocker.patch("time.sleep")

        wait_for_loopdev_partitions(
            str(tmp_path / "loop0"), [1, 2], timeout=5.0
        )

    def test_raises_on_timeout(self, mocker):
        """Raises ImageError when partition nodes don't appear in time."""
        from imagecraft.errors import ImageError
        from imagecraft.pack.image import wait_for_loopdev_partitions

        mocker.patch("imagecraft.pack.image.run")
        mocker.patch.object(Path, "exists", return_value=False)
        mocker.patch("time.sleep")
        # Simulate timeout immediately
        mocker.patch(
            "time.monotonic",
            side_effect=[0.0, 0.0, 100.0],
        )

        with pytest.raises(ImageError, match="partition nodes did not appear"):
            wait_for_loopdev_partitions("/dev/loop0", [1, 2], timeout=1.0)

    def test_udevadm_failure_falls_back_to_polling(self, mocker, tmp_path):
        """Falls back to polling when udevadm settle fails."""
        import subprocess

        from imagecraft.pack.image import wait_for_loopdev_partitions

        part = tmp_path / "loop0p1"
        part.touch()

        # udevadm settle raises CalledProcessError
        mocker.patch(
            "imagecraft.pack.image.run",
            side_effect=subprocess.CalledProcessError(1, "udevadm"),
        )
        mocker.patch.object(Path, "exists", return_value=True)

        # Should not raise even though udevadm failed
        wait_for_loopdev_partitions(str(tmp_path / "loop0"), [1], timeout=5.0)

    def test_calls_udevadm_settle_with_timeout(self, mocker, tmp_path):
        """Calls udevadm settle with the specified timeout."""
        from unittest.mock import call as mcall

        from imagecraft.pack.image import wait_for_loopdev_partitions

        mock_run = mocker.patch("imagecraft.pack.image.run")
        mocker.patch.object(Path, "exists", return_value=True)

        wait_for_loopdev_partitions("/dev/loop5", [1, 2], timeout=7.0)

        mock_run.assert_called_once_with("udevadm", "settle", "--timeout", "7")
