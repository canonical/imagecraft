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

from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from craft_parts.filesystem_mounts import FilesystemMount
from craft_platforms import DebianArchitecture
from imagecraft.errors import ImageError
from imagecraft.models import Volume
from imagecraft.models.volume import (
    GPTStructureItem,
    GPTStructureList,
    GPTVolume,
    MBRStructureItem,
    MBRStructureList,
    MBRVolume,
)
from imagecraft.pack.grubutil import (
    _part_num,
    _partition_mounts,
    setup_grub,
)
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


@pytest.fixture
def mock_grub_mounts(mocker, new_dir):
    """Provide a standard set of mocks for the FUSE/ImageDevDir mounts in setup_grub."""
    dev_dir = Path(new_dir, "workdir", "dev")
    dev_dir.mkdir(parents=True)

    devices = {
        None: dev_dir / "pc.img",
        1: dev_dir / "pc.img1",
        2: dev_dir / "pc.img2",
        3: dev_dir / "pc.img3",
        "pc.img1": dev_dir / "pc.img1",
        "pc.img2": dev_dir / "pc.img2",
        "pc.img3": dev_dir / "pc.img3",
    }
    image_dev_dir = mocker.MagicMock()
    image_dev_dir.return_value.__enter__.return_value = devices
    mocker.patch("imagecraft.utils.mount.ImageDevDir", image_dev_dir)

    composite_cls = mocker.patch("imagecraft.utils.mount.CompositeMount")
    composite_cls.return_value.mount.return_value = Path(new_dir, "workdir", "mount")

    mocker.patch("imagecraft.pack.grubutil._partition_mounts", return_value=[])

    os_utils_mock = mocker.patch("imagecraft.pack.grubutil.os_utils")

    return mocker.MagicMock(
        image_dev_dir=image_dev_dir,
        composite_cls=composite_cls,
        os_utils=os_utils_mock,
        dev_dir=dev_dir,
        devices=devices,
    )


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
def test_setup_grub(mocker, new_dir, volume, filesystem_mount, mock_grub_mounts):
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(
        volume=volume,
        disk_path=disk_path,
    )
    workdir = Path(new_dir, "workdir")
    workdir.mkdir(exist_ok=True)
    mock_chroot = mocker.patch("imagecraft.pack.grubutil.Chroot")

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
    assert (
        mock_chroot.return_value.execute.call_args.kwargs["loop_dev"] == "/dev/pc.img"
    )

    chroot_mounts = mock_chroot.call_args.kwargs["mounts"]
    dev_bind_mount = next(
        (m for m in chroot_mounts if m._relative_mountpoint == "/dev"), None
    )
    assert dev_bind_mount is not None
    assert dev_bind_mount._fstype is None
    assert dev_bind_mount._src == str(mock_grub_mounts.dev_dir)


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
def test_setup_grub_partitions(
    mocker, new_dir, volume, arch, emitter, message, mock_grub_mounts
):
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
    workdir.mkdir(exist_ok=True)
    mock_chroot = mocker.patch("imagecraft.pack.grubutil.Chroot")

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
def test_setup_grub_mbr_bios(mocker, new_dir, arch, mock_grub_mounts):
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(volume=_MBR_VOLUME_WITH_BOOT, disk_path=disk_path)
    workdir = Path(new_dir, "workdir")
    workdir.mkdir(exist_ok=True)
    mock_chroot = mocker.patch("imagecraft.pack.grubutil.Chroot")
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
    assert (
        mock_chroot.return_value.execute.call_args.kwargs["loop_dev"] == "/dev/pc.img"
    )


@pytest.mark.parametrize(
    ("volume", "filesystem_mount", "expected_entries"),
    [
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
            FilesystemMount.unmarshal(
                [
                    {"mount": "/", "device": "(volume/pc/rootfs)"},
                    {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
                ]
            ),
            [
                ("/", "ext4"),
                ("/boot/efi", "vfat"),
            ],
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
            FilesystemMount.unmarshal(
                [
                    {"mount": "/", "device": "(volume/pc/rootfs)"},
                ]
            ),
            [
                ("/", "ext4"),
            ],
        ),
    ],
)
@pytest.mark.usefixtures("new_dir")
def test_partition_mounts(
    mocker,
    new_dir,
    volume: Volume,
    filesystem_mount: FilesystemMount,
    expected_entries: list[tuple[str, str]],
):
    mocker.patch("imagecraft.pack.grubutil.gptutil.get_partition_sector_offset")
    mocker.patch(
        "imagecraft.pack.grubutil.gptutil.get_partition_size_sectors",
        return_value=12345,
    )
    mount_partition_mock = mocker.patch(
        "imagecraft.utils.mount.mount_partition",
        side_effect=lambda *args, **kwargs: MagicMock(),
    )
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch()

    part_mounts = _partition_mounts(disk_path, volume.structure, filesystem_mount)

    assert len(part_mounts) == len(expected_entries)
    actual_mountpoints = [mp for mp, _ in part_mounts]
    expected_mountpoints = [mp for mp, _ in expected_entries]
    assert actual_mountpoints == expected_mountpoints
    assert mount_partition_mock.call_count == len(expected_entries)

    for (_, filesystem), call in zip(
        expected_entries, mount_partition_mock.call_args_list
    ):
        assert str(call.args[1].value).lower() == filesystem


@pytest.mark.parametrize(
    ("volume", "filesystem_mount"),
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
            FilesystemMount.unmarshal(
                [
                    {"mount": "/", "device": "(volume/pc/not-matching)"},
                ]
            ),
        ),
    ],
)
@pytest.mark.usefixtures("new_dir")
def test_partition_mounts_errors(
    new_dir,
    volume: Volume,
    filesystem_mount: FilesystemMount,
):
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch()

    with pytest.raises(ImageError, match="Cannot find a partition named"):
        _partition_mounts(disk_path, volume.structure, filesystem_mount)


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
    items = []
    for spec in structure_spec:
        item = MagicMock(spec=GPTStructureItem)
        item.name = spec["name"]
        item.partition_number = spec["partition_number"]
        items.append(item)
    structure = cast(GPTStructureList, items)

    assert _part_num(name, structure) == expected


def test_part_num_mbr_plain():
    structure = cast(
        MBRStructureList,
        [MagicMock(spec=MBRStructureItem, partition_number=None) for _ in range(3)],
    )
    for i, name in enumerate(["boot", "data", "rootfs"]):
        structure[i].name = name

    assert _part_num("boot", structure) == 1
    assert _part_num("data", structure) == 2
    assert _part_num("rootfs", structure) == 3


def test_part_num_mbr_extended():
    structure = cast(
        MBRStructureList,
        [MagicMock(spec=MBRStructureItem, partition_number=None) for _ in range(5)],
    )
    for i, name in enumerate(["boot", "p2", "p3", "logical1", "logical2"]):
        structure[i].name = name

    assert _part_num("boot", structure) == 1
    assert _part_num("p2", structure) == 2
    assert _part_num("p3", structure) == 3
    # slot 4 is the synthesised extended container — logical partitions start at 5
    assert _part_num("logical1", structure) == 5
    assert _part_num("logical2", structure) == 6
