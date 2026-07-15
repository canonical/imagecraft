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

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

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


@dataclass
class PartitionGeometry:
    """Geometry of a partition within a disk image."""

    sector_offset: int
    """Start sector of the partition within the image."""

    sector_count: int
    """Number of sectors occupied by the partition."""

    sector_size: int
    """Sector size of the image, in bytes."""

    @property
    def size_bytes(self) -> int:
        """Return the partition size in bytes."""
        return self.sector_count * self.sector_size


# Image file operations


def create_zero_image(*, imagepath: Path, disk_size: DiskSize) -> None:
    """Create an empty image.

    :param imagepath: Path to image file.
    :param disk_size: Disk size attributes.
    :raises CalledProcessError: If truncate fails.
    """
    # Remove possibly pre-existing image
    imagepath.unlink(missing_ok=True)
    emit.debug(f"Creating file {imagepath} with size {disk_size.bytesize} bytes")
    with imagepath.open("w+") as image_file:
        image_file.truncate(disk_size.bytesize)


def _format_populate_ext_partition(
    *,
    fstype: ExtT,
    content_dir: Path | None,
    partitionpath: Path,
    label: str | None = None,
    offset_bytes: int = 0,
    size_bytes: int | None = None,
) -> None:
    """Format a partition/device as EXT3/4 and embed content.

    :param fstype: Type of Ext filesystem (ext3/4).
    :param content_dir: Directory containing contents for partition, or None.
    :param partitionpath: Path to partition file or block device.
    :param label: Ext Filesystem label, empty if not supplied.
    :param offset_bytes: Byte offset within ``partitionpath`` at which to create
        the filesystem. 0 means the start of the file/device.
    :param size_bytes: Size of the filesystem to create, in bytes. When None,
        mke2fs uses the remainder of the device after ``offset_bytes``.
    :raises CalledProcessError: If mke2fs fails.
    """
    mke2fs_args: list[str | Path] = ["-t", fstype]

    if content_dir is not None:
        mke2fs_args.extend(["-d", content_dir])

    if label is not None:
        mke2fs_args.extend(["-L", label])

    if offset_bytes:
        mke2fs_args.extend(["-E", f"offset={offset_bytes}"])

    mke2fs_args.append(partitionpath)

    if size_bytes is not None:
        # The fs-size argument with a 'k' suffix is an absolute size that does
        # not depend on the block size mke2fs picks. Round down to whole KiB so
        # the filesystem never extends past the partition's end.
        mke2fs_args.append(f"{size_bytes // 1024}k")

    with emit.open_stream(f"Creating {fstype} partition (label: {label!r})") as stream:
        run("mke2fs", *mke2fs_args, stdout=stream, stderr=stream)


