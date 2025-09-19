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

import contextlib
import json
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any, cast

from craft_cli import emit

from imagecraft import errors
from imagecraft.models import Role, Volume
from imagecraft.subprocesses import run

_LOSETUP_BIN = "losetup"


def _get_loop_devices() -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]],
        json.loads(run(_LOSETUP_BIN, "--json").stdout.strip())["loopdevices"],
    )


def _detach_loop_device(
    loop_device: str | Path, file: str | Path | None = None
) -> None:
    emit.debug(f"Detaching loop device {loop_device} (from {file})")
    run(_LOSETUP_BIN, "-d", loop_device)


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
                f"Image specified ({self.disk_path}) doesn't exist or is not a valid file."
            )

    @property
    def has_data_partition(self) -> bool:
        """The partition number associated to the data partition of the image."""
        for _, structure_item in enumerate(self.volume.structure):
            if structure_item.role == Role.SYSTEM_DATA:
                return True
        return False

    @property
    def has_boot_partition(self) -> bool:
        """The partition number associated to the boot partition of the image."""
        for _, structure_item in enumerate(self.volume.structure):
            if structure_item.role == Role.SYSTEM_BOOT:
                return True
        return False

    @contextlib.contextmanager
    def attach_loopdev(self) -> Iterator[str]:
        """Attach a loop device for this image file."""
        if not hasattr(self, "loop_device"):
            # This command attaches a loop device and returns the path in /dev
            self.loop_device = run(
                _LOSETUP_BIN,
                "--find",
                "--show",
                "--partscan",
                self.disk_path,
            ).stdout.strip()
            emit.debug(
                f"Attached image {self.disk_path} as loop device {self.loop_device}"
            )
        try:
            yield self.loop_device
        finally:
            self._detach_loopdevs()

    def _get_loopdevs(self) -> Generator[dict[str, Any]]:
        """Return the loop devices attached from this image file."""
        for loop_device in _get_loop_devices():
            with contextlib.suppress(FileNotFoundError):
                if self.disk_path.samefile(Path(loop_device["back-file"])):
                    yield loop_device

    def _detach_loopdevs(self) -> None:
        """Detach all loop devices that are attached from this image file."""
        for loop_device in self._get_loopdevs():
            _detach_loop_device(loop_device["name"], file=loop_device["back-file"])
