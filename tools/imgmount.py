#!/usr/bin/env python3
"""Utility to mount and unmount imagecraft images."""
# Various invocations here can have multiple numbers of args, so magic values are ok.
# ruff: noqa: PLR2004

import contextlib
import json
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

ME = Path(sys.argv[0]).name
MP_ROOT = Path("/mnt/imagecraft")


def print_usage_exit() -> None:
    """Display the program's usage information and exit."""
    print(f"""\
{ME} [mount] {{file.img}} - Mount the image's partitions in subdirs under {MP_ROOT}.
{ME} umount [file.img] - Unmount any currently-mounted image, or the one specified.
""")
    sys.exit(0)


def usage_error_exit(what: str | None = None) -> None:
    """Display an error message caused by the user and exit."""
    if not what:
        what = "Incorrect usage"
    sys.exit(what + f" - try '{ME} help'")


def vprint(*args: Any, **kwargs: Any) -> None:
    """Display verbose status messages."""
    print(*args, **kwargs)


def _run(*args: Any) -> Any:  # noqa: ANN401
    return subprocess.run(
        list(args),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def _get_loop_devices() -> list[dict[str, Any]]:
    return json.loads(_run("losetup", "--json"))["loopdevices"]


def _detach_loop_device(
    loop_device: str | Path, file: str | Path | None = None
) -> None:
    vprint("Detaching loop device", loop_device, f"(from {file})")
    _run("losetup", "-d", loop_device)


def _lsblk(blk_device: str | Path) -> dict[str, Any]:
    blkdevs = json.loads(_run("lsblk", "--json", blk_device))["blockdevices"]
    if len(blkdevs) > 1:
        sys.exit(f"Unexpectedly found more than one block device {blk_device}")
    return blkdevs[0]


def _findmnt(path: str | Path) -> dict[str, str]:
    return json.loads(_run("findmnt", "--json", path))["filesystems"]


def _mount(dev: str | Path, mp: str | Path) -> None:
    """Mount the device dev at path mp."""
    vprint(f"Mounting {dev} at {mp}")
    _run("mount", dev, mp)


def _umount(path: str | Path) -> None:
    """Unmount the path - can be either a dev entry or mountpoint."""
    vprint(f"Unmounting {path}")
    _run("umount", path)


class ImageFile:
    """Wraps an image file produced by imagecraft."""

    def __init__(self, image_file: str | Path) -> None:
        self.image_file = Path(image_file)
        if not self.image_file.is_file():
            sys.exit(f"Image file specified ({self.image_file}) doesn't exist.")

    def _sfdisk(self) -> Any:  # noqa: ANN401
        # The sfdisk output won't change at imgmount runtime, only make the call once
        if not hasattr(self, "_sfdisk_out"):
            self._sfdisk_out = json.loads(
                _run(
                    "sfdisk",
                    "--json",
                    self.image_file,
                )
            )["partitiontable"]
        return self._sfdisk_out

    def get_img_partitions(self) -> list[dict[str, Any]]:
        """Return information about the partitions in this image file."""
        return self._sfdisk()["partitions"]

    def _get_sector_size(self) -> int:
        partition_table = self._sfdisk()
        if partition_table["unit"] != "sectors":
            sys.exit("Support for non-sector units not implemented")
        return partition_table["sectorsize"]

    def attach_loopdev(self) -> str:
        """Attach a loop device for this image file."""
        if not hasattr(self, "loop_device"):
            # This command attaches a loop device and returns the path in /dev
            self.loop_device = _run(
                "losetup",
                "--find",
                "--show",
                "--partscan",
                self.image_file,
            )
            vprint(
                f"Attached image {self.image_file} as loop device {self.loop_device}"
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


def umount(image_file: Path | None) -> None:
    """Unmount the specified imagecraft image file, or if none specified unmount the one mounted."""
    if not image_file:
        sys.exit(
            "Unmounting without specifying an image file is currently not implemented."
        )

    image = ImageFile(image_file)
    for partition in image.get_img_partitions():
        partition_mp = MP_ROOT / partition["name"]
        if not partition_mp.is_mount():
            vprint(f"{partition_mp} is not mounted")
        else:
            _umount(partition_mp)
        with contextlib.suppress(FileNotFoundError):
            partition_mp.rmdir()

    with contextlib.suppress(FileNotFoundError):
        MP_ROOT.rmdir()
    image.detach_loopdevs()
    sys.exit(0)


def mount(image_file: str | Path) -> None:
    """Mount the specified imagecraft image file."""
    image = ImageFile(image_file)
    image.attach_loopdev()

    for loopdev_part, img_part in zip(
        image.get_loopdev_partitions(),
        image.get_img_partitions(),
    ):
        partition_mp = MP_ROOT / img_part["name"]
        partition_mp.mkdir(parents=True, exist_ok=True)
        if partition_mp.is_mount():
            sys.exit(
                f"Refusing to mount - something is already mounted at {partition_mp}"
            )

        partition_loopdev = Path("/dev", loopdev_part["name"])

        _mount(partition_loopdev, partition_mp)
    sys.exit(0)


def main() -> None:
    """Do the main things."""
    if len(sys.argv) == 1:
        usage_error_exit("Argument required")

    subcommand = sys.argv[1]

    image_file = None
    if subcommand in ("umount", "unmount"):
        if len(sys.argv) > 2:
            image_file = Path(sys.argv[2])
            if not image_file.is_file():
                usage_error_exit(
                    "You can optionally pass an image file to 'umount', but you "
                    f"passed '{image_file}'"
                )
        umount(image_file)
    elif subcommand == "mount":
        if len(sys.argv) != 3:
            usage_error_exit("Specify the image file to mount")
        image_file = sys.argv[2]
    elif subcommand in ("usage", "help", "--help", "-h"):
        print_usage_exit()

    # Try to assume "mount" was intended but omitted
    if subcommand != "mount":
        if Path(subcommand).is_file():
            image_file = subcommand
            subcommand = "mount"
        else:
            usage_error_exit(f"Unknown subcommand {subcommand}")

    if not image_file:
        # This case shouldn't be possible to hit, but adding this check makes pyright
        # happy and guards against logic errors.
        sys.exit("Image file not specified")
    mount(image_file)


if __name__ == "__main__":
    main()
