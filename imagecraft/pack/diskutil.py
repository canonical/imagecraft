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

"""Disk-related utility functions."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from craft_cli import CraftError, emit

from imagecraft.models import FileSystem
from imagecraft.subprocesses import run

# pylint: disable=no-member


FatT = Literal["fat", "vfat"]
ExtT = Literal["ext3", "ext4"]


# Conversion functions


def bytes_to_sectors(
    bytes_: int,
    sector_size: int,
) -> int:
    """Convert bytes to sector count.

    The sector count will be rounded up to the nearest sector boundary

    :param bytes_: Byte count.
    :param sector_size: Size of a sector.

    :returns: Number of sectors.
    """
    return (bytes_ + sector_size - 1) // sector_size


def align_to_sectors(
    bytes_: int,
    sector_size: int,
) -> int:
    """Aligns bytes to sector size.

    :param bytes_: Byte count.
    :param sector_size: Size of a sector.

    :returns: Size aligned on the sector size.
    """
    return (((bytes_ - 1) // sector_size) + 1) * sector_size


@dataclass
class DiskSize:
    """Represents a disk size + sector size."""

    bytesize: int
    """Size of the disk"""

    sector_size: int
    """Size of each sector in bytes"""

    @property
    def sector_count(self) -> int:
        """Return number of sectors."""
        return bytes_to_sectors(bytes_=self.bytesize, sector_size=self.sector_size)


# Image file operations


def create_zero_image(*, imagepath: Path, disk_size: DiskSize) -> None:
    """Create an empty image.

    :param imagepath: Path to image file.
    :param disk_size: Disk size attributes.
    :raises CalledProcessError: If truncate fails.
    """
    # Remove possibly pre-existing image
    imagepath.unlink(missing_ok=True)
    run("truncate", f"-s {disk_size.bytesize}", str(imagepath))


def _format_populate_ext_partition(  # pylint: disable=too-many-arguments
    *,
    fstype: ExtT,
    content_dir: Path,
    partitionpath: Path,
    disk_size: DiskSize,
    label: str | None = None,
) -> None:
    """Format partition EXT3/4 and copy files.

    :param fstype: Type of Ext filesystem (ext3/4).
    :param content_dir: Directory containing contents for partition.
    :param partitionpath: Path to partition file.
    :param disk_size: Disk size attributes.
    :param label: Ext Filesystem label, empty if not supplied.
    :raises CalledProcessError: If dd or mke2fs fails.
    """
    # Create the partition file
    create_zero_image(imagepath=partitionpath, disk_size=disk_size)

    # Create and copy
    mke2fs_args = [
        "-q",
        "-t",
        fstype,
        "-d",
        content_dir,
    ]

    if label is not None:
        mke2fs_args.extend(["-L", label])

    mke2fs_args.append(partitionpath)

    run("mke2fs", *mke2fs_args)


def _format_populate_fat_partition(  # pylint: disable=too-many-arguments
    *,
    fattype: FatT,
    fatsize: int | None,
    content_dir: Path,
    partitionpath: Path,
    disk_size: DiskSize,
    label: str | None = None,
) -> None:
    """Format partition FAT and copy files.

    :param fattype: One of fat, vfat.
    :param fatsize: 12, 16, 32, or None to let the driver decide.
    :param content_dir: Directory containing contents for partition.
    :param partitionpath: Path to partition file.
    :param disk_size: Disk size attributes.
    :param label: Fat Filesystem label, empty if not supplied.
    :raises CalledProcessError: If dd, mkfs.xxx, or mcopy fails.
    """
    # Create the partition file
    create_zero_image(imagepath=partitionpath, disk_size=disk_size)

    # Create and copy
    mkdosfs_args: list[str | Path] = []

    if fatsize is not None:
        mkdosfs_args.extend(["-F", str(fatsize)])

    if label is not None:
        mkdosfs_args.extend(["-n", label])

    mkdosfs_args.append(partitionpath)

    run("mkfs." + fattype, *mkdosfs_args)

    if any(content_dir.iterdir()):
        # If we invoke mcopy directly, the sh wrapper will quote the
        # source path because it contains a wildcard. This will confuse
        # mcopy. Instead, we wrap the call in bash to get it to
        # remove the quotes. Mcopy will fail if the content directory is
        # empty.
        # Note that the documentation for mcopy's -i flag can be hard to find - some is here:
        # https://www.gnu.org/software/mtools/manual/mtools.html#drive-letters
        mcopy_cmd = f"mcopy -n -o -s -i{str(partitionpath)} {content_dir}/* ::"
        run("bash", "-c", mcopy_cmd)


def format_populate_partition(
    *,
    fstype: FileSystem,
    content_dir: Path,
    partitionpath: Path,
    disk_size: DiskSize,
    label: str | None = None,
) -> None:
    """Format partition and copy files.

    :param fstype: Type of FS - one of (vfat, fat16, ext3, ext4).
    :param content_dir: Directory containing contents for partition.
    :param partitionpath: Path to partition file.
    :param disk_size: Disk size attributes.
    :param label: Filesystem label, empty if not supplied.
    :param uuid: Filesystem UUID, generated if not supplied.
    """
    if fstype.value.startswith("ext"):
        _format_populate_ext_partition(
            fstype=cast(ExtT, fstype.value),
            content_dir=content_dir,
            partitionpath=partitionpath,
            disk_size=disk_size,
            label=label,
        )
        return
    if "fat" in fstype.value:
        fattype: FatT
        if fstype == FileSystem.VFAT:
            fattype = "vfat"
            fatsize = None
        elif fstype == FileSystem.FAT16:
            fattype = "fat"
            fatsize = 16
        else:
            raise CraftError(f"Unsupported FAT: {fstype}")
        _format_populate_fat_partition(
            fattype=fattype,
            fatsize=fatsize,
            content_dir=content_dir,
            partitionpath=partitionpath,
            disk_size=disk_size,
            label=label,
        )
        return
    raise CraftError(f"Unsupported filesystem: {fstype}")


def inject_partition_into_image(
    *,
    partition: Path,
    imagepath: Path,
    sector_offset: int,
    disk_size: DiskSize,
) -> None:
    """Inject partition into image.

    :param partition: Path to partition file.
    :param imagepath: Path to image file.
    :param sector_offset: Number of image sectors to skip before writing.
    :param disk_size: Disk size attributes.
    :raises CalledProcessError: If dd fails.
    """
    part_size = partition.stat().st_size
    requested_size = disk_size.sector_size * disk_size.sector_count
    if part_size != requested_size:
        raise CraftError(
            f"Partition {partition.name!r} not expected size "
            f"(actual: {part_size} vs. expected: {requested_size})."
        )

    cmd = [
        "dd",
        f"if={str(partition)}",
        f"of={str(imagepath)}",
        f"bs={disk_size.sector_size}",
        f"seek={sector_offset}",
        "status=progress",
        "conv=notrunc,sparse",
    ]
    with subprocess.Popen(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as dd_proc:
        if not dd_proc.stdout:
            return
        for line in iter(dd_proc.stdout.readline, ""):
            emit.trace(line)
        ret = dd_proc.wait()
    if ret:
        raise subprocess.CalledProcessError(ret, cmd)
