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

import contextlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from craft_parts.filesystem_mounts import FilesystemMount
from craft_platforms import DebianArchitecture
from imagecraft.errors import ImageError
from imagecraft.models import Volume
from imagecraft.models.volume import (
    GPTStructureItem,
    GPTVolume,
    MBRStructureItem,
    MBRVolume,
)
from imagecraft.pack.chroot import Mount
from imagecraft.pack.grubutil import _image_mounts, _part_num, setup_grub
from imagecraft.pack.image import Image


@pytest.fixture
def volume():
    return GPTVolume.unmarshal(
        {
            "schema": "gpt",
            "structure": [
                {
                    "name": "efi",
                    "role": "system-boot",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "vfat",
                    "size": "3G",
                    "filesystem-label": "",
                },
                {
                    "name": "boot",
                    "role": "system-boot",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "fat16",
                    "size": "6G",
                },
                {
                    "name": "rootfs",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "0",
                    "filesystem-label": "writable",
                },
            ],
        }
    )


@contextlib.contextmanager
def fake_loopdev_handler():
    yield "loop99"


@pytest.mark.parametrize(
    ("filesystem_mount"),
    [
        FilesystemMount.unmarshal(
            [
                {"mount": "/", "device": "(volume/pc/rootfs)"},
                {"mount": "/boot", "device": "(volume/pc/boot)"},
                {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
            ]
        ),
        FilesystemMount.unmarshal(
            [
                {"mount": "/", "device": "(volume/pc/rootfs)"},
                {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
            ]
        ),
    ],
)
@pytest.mark.usefixtures("new_dir")
def test_setup_grub(mocker, new_dir, volume, filesystem_mount):
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(
        volume=volume,
        disk_path=disk_path,
    )
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    mock_chroot = mocker.patch("imagecraft.pack.grubutil.Chroot")
    mocker.patch.object(image, "attach_loopdev", side_effect=fake_loopdev_handler)

    setup_grub(
        image=image,
        workdir=workdir,
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    assert mock_chroot.return_value.execute.called
    assert (
        mock_chroot.return_value.execute.call_args.kwargs["grub_target"] == "x86_64-efi"
    )


@pytest.mark.parametrize(
    ("volume", "arch", "message"),
    [
        (
            GPTVolume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                    ],
                }
            ),
            DebianArchitecture.AMD64,
            "Skipping GRUB installation because no boot partition was found",
        ),
        (
            GPTVolume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                    ],
                }
            ),
            DebianArchitecture.AMD64,
            "Skipping GRUB installation because no data partition was found",
        ),
        (
            GPTVolume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                    ],
                }
            ),
            DebianArchitecture.S390X,
            "Cannot install GRUB on this architecture",
        ),
        (
            MBRVolume.unmarshal(
                {
                    "schema": "mbr",
                    "structure": [
                        {
                            "name": "boot",
                            "role": "system-boot",
                            "type": "83",
                            "filesystem": "ext4",
                            "size": "512M",
                        },
                    ],
                }
            ),
            DebianArchitecture.AMD64,
            "Skipping GRUB installation because no data partition was found",
        ),
        (
            MBRVolume.unmarshal(
                {
                    "schema": "mbr",
                    "structure": [
                        {
                            "name": "boot",
                            "role": "system-boot",
                            "type": "83",
                            "filesystem": "ext4",
                            "size": "512M",
                        },
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "83",
                            "filesystem": "ext4",
                            "size": "5G",
                        },
                    ],
                }
            ),
            DebianArchitecture.ARM64,
            "Cannot install GRUB on this architecture",
        ),
    ],
)
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_partitions(mocker, new_dir, volume, arch, emitter, message):
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
        ]
    )
    image = Image(
        volume=volume,
        disk_path=disk_path,
    )
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    mock_chroot = mocker.patch("imagecraft.pack.grubutil.Chroot")
    mocker.patch.object(image, "attach_loopdev", side_effect=fake_loopdev_handler)

    setup_grub(
        image=image, workdir=workdir, arch=arch, filesystem_mount=filesystem_mount
    )

    mock_chroot.return_value.execute.assert_not_called()

    emitter.assert_progress(message, permanent=True)


_MBR_VOLUME_WITH_BOOT = MBRVolume.unmarshal(
    {
        "schema": "mbr",
        "structure": [
            {
                "name": "boot",
                "role": "system-boot",
                "type": "83",
                "filesystem": "ext4",
                "size": "512M",
            },
            {
                "name": "rootfs",
                "role": "system-data",
                "type": "83",
                "filesystem": "ext4",
                "size": "5G",
            },
        ],
    }
)


