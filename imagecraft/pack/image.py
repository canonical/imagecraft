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

"""Image handling."""

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

from craft_cli import emit

from imagecraft import errors
from imagecraft.models import Role, Volume
from imagecraft.subprocesses import run


def _lsblk(blk_device: str | Path) -> dict[str, Any]:
    blkdevs = json.loads(run("lsblk", "--json", blk_device))["blockdevices"]
    if len(blkdevs) > 1:
        raise errors.ImageError(
            f"Unexpectedly found more than one block device {blk_device}"
        )
    return blkdevs[0]


def _get_loop_devices() -> list[dict[str, Any]]:
    return json.loads(run("losetup", "--json"))["loopdevices"]


def _detach_loop_device(
    loop_device: str | Path, file: str | Path | None = None
) -> None:
    emit.debug("Detaching loop device", loop_device, f"(from {file})")
    run("losetup", "-d", loop_device)


class Image:
    """Image.

    :param volume: the Volume associated to the image.
    :param disk_path: path to the disk.
    """

    volume: Volume
    disk_path: Path

    def __init__(
        self,
        *,
        volume: Volume,
        disk_path: Path,
    ) -> None:
        self.volume = volume
        self.disk_path = disk_path
        if not self.disk_path.is_file():
            raise errors.ImageError(
                f"Image file specified ({self.disk_path}) doesn't exist."
            )

    @property
    def data_partition_number(self) -> int | None:
        """The partition number associated to the data partition of the image."""
        for i, structure_item in enumerate(self.volume.structure):
            if structure_item.Role == Role.SYSTEM_DATA:
                return i
        return None

    @property
    def boot_partition_number(self) -> int | None:
        """The partition number associated to the data partition of the image."""
        for i, structure_item in enumerate(self.volume.structure):
            if structure_item.Role == Role.SYSTEM_BOOT:
                return i
        return None

    def attach_loopdev(self) -> str:
        """Attach a loop device for this image file."""
        if not hasattr(self, "loop_device"):
            # This command attaches a loop device and returns the path in /dev
            self.loop_device = run(
                "losetup",
                "--find",
                "--show",
                "--partscan",
                self.disk_path,
            )
            emit.debug(
                f"Attached image {self.disk_path} as loop device {self.loop_device}"
            )
        return self.loop_device

    def get_loopdevs(self) -> Generator[dict[str, Any]]:
        """Return the loop devices attached from this image file."""
        for loop_device in _get_loop_devices():
            try:
                if self.image_file.samefile(Path(loop_device["back-file"])):
                    yield loop_device
            except FileNotFoundError:  # noqa: PERF203
                continue

    def detach_loopdevs(self) -> None:
        """Detach all loop devices that are attached from this image file."""
        for loop_device in self.get_loopdevs():
            _detach_loop_device(loop_device["name"], file=loop_device["back-file"])

    def get_loopdev_partitions(self) -> list[dict[str, Any]]:
        """Get information about the loop device partitions of the image's loop device."""
        return _lsblk(self.loop_device)["children"]
