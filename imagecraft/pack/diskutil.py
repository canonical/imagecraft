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

"""Disk related utility functions."""

from pathlib import Path
from typing import Literal

from craft_cli import CraftError

from imagecraft.platforms import FileSystem
from imagecraft.subprocesses import run

# pylint: disable=no-member

FatT = Literal["fat", "vfat"]

# Size constants

GIB = 1 << 30  # 1 GiB
MIB = 1 << 20  # 1 MiB
KIB = 1 << 10  # 1 KiB


# Conversion functions


def bytes_to_sectors(
    bytes_: int,
    sector_size: int,
    unit_multiplier: int = 1,
) -> int:
    """Convert bytes to sector count.

    The sector count will be rounded up to the nearest sector boundary

    :param bytes_: Byte count.
    :param sector_size: Size of a sector.
    :param unit_multiplier: Use one of the *IB constants here if the input unit is
    something larger than "bytes" (KIB, MIB, GIB).

    :returns: Number of sectors.
    """
    return ((bytes_ * unit_multiplier) + sector_size - 1) // sector_size


# Image file operations


def create_zero_image(*, imagepath: Path, sector_size: int, sector_count: int) -> None:
    """Create an empty image.

    :param imagepath: Path to image file.
    :param sector_size: Size of a sector.
    :param sector_count: Number of sectors.
    :raises CalledProcessError: If dd fails.
    """
    run(
        "dd",
        "if=/dev/zero",
        f"of={str(imagepath)}",
        f"bs={sector_size}",
        f"count={sector_count}",
        "conv=sparse",
    )


def format_install_ext_partition(  # pylint: disable=too-many-arguments
    *,
    fstype: str,
    content_dir: Path,
    partitionpath: Path,
    sector_size: int,
    sector_count: int,
    label: str | None = None,
    uuid: str | None = None,
) -> None:
    """Format partition EXT2/3/4 and copy files.

    :param fstype: Type of Ext filesystem (ext2/3/4).
    :param content_dir: Directory containing contents for partition.
    :param partitionpath: Path to partition file.
    :param sector_size: Size of a sector.
    :param sector_count: Number of sectors.
    :param label: Ext Filesystem label, empty if not supplied.
    :param uuid: Ext Filesystem UUID, generated if not supplied.
    :raises CalledProcessError: If dd or mke2fs fails.
    """
    # Create the partition file
    create_zero_image(
        imagepath=partitionpath, sector_size=sector_size, sector_count=sector_count
    )

    # Create and copy
    mke2fs_args = [
        "-Eno_copy_xattrs",
        "-t",
        fstype,
        "-d",
        content_dir,
    ]

    if label is not None:
        mke2fs_args.extend(["-L", label])

    if uuid is not None:
        mke2fs_args.extend(["-U", uuid])

    mke2fs_args.append(partitionpath)

    run("mke2fs", *mke2fs_args)


def format_install_fat_partition(  # pylint: disable=too-many-arguments
    *,
    fattype: FatT,
    fatsize: int | None,
    content_dir: Path,
    partitionpath: Path,
    sector_size: int,
    sector_count: int,
    label: str | None = None,
    uuid: str | None = None,
) -> None:
    """Format partition FAT and copy files.

    :param fattype: One of fat, vfat.
    :param fatsize: 12, 16, 32, or None to let the driver decide.
    :param content_dir: Directory containing contents for partition.
    :param partitionpath: Path to partition file.
    :param sector_size: Size of a sector.
    :param sector_count: Number of sectors.
    :param label: Fat Filesystem label, empty if not supplied.
    :param uuid: Fat Filesystem UUID, generated if not supplied.
    :raises CalledProcessError: If dd, mkfs.xxx, or mcopy fails.
    """
    # Create the partition file
    create_zero_image(
        imagepath=partitionpath, sector_size=sector_size, sector_count=sector_count
    )

    # Create and copy
    mkdosfs_args: list[str | Path] = []

    if fatsize is not None:
        mkdosfs_args.extend(["-F", str(fatsize)])

    if label is not None:
        mkdosfs_args.extend(["-n", label])

    if uuid is not None:
        mkdosfs_args.extend(["-i", uuid])

    mkdosfs_args.append(partitionpath)

    run("mkfs." + fattype, *mkdosfs_args)

    if any(content_dir.iterdir()):
        # If we invoke mcopy directly, the sh wrapper will quote the
        # source path because it contains a wildcard. This will confuse
        # mcopy. Instead, we wrap the call in bash to get it to
        # remove the quotes. Mcopy will fail if the content directory is
        # empty.
        # Note that the -i flag to mcopy seems to be completely undocumented.
        # It appears to insert files into a filesystem file.
        mcopy_args = f"mcopy -n -o -s -i{str(partitionpath)} {content_dir}/* ::"
        run("bash", "-c", mcopy_args)


def format_install_partition(
    *,
    fstype: FileSystem,
    content_dir: Path,
    partitionpath: Path,
    sector_size: int,
    sector_count: int,
    label: str | None = None,
    uuid: str | None = None,
) -> None:
    """Format partition and copy files.

    :param fstype: Type of FS - one of (vfat, fat16, ext3, ext4).
    :param content_dir: Directory containing contents for partition.
    :param partitionpath: Path to partition file.
    :param sector_size: Size of a sector.
    :param sector_count: Number of sectors.
    :param label: Filesystem label, empty if not supplied.
    :param uuid: Filesystem UUID, generated if not supplied.
    """
    if fstype.value.startswith("ext"):
        return format_install_ext_partition(
            fstype=fstype.value,
            content_dir=content_dir,
            partitionpath=partitionpath,
            sector_size=sector_size,
            sector_count=sector_count,
            label=label,
            uuid=uuid,
        )
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
        return format_install_fat_partition(
            fattype=fattype,
            fatsize=fatsize,
            content_dir=content_dir,
            partitionpath=partitionpath,
            sector_size=sector_size,
            sector_count=sector_count,
            label=label,
            uuid=uuid,
        )
    raise CraftError(f"Unsupported filesystem: {fstype}")


def inject_partition_into_image(
    *,
    partition: Path,
    imagepath: Path,
    sector_size: int,
    sector_offset: int,
    sector_count: int,
) -> None:
    """Inject partition into image.

    :param partition: Path to partition file.
    :param imagepath: Path to image file.
    :param sector_size: Size of a sector.
    :param sector_offset: Number of image sectors to skip before writing.
    :param sector_count: Number of sectors to write.
    :raises CalledProcessError: If dd fails.
    """
    part_size = partition.stat().st_size
    requested_size = sector_size * sector_count
    if part_size != requested_size:
        raise CraftError(
            f"Partition {partition.name!r} not expected size "
            f"(actual: {part_size} vs. expected: {requested_size})."
        )

    run(
        "dd",
        f"if={str(partition)}",
        f"of={str(imagepath)}",
        f"bs={sector_size}",
        f"seek={sector_offset}",
        f"count={sector_count}",
        "conv=notrunc,sparse",
    )
