# Copyright 2022-2024 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For further info, check https://github.com/canonical/imagecraft

"""Disk related utility functions."""

import pathlib

from craft_cli import CraftError

from imagecraft import utils

# pylint: disable=no-member


# Size constants

GIB = 1 << 30  # 1 GiB
MIB = 1 << 20  # 1 MiB
KIB = 1 << 10  # 1 KiB


# Conversion functions


def convert_gib_to_sectors(*, gibibyte: int, sector_size: int) -> int:
    """Convert GiB to sector count.

    The sector count will be rounded up to the nearest sector boundary

    :param gibibyte: Gibibytes.
    :param sector_size: Size of a sector.

    :returns: Number of sectors.
    """
    return ((gibibyte * GIB) + (sector_size - 1)) // sector_size


def convert_mib_to_sectors(*, mebibyte: int, sector_size: int) -> int:
    """Convert MiB to sector count.

    The sector count will be rounded up to the nearest sector boundary

    :param gibibyte: Mibibytes.
    :param sector_size: Size of a sector.

    :returns: Number of sectors.
    """
    return ((mebibyte * MIB) + (sector_size - 1)) // sector_size


def convert_kib_to_sectors(*, kibibyte: int, sector_size: int) -> int:
    """Convert KiB to sector count.

    The sector count will be rounded up to the nearest sector boundary

    :param gibibyte: Kibibytes.
    :param sector_size: Size of a sector.

    :returns: Number of sectors.
    """
    return ((kibibyte * KIB) + (sector_size - 1)) // sector_size


# Image file operations


def create_zero_image(
    *,
    imagepath: pathlib.Path,
    sector_size: int,  # noqa: ARG001 - Unused function argument
    sector_count: int,
) -> None:
    """Create an empty image.

    :param imagepath: Path to image file.
    :param sector_size: Size of a sector.
    :param sector_count: Number of sectors.
    """
    utils.cmd(
        "truncate",
        "-s",
        f"{sector_count}",
        f"{str(imagepath)}",
    )


def format_install_ext_partition(  # pylint: disable=too-many-arguments
    *,
    content_dir: pathlib.Path,
    sector_size: int,
    sector_count: int,
    partitionpath: pathlib.Path,
    fstype: str,
    label: str | None = None,
    uuid: str | None = None,
) -> None:
    """Format partition EXT2/3/4 and copy files.

    :param content_dir: Directory containing contents for partition.
    :param sector_size: Size of a sector.
    :param sector_count: Number of sectors.
    :param partitionpath: Path to partition file.
    :param fstype: Type of Ext filesystem (ext2/3/4).
    :param label: Ext Filesystem label, empty if not supplied.
    :param uuid: Ext Filesystem UUID, generated if not supplied.
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

    utils.cmd("mke2fs", *mke2fs_args)


def format_install_fat_partition(  # pylint: disable=too-many-arguments
    *,
    content_dir: pathlib.Path,
    sector_size: int,
    sector_count: int,
    partitionpath: pathlib.Path,
    label: str | None = None,
    uuid: str | None = None,
) -> None:
    """Format partition FAT32 and copy files.

    :param content_dir: Directory containing contents for partition.
    :param sector_size: Size of a sector.
    :param sector_count: Number of sectors.
    :param partitionpath: Path to partition file.
    :param label: Fat Filesystem label, empty if not supplied.
    :param uuid: Fat Filesystem UUID, generated if not supplied.
    """
    # Create the partition file
    create_zero_image(
        imagepath=partitionpath, sector_size=sector_size, sector_count=sector_count
    )

    # Create and copy
    mkdosfs_args: list[str | pathlib.Path] = [
        "-F",
        "32",
    ]

    if label is not None:
        mkdosfs_args.extend(["-n", label])

    if uuid is not None:
        mkdosfs_args.extend(["-i", uuid])

    mkdosfs_args.append(partitionpath)

    utils.cmd("mkdosfs", *mkdosfs_args)

    if any(content_dir.iterdir()):
        # If we invoke mcopy directly, the sh wrapper will quote the
        # source path because it contains a wildcard. This will confuse
        # mcopy. Instead, we wrap the call in bash to get it to
        # remove the quotes. Mcopy will fail if the content directory is
        # empty.
        # Note that the -i flag to mcopy seems to be completely undocumented.
        # It appears to insert files into a filesystem file.
        mcopy_args = f"mcopy -n -o -s -i{str(partitionpath)} {content_dir}/* ::"
        utils.cmd("bash", "-c", mcopy_args)


def inject_partition_into_image(
    *,
    partition: pathlib.Path,
    imagepath: pathlib.Path,
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
    """
    part_size = partition.stat().st_size
    requested_size = sector_size * sector_count
    if part_size != requested_size:
        raise CraftError(
            f"Partition {partition.name!r} not expected size "
            f"(actual: {part_size} vs. expected: {requested_size})."
        )

    utils.cmd(
        "dd",
        f"if={str(partition)}",
        f"of={str(imagepath)}",
        f"bs={sector_size}",
        f"seek={sector_offset}",
        f"count={sector_count}",
        "conv=notrunc,sparse",
    )


def compare_contents_partition_size(
    *,
    partition_name: str,
    available_size_bytes: int,
    fit_image: pathlib.Path,
    fit_contents_src: pathlib.Path,
) -> None:
    """Ensure the FIT image will fit in the partition.

    In case of failure, the culprit is probably extra stuff going into the
    initramfs, so point the user to the source dir where those files are.
    """
    actual_size_bytes = fit_image.stat().st_size
    if actual_size_bytes > available_size_bytes:
        raise CraftError(
            f"Disk contents are too large for {partition_name}, "
            f"check for extra or large files in {fit_contents_src}.  Contents "
            f"need to be <={available_size_bytes * MIB}MB, but are "
            f"{actual_size_bytes * MIB}MB."
        )