def _format_populate_fat_partition(  # pylint: disable=too-many-arguments
    *,
    fattype: FatT,
    fatsize: int | None,
    content_dir: Path | None,
    partitionpath: Path,
    label: str | None = None,
    offset_bytes: int = 0,
    sector_size: int = 512,
    size_bytes: int | None = None,
) -> None:
    """Format a partition/device as FAT and copy content.

    :param fattype: One of fat, vfat.
    :param fatsize: 12, 16, 32, or None to let the driver decide.
    :param content_dir: Directory containing contents for partition, or None.
    :param partitionpath: Path to partition file or block device.
    :param label: Fat Filesystem label, empty if not supplied.
    :param offset_bytes: Byte offset within ``partitionpath`` at which to create
        the filesystem. 0 means the start of the file/device.
    :param sector_size: Logical sector size, used to translate ``offset_bytes``
        into the sector unit that ``mkfs.fat --offset`` expects.
    :param size_bytes: Size of the filesystem to create, in bytes. When None,
        mkfs.fat uses the remainder of the device after the offset.
    :raises CalledProcessError: If mkfs.xxx or mcopy fails.
    """
    mkdosfs_args: list[str | Path] = []

    if fatsize is not None:
        mkdosfs_args.extend(["-F", str(fatsize)])

    if label is not None:
        mkdosfs_args.extend(["-n", label])

    if offset_bytes:
        mkdosfs_args.extend(["--offset", str(offset_bytes // sector_size)])

    mkdosfs_args.append(partitionpath)

    if size_bytes is not None:
        # block-count is in 1024-byte blocks; round down to whole KiB so the
        # filesystem stays within the partition.
        mkdosfs_args.append(str(size_bytes // 1024))

    with emit.open_stream(f"Creating {fattype} partition (label: {label!r})") as stream:
        run("mkfs." + fattype, *mkdosfs_args, stdout=stream, stderr=stream)

    if content_dir is not None and any(content_dir.iterdir()):
        # If we invoke mcopy directly, the sh wrapper will quote the
        # source path because it contains a wildcard. This will confuse
        # mcopy. Instead, we wrap the call in bash to get it to
        # remove the quotes. Mcopy will fail if the content directory is
        # empty.
        # Note that the documentation for mcopy's -i flag can be hard to find - some is here:
        # https://www.gnu.org/software/mtools/manual/mtools.html#drive-letters
        # A '@@<byte-offset>' suffix tells mtools where the filesystem starts
        # within the image, mirroring mkfs.fat's --offset.
        image_arg = str(partitionpath)
        if offset_bytes:
            image_arg = f"{image_arg}@@{offset_bytes}"
        mcopy_cmd = f"mcopy -n -o -s -i{image_arg} {content_dir}/* ::"
        with emit.open_stream("Copying files to partition") as stream:
            run("bash", "-c", mcopy_cmd, stdout=stream, stderr=stream)


def format_device(
    *,
    device_path: Path,
    fstype: FileSystem,
    label: str | None = None,
    content_dir: Path | None = None,
) -> None:
    """Format and populate an existing block device or image file.

    Unlike :func:`format_populate_partition`, this function does not create the
    target file — the device must already exist (e.g. a loop-device partition node).

    :param device_path: Path to the block device or image file.
    :param fstype: The filesystem type to create.
    :param label: Optional filesystem label.
    :param content_dir: Optional directory whose contents are copied into the
        filesystem after formatting.
    :raises CraftError: If the device does not exist or the filesystem is unsupported.
    """
    if not device_path.exists():
        raise CraftError(f"Device {device_path} does not exist")

    if fstype.value.startswith("ext"):
        _format_populate_ext_partition(
            fstype=cast(ExtT, fstype.value),
            content_dir=content_dir,
            partitionpath=device_path,
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
            partitionpath=device_path,
            label=label,
        )
        return

    raise CraftError(f"Unsupported filesystem: {fstype}")


def format_populate_partition(
    *,
    fstype: FileSystem,
    content_dir: Path,
    partitionpath: Path,
    label: str | None = None,
    geometry: PartitionGeometry | None = None,
) -> None:
    """Format a partition and copy files.

    When ``geometry`` is given, the filesystem is created in place at the
    partition's offset within ``partitionpath`` (which is then the whole disk
    image) and constrained to the partition's size. mke2fs, mkfs.fat and mcopy
    all support writing at an offset, so this lets imagecraft build partitions
    directly inside the image without loop devices or an intermediate copy.
    When ``geometry`` is None, the whole of ``partitionpath`` is formatted.

    :param fstype: Type of FS - one of (vfat, fat16, ext3, ext4).
    :param content_dir: Directory containing contents for partition.
    :param partitionpath: Path to the partition file, or the disk image when
        ``geometry`` is supplied.
    :param label: Filesystem label, empty if not supplied.
    :param geometry: Optional on-disk geometry of the partition within
        ``partitionpath``.
    """
    offset_bytes = 0
    sector_size = 512
    size_bytes: int | None = None
    if geometry is not None:
        offset_bytes = geometry.sector_offset * geometry.sector_size
        sector_size = geometry.sector_size
        size_bytes = geometry.size_bytes

    if fstype.value.startswith("ext"):
        _format_populate_ext_partition(
            fstype=cast(ExtT, fstype.value),
            content_dir=content_dir,
            partitionpath=partitionpath,
            label=label,
            offset_bytes=offset_bytes,
            size_bytes=size_bytes,
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
            label=label,
            offset_bytes=offset_bytes,
            sector_size=sector_size,
            size_bytes=size_bytes,
        )
        return
    raise CraftError(f"Unsupported filesystem: {fstype}")


def _read_sfdisk_partition_table(imagepath: Path) -> dict[str, Any]:
    """Return the parsed sfdisk --json partition table for a disk image.

    Works for both GPT and MBR partition tables.

    :raises CalledProcessError: If sfdisk fails.
    """
    result = run("sfdisk", "--json", imagepath, stderr=subprocess.PIPE)
    return cast(dict[str, Any], json.loads(result.stdout)["partitiontable"])


def get_partition_geometry(imagepath: Path, partition_number: int) -> PartitionGeometry:
    """Return the on-disk geometry of the given partition.

    Looks up the partition by node suffix (``<imagepath><partition_number>``),
    which works for both GPT and MBR images partitioned via sfdisk.

    :param imagepath: Path to the disk image file.
    :param partition_number: 1-based partition number as written in the
        partition table (for MBR with an extended container, logical
        partitions start at 5).
    :raises CraftError: If the partition cannot be found in the table.
    """
    table = _read_sfdisk_partition_table(imagepath)
    sector_size = int(table.get("sectorsize", 512))
    target_node = f"{imagepath}{partition_number}"
    for partition in table.get("partitions", []):
        if partition.get("node") == target_node:
            return PartitionGeometry(
                sector_offset=int(partition["start"]),
                sector_count=int(partition["size"]),
                sector_size=sector_size,
            )
    raise CraftError(
        f"No partition numbered {partition_number} in {imagepath}",
    )