@pytest.mark.parametrize(
    "arch",
    [DebianArchitecture.AMD64, DebianArchitecture.I386],
)
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_mbr_bios(mocker, new_dir, arch):
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(volume=_MBR_VOLUME_WITH_BOOT, disk_path=disk_path)
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    mock_chroot = mocker.patch("imagecraft.pack.grubutil.Chroot")
    mocker.patch.object(image, "attach_loopdev", side_effect=fake_loopdev_handler)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot", "device": "(volume/pc/boot)"},
        ]
    )

    setup_grub(
        image=image, workdir=workdir, arch=arch, filesystem_mount=filesystem_mount
    )

    assert mock_chroot.return_value.execute.called
    assert mock_chroot.return_value.execute.call_args.kwargs["grub_target"] == "i386-pc"


@pytest.mark.parametrize(
    ("loop_dev", "volume", "filesystem_mount", "mounts"),
    [
        (
            "/dev/loop99",
            GPTVolume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                    ],
                }
            ),
            FilesystemMount.unmarshal(
                [
                    {"mount": "/", "device": "(volume/pc/rootfs)"},
                    {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
                ]
            ),
            [
                Mount(
                    fstype=None,
                    src="/dev/loop99p2",
                    relative_mountpoint="/",
                ),
                Mount(
                    fstype=None,
                    src="/dev/loop99p1",
                    relative_mountpoint="/boot/efi",
                ),
            ],
        ),
        (
            "/dev/loop99",
            GPTVolume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                    ],
                }
            ),
            FilesystemMount.unmarshal(
                [
                    {"mount": "/", "device": "(volume/pc/rootfs)"},
                ]
            ),
            [
                Mount(
                    fstype=None,
                    src="/dev/loop99p2",
                    relative_mountpoint="/",
                ),
            ],
        ),
    ],
)
def test_image_mounts(
    loop_dev: str,
    volume: Volume,
    filesystem_mount: FilesystemMount,
    mounts: list[Mount],
):
    assert _image_mounts(loop_dev, volume.structure, filesystem_mount) == mounts


@pytest.mark.parametrize(
    ("loop_dev", "volume", "filesystem_mount"),
    [
        (
            "/dev/loop99",
            GPTVolume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                    ],
                }
            ),
            FilesystemMount.unmarshal(
                [
                    {"mount": "/", "device": "(volume/pc/not-matching)"},
                ]
            ),
        ),
    ],
)
def test_image_mounts_errors(
    loop_dev: str,
    volume: Volume,
    filesystem_mount: FilesystemMount,
):
    with pytest.raises(ImageError, match="Cannot find a partition named"):
        _image_mounts(loop_dev, volume.structure, filesystem_mount)


# ── _part_num ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "structure_spec", "expected"),
    [
        pytest.param(
            "rootfs",
            [
                {"name": "efi", "partition_number": None},
                {"name": "rootfs", "partition_number": None},
            ],
            2,
            id="gpt-position-based",
        ),
        pytest.param(
            "rootfs",
            [
                {"name": "efi", "partition_number": None},
                {"name": "rootfs", "partition_number": 5},
            ],
            5,
            id="gpt-explicit-number",
        ),
        pytest.param(
            "missing",
            [{"name": "efi", "partition_number": None}],
            None,
            id="not-found",
        ),
    ],
)
def test_part_num_gpt(name, structure_spec, expected):
    structure = []
    for spec in structure_spec:
        item = MagicMock(spec=GPTStructureItem)
        item.name = spec["name"]
        item.partition_number = spec["partition_number"]
        structure.append(item)

    assert _part_num(name, structure) == expected


def test_part_num_mbr_plain():
    structure = [
        MagicMock(spec=MBRStructureItem, partition_number=None) for _ in range(3)
    ]
    for i, name in enumerate(["boot", "data", "rootfs"]):
        structure[i].name = name

    assert _part_num("boot", structure) == 1
    assert _part_num("data", structure) == 2
    assert _part_num("rootfs", structure) == 3


def test_part_num_mbr_extended():
    structure = [
        MagicMock(spec=MBRStructureItem, partition_number=None) for _ in range(5)
    ]
    for i, name in enumerate(["boot", "p2", "p3", "logical1", "logical2"]):
        structure[i].name = name

    assert _part_num("boot", structure) == 1
    assert _part_num("p2", structure) == 2
    assert _part_num("p3", structure) == 3
    # slot 4 is the synthesised extended container — logical partitions start at 5
    assert _part_num("logical1", structure) == 5
    assert _part_num("logical2", structure) == 6
