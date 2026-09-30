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

import os
import shutil
from pathlib import Path

import pytest
from imagecraft.models import FileSystem, GPTVolume, MBRVolume
from imagecraft.pack import diskutil, gptutil, mbrutil
from imagecraft.utils.mount import (
    mount_partition,
    mount_volume,
)

from tests.conftest import is_noble_non_amd64


@pytest.fixture(
    params=[
        pytest.param(False, marks=pytest.mark.requires_root, id="as_root"),
        pytest.param(True, id="with_fakeroot"),
    ]
)
def fakeroot(request: pytest.FixtureRequest) -> bool:
    return request.param


@pytest.fixture(
    params=[
        pytest.param(
            GPTVolume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                            "filesystem": "vfat",
                            "size": "32M",
                            "filesystem-label": "EFI",
                        },
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "64M",
                            "filesystem-label": "writable",
                        },
                    ],
                }
            ),
            id="gpt",
        ),
        pytest.param(
            MBRVolume.unmarshal(
                {
                    "schema": "mbr",
                    "structure": [
                        {
                            "name": "ubuntu-seed",
                            "role": "system-boot",
                            "type": "0C",
                            "filesystem": "vfat",
                            "size": "32M",
                            "filesystem-label": "seed",
                        },
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "83",
                            "filesystem": "ext4",
                            "size": "64M",
                            "filesystem-label": "writable",
                        },
                    ],
                }
            ),
            id="mbr",
        ),
    ]
)
def volume_definition(request: pytest.FixtureRequest) -> GPTVolume | MBRVolume:
    return request.param


@pytest.fixture(params=[pytest.param(fs, id=fs.value) for fs in FileSystem])
def fstype(request: pytest.FixtureRequest) -> FileSystem:
    return request.param


def test_mount_partition_standalone(
    tmp_path: Path,
    fstype: FileSystem,
    fakeroot: bool,  # noqa: FBT001
):
    if "ext" in fstype.value and shutil.which("fuse2fs") is None:
        pytest.skip("fuse2fs is not installed")
    if "fat" in fstype.value:
        if is_noble_non_amd64():
            pytest.skip("fusefat is unavailable on noble on non-amd64 architectures")
        if shutil.which("fusefat") is None:
            pytest.skip("fusefat is not installed")

    img_path = tmp_path / f"standalone.{fstype.value}"
    with img_path.open("wb") as f:
        f.truncate(32 * 1024 * 1024)

    content_dir = tmp_path / "empty_content"
    content_dir.mkdir(exist_ok=True)
    diskutil.format_populate_partition(
        fstype=fstype,
        content_dir=content_dir,
        partitionpath=img_path,
    )

    mount = mount_partition(img_path, fstype, fakeroot=fakeroot)
    with mount as root:
        test_file = root / "hello.txt"
        test_file.write_text(f"Hello {fstype.value} FUSE!\n")
        sub_dir = root / "dir" / "subdir"
        sub_dir.mkdir(parents=True)
        (sub_dir / "data.bin").write_bytes(b"PAYLOAD_DATA")

    assert not mount.is_mounted

    # Verify data persisted across unmount
    with mount as root:
        assert (root / "hello.txt").read_text() == f"Hello {fstype.value} FUSE!\n"
        assert (root / "dir" / "subdir" / "data.bin").read_bytes() == b"PAYLOAD_DATA"


