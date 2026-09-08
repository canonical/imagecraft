# Copyright 2026 Canonical Ltd.
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

"""Direct disk image and filesystem superblock inspection.

These helpers read raw bytes from a disk image file without mounting it or
attaching a loop device, so that filesystem metadata (such as the ext4 UUID)
can be inspected in unprivileged environments.
"""

from pathlib import Path
from uuid import UUID

from imagecraft.pack.bootloader.const import (
    EXT4_MAGIC,
    EXT4_MAGIC_OFFSET,
    EXT4_SUPERBLOCK_OFFSET,
    EXT4_UUID_BYTES,
    EXT4_UUID_OFFSET,
)


def read_ext4_uuid(
    image_path: Path,
    partition_start_bytes: int,
    *,
    validate_magic: bool = True,
) -> UUID:
    """Read the filesystem UUID directly from an ext2/3/4 superblock.

    See the Linux kernel documentation for the on-disk ext4 superblock layout:
    https://www.kernel.org/doc/html/latest/filesystems/ext4/dynamic.html#the-superblock

    :param image_path: Path to the raw disk image file.
    :param partition_start_bytes: Byte offset where the partition starts on disk.
    :param validate_magic: Whether to verify the ext2/3/4 magic signature (0xEF53).
    :return: UUID of the filesystem.
    :raises FileNotFoundError: If the disk image file does not exist.
    :raises ValueError: If the superblock cannot be read or the magic is invalid.
    """
    if not image_path.is_file():
        raise FileNotFoundError(f"Disk image file not found: {image_path}")

    superblock_start = partition_start_bytes + EXT4_SUPERBLOCK_OFFSET

    with image_path.open("rb") as image_file:
        if validate_magic:
            image_file.seek(superblock_start + EXT4_MAGIC_OFFSET)
            magic = image_file.read(len(EXT4_MAGIC))
            if magic != EXT4_MAGIC:
                raise ValueError(
                    f"Partition at byte {partition_start_bytes} does not contain a "
                    f"valid ext2/3/4 filesystem (expected magic {EXT4_MAGIC.hex()}, "
                    f"got {magic.hex()})"
                )

        image_file.seek(superblock_start + EXT4_UUID_OFFSET)
        uuid_bytes = image_file.read(EXT4_UUID_BYTES)
        if len(uuid_bytes) != EXT4_UUID_BYTES:
            raise ValueError(
                f"Failed to read {EXT4_UUID_BYTES} bytes for filesystem UUID at "
                f"offset {superblock_start + EXT4_UUID_OFFSET}"
            )

    return UUID(bytes=uuid_bytes)
