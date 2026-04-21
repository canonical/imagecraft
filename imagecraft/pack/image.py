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
import subprocess
import time
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any, cast

from craft_cli import emit

from imagecraft import errors
from imagecraft.models import Role, Volume
from imagecraft.subprocesses import run

_LOSETUP_BIN = "losetup"
_UDEVADM_BIN = "udevadm"
_PARTITION_WAIT_TIMEOUT = 10.0


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


def _volume_partition_nums(volume: Volume) -> list[int]:
    """Return the partition numbers for each structure item in a volume.

    Partition numbers are either explicitly set via ``structure_item.partition_number``
    or implicitly assigned as the 1-based index of the item in the structure list.
    """
    return [
        (s.partition_number or i) for i, s in enumerate(volume.structure, start=1)
    ]


def _wait_for_loopdev_partitions(
    loop_device: str,
    partition_nums: list[int],
    timeout: float = _PARTITION_WAIT_TIMEOUT,
) -> None:
    """Wait for loop device partition nodes to appear in /dev.

    After attaching a loop device with --partscan, the kernel may not
    immediately create the partition device nodes. This function waits
    until all expected partition nodes are available.

    :param loop_device: Path to the loop device (e.g. '/dev/loop7')
    :param partition_nums: List of partition numbers to wait for
    :param timeout: Maximum time to wait in seconds
    :raises errors.ImageError: If partition nodes do not appear within the timeout
    """
    if not partition_nums:
        return

    expected = [Path(f"{loop_device}p{n}") for n in partition_nums]

    # Ask udev to settle so device nodes are created before we poll.
    try:
        run(_UDEVADM_BIN, "settle", "--timeout", str(int(timeout)))
    except (subprocess.CalledProcessError, OSError):
        emit.debug("udevadm settle failed or unavailable; falling back to polling")

    # Poll until all partition nodes appear or the timeout is reached.
    deadline = time.monotonic() + timeout
    missing = [p for p in expected if not p.exists()]
    while missing and time.monotonic() < deadline:
        time.sleep(0.1)
        missing = [p for p in expected if not p.exists()]

    if missing:
        raise errors.ImageError(
            f"Loop device partition nodes did not appear within {timeout:.0f}s: "
            + ", ".join(str(p) for p in missing)
        )


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
        """Check if a data partition is present in the image."""
        return any(s.role == Role.SYSTEM_DATA for s in self.volume.structure)

    @property
    def has_boot_partition(self) -> bool:
        """Check if a boot partition is present in the image."""
        return any(s.role == Role.SYSTEM_BOOT for s in self.volume.structure)

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
            _wait_for_loopdev_partitions(
                self.loop_device, _volume_partition_nums(self.volume)
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