def test_mount_partition_offset(
    tmp_path: Path,
    fstype: FileSystem,
    fakeroot: bool,  # noqa: FBT001
):
    if "ext" in fstype.value and shutil.which("fuse2fs") is None:
        pytest.skip("fuse2fs is not installed")
    if "fat" in fstype.value:
        if is_noble_non_amd64():
            pytest.skip("fusefat is unavailable on noble on non-amd64 architectures")
        if shutil.which("fusefat") is None:
            pytest.skip("fusefat is not installed")
        if shutil.which("fusefile") is None:
            pytest.skip("fusefile is not installed")
        if os.geteuid() != 0:
            pytest.skip(
                f"{fstype.value} offset mounts via fusefile require root permissions"
            )

    disk_path = tmp_path / f"disk_{fstype.value}.raw"
    disk_size = 64 * 1024 * 1024
    offset_bytes = 1048576  # 1 MiB
    part_size_bytes = 32 * 1024 * 1024  # 32 MiB

    with disk_path.open("wb") as f:
        f.truncate(disk_size)

    part_tmp = tmp_path / f"part_{fstype.value}.img"
    with part_tmp.open("wb") as f:
        f.truncate(part_size_bytes)
    content_dir = tmp_path / "empty_content"
    content_dir.mkdir(exist_ok=True)
    diskutil.format_populate_partition(
        fstype=fstype,
        content_dir=content_dir,
        partitionpath=part_tmp,
    )

    with part_tmp.open("rb") as src, disk_path.open("r+b") as dst:
        dst.seek(offset_bytes)
        dst.write(src.read())

    part_tmp.unlink()

    mount = mount_partition(
        disk_path,
        fstype,
        offset=offset_bytes,
        size=part_size_bytes,
        fakeroot=fakeroot,
    )

    with mount as root:
        (root / "config.txt").write_text(f"offset {fstype.value} config\n")
        sub_dir = root / "sub"
        sub_dir.mkdir(parents=True)
        (sub_dir / "test.bin").write_bytes(b"OFFSET_BINARY")

    assert not mount.is_mounted

    # Verify persistence directly from the disk image at offset
    with mount as root:
        assert (root / "config.txt").read_text() == f"offset {fstype.value} config\n"
        assert (root / "sub" / "test.bin").read_bytes() == b"OFFSET_BINARY"


@pytest.mark.requires_root
def test_volume_mount(
    volume_definition: GPTVolume | MBRVolume,
    tmp_path: Path,
):
    if is_noble_non_amd64():
        pytest.skip("fusefat is unavailable on noble on non-amd64 architectures")
    if (
        shutil.which("fuse2fs") is None
        or shutil.which("fusefat") is None
        or shutil.which("fusefile") is None
    ):
        pytest.skip(
            "Required FUSE binaries (fuse2fs, fusefat, fusefile) are not installed"
        )
    disk_path = tmp_path / f"{volume_definition.volume_schema.value}_disk.raw"
    sector_size = gptutil.SECTOR_SIZE_512

    if isinstance(volume_definition, GPTVolume):
        gptutil.create_empty_gpt_image(disk_path, sector_size, volume_definition)
    else:
        mbrutil.create_empty_mbr_image(disk_path, sector_size, volume_definition)

    # Format and inject partitions into the image
    for idx, item in enumerate(volume_definition.structure, start=1):
        part_file = tmp_path / f"{item.name}.img"
        with part_file.open("wb") as f:
            f.truncate(int(item.size))
        content_dir = tmp_path / f"{item.name}_content"
        content_dir.mkdir(exist_ok=True)
        diskutil.format_populate_partition(
            fstype=item.filesystem,
            content_dir=content_dir,
            partitionpath=part_file,
            label=item.filesystem_label,
        )
        if isinstance(volume_definition, GPTVolume):
            start_sector = gptutil.get_partition_sector_offset(disk_path, item.name)
        else:
            start_sector = gptutil.get_partition_sector_offset_by_number(disk_path, idx)

        diskutil.inject_partition_into_image(
            partition=part_file,
            imagepath=disk_path,
            sector_offset=start_sector,
            disk_size=diskutil.DiskSize(
                bytesize=int(item.size), sector_size=sector_size
            ),
        )

    # Mount full composite volume
    with mount_volume(volume_definition, disk_path) as rootfs:
        # Write to rootfs (ext4)
        etc_dir = rootfs / "etc"
        etc_dir.mkdir(parents=True, exist_ok=True)
        (etc_dir / "hostname").write_text(
            f"{volume_definition.volume_schema.value}-box\n"
        )

        # Write to EFI / boot partition (vfat, nested under /boot/efi)
        efi_root = rootfs / "boot" / "efi"
        if (efi_root / "EFI").is_file() and (efi_root / "EFI").stat().st_size == 0:
            (efi_root / "EFI").unlink()

        efi_boot = efi_root / "EFI" / "BOOT"
        efi_boot.mkdir(parents=True, exist_ok=True)
        (efi_boot / "grubx64.efi").write_bytes(b"GRUB_BINARY")

    # Remount and verify both filesystems
    with mount_volume(volume_definition, disk_path) as rootfs:
        assert (rootfs / "etc" / "hostname").read_text() == (
            f"{volume_definition.volume_schema.value}-box\n"
        )
        assert (
            rootfs / "boot" / "efi" / "EFI" / "BOOT" / "grubx64.efi"
        ).read_bytes() == b"GRUB_BINARY"
