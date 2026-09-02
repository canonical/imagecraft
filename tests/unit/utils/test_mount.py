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

import subprocess
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest
from imagecraft import errors
from imagecraft.models import GPTVolume, MBRVolume
from imagecraft.utils.mount import (
    BaseMount,
    CompositeMount,
    ExtFuseMount,
    FatFuseMount,
    ImageDevDir,
    VirtualOffsetDevice,
    mount_partition,
    mount_volume,
)


@pytest.fixture
def mock_run(mocker):
    return mocker.patch(
        "imagecraft.utils.mount.run",
        return_value=CompletedProcess(args=[], returncode=0, stdout=""),
    )


@pytest.fixture
def gpt_volume():
    return GPTVolume.unmarshal(
        {
            "schema": "gpt",
            "structure": [
                {
                    "name": "efi",
                    "role": "system-boot",
                    "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                    "filesystem": "vfat",
                    "size": "256M",
                },
                {
                    "name": "rootfs",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "4G",
                },
            ],
        }
    )


@pytest.fixture
def mbr_volume():
    return MBRVolume.unmarshal(
        {
            "schema": "mbr",
            "structure": [
                {
                    "name": "ubuntu-seed",
                    "role": "system-boot",
                    "type": "0C",
                    "filesystem": "vfat",
                    "size": "1200M",
                },
                {
                    "name": "ubuntu-data",
                    "role": "system-data",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "2G",
                },
            ],
        }
    )


def test_virtual_offset_device_mount_success(mock_run, tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    disk_path.touch()
    vdev = VirtualOffsetDevice(disk_path, offset=1048576, size=67108864)

    assert not vdev.is_mounted
    part_file = vdev.mount()

    assert vdev.is_mounted
    assert part_file.name == "part.img"
    assert part_file.exists()
    mock_run.assert_called_once_with(
        "fusefile",
        str(part_file),
        f"{disk_path.resolve()}/1048576+67108864",
    )

    assert vdev.mount() == part_file
    assert mock_run.call_count == 1

    vdev.unmount()
    assert not vdev.is_mounted
    mock_run.assert_called_with("fusermount", "-u", str(part_file))


def test_virtual_offset_device_mount_failure(mock_run, tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    mock_run.side_effect = subprocess.CalledProcessError(1, "fusefile")
    vdev = VirtualOffsetDevice(disk_path, offset=1048576, size=67108864)

    with pytest.raises(
        errors.MountError, match="Failed to create virtual offset device"
    ):
        vdev.mount()

    assert not vdev.is_mounted
    assert vdev.part_file is None


def test_virtual_offset_device_unmount_lazy(mock_run, tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    vdev = VirtualOffsetDevice(disk_path, offset=1048576, size=67108864)
    part_file = vdev.mount()

    vdev.unmount(lazy=True)
    assert not vdev.is_mounted
    mock_run.assert_called_with("fusermount", "-u", "-z", str(part_file))


def test_virtual_offset_device_unmount_not_mounted(mock_run, tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    vdev = VirtualOffsetDevice(disk_path, offset=1048576, size=67108864)
    vdev.unmount()
    mock_run.assert_not_called()


def test_virtual_offset_device_context_manager(mock_run, tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    vdev = VirtualOffsetDevice(disk_path, offset=1048576, size=67108864)

    with vdev as part_file:
        assert vdev.is_mounted
        assert part_file.name == "part.img"

    assert not vdev.is_mounted
    mock_run.assert_called_with("fusermount", "-u", str(part_file))


def test_ext_fuse_mount_standalone(mock_run, tmp_path: Path):
    img_path = tmp_path / "rootfs.img"
    mount = ExtFuseMount(img_path)

    assert not mount.is_mounted
    mountpoint = mount.mount()

    assert mount.is_mounted
    assert mountpoint.exists()
    mock_run.assert_called_once_with(
        "fuse2fs",
        "-o",
        "rw",
        str(img_path.resolve()),
        str(mountpoint.resolve()),
    )

    mount.unmount()
    assert not mount.is_mounted
    mock_run.assert_called_with("fusermount3", "-u", str(mountpoint.resolve()))


def test_ext_fuse_mount_with_offset_and_options(mock_run, tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    custom_mount = tmp_path / "custom_mount"
    mount = ExtFuseMount(
        disk_path,
        offset=1048576,
        mountpoint=custom_mount,
        read_only=True,
        allow_other=True,
        fakeroot=True,
    )

    mountpoint = mount.mount()
    assert mountpoint == custom_mount
    mock_run.assert_called_once_with(
        "fuse2fs",
        "-o",
        "offset=1048576,ro,allow_other,fakeroot",
        str(disk_path.resolve()),
        str(custom_mount.resolve()),
    )

    mount.unmount(lazy=True)
    mock_run.assert_called_with("fusermount3", "-u", "-z", str(custom_mount.resolve()))


def test_ext_fuse_mount_failure(mock_run, tmp_path: Path):
    img_path = tmp_path / "rootfs.img"
    mock_run.side_effect = subprocess.CalledProcessError(1, "fuse2fs")
    mount = ExtFuseMount(img_path)

    with pytest.raises(errors.MountError) as exc_info:
        mount.mount()

    assert "Failed to mount ext partition" in str(exc_info.value)
    assert "at None" not in str(exc_info.value)
    assert not mount.is_mounted


def test_ext_fuse_mount_context_manager(mock_run, tmp_path: Path):
    img_path = tmp_path / "rootfs.img"
    mount = ExtFuseMount(img_path)

    with mount as mnt:
        assert mount.is_mounted
        assert mnt.exists()

    assert not mount.is_mounted


def test_fat_fuse_mount_standalone(mock_run, tmp_path: Path):
    img_path = tmp_path / "efi.img"
    mount = FatFuseMount(img_path)

    assert not mount.is_mounted
    mountpoint = mount.mount()

    assert mount.is_mounted
    assert mountpoint.exists()
    mock_run.assert_called_once_with(
        "fusefat",
        "-o",
        "rw+",
        str(img_path.resolve()),
        str(mountpoint.resolve()),
    )

    mount.unmount()
    assert not mount.is_mounted
    mock_run.assert_called_with("fusermount3", "-u", str(mountpoint.resolve()))


def test_fat_fuse_mount_with_offset_spawns_vdev(mock_run, tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    mount = FatFuseMount(
        disk_path,
        offset=1048576,
        size=67108864,
        read_only=True,
        allow_other=True,
    )

    mount.mount()
    assert mount.is_mounted
    assert mount._vpart is not None
    assert mount._vpart.is_mounted

    assert mock_run.call_count == 2
    fusefile_call, fusefat_call = mock_run.call_args_list
    assert fusefile_call[0][0] == "fusefile"
    assert fusefat_call[0][0] == "fusefat"
    assert fusefat_call[0][1] == "-o"
    assert fusefat_call[0][2] == "ro,allow_other"

    mount.unmount()
    assert not mount.is_mounted
    assert mock_run.call_count == 4
    unmount_fat, unmount_vpart = mock_run.call_args_list[2:]
    assert unmount_fat[0][0] == "fusermount3"
    assert unmount_vpart[0][0] == "fusermount"


def test_fat_fuse_mount_offset_missing_size_raises(tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    mount = FatFuseMount(disk_path, offset=1048576, size=None)

    with pytest.raises(errors.MountError, match="Partition size must be specified"):
        mount.mount()


def test_fat_fuse_mount_failure_cleans_up_vdev(mock_run, tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    mock_run.side_effect = [
        CompletedProcess(args=[], returncode=0, stdout=""),
        subprocess.CalledProcessError(1, "fusefat"),
        CompletedProcess(args=[], returncode=0, stdout=""),
    ]
    mount = FatFuseMount(disk_path, offset=1048576, size=67108864)

    with pytest.raises(errors.MountError) as exc_info:
        mount.mount()

    assert "Failed to mount FAT partition" in str(exc_info.value)
    assert "at None" not in str(exc_info.value)
    assert not mount.is_mounted
    assert mount._vpart is None
    assert mock_run.call_count == 3
    assert mock_run.call_args_list[2][0][0] == "fusermount"


def test_mount_partition_factory(tmp_path: Path):
    img_path = tmp_path / "test.img"

    ext_mount = mount_partition(img_path, "ext4", offset=100, fakeroot=True)
    assert isinstance(ext_mount, ExtFuseMount)
    assert ext_mount.offset == 100
    assert ext_mount.fakeroot is True

    fat_mount = mount_partition(img_path, "vfat", offset=200, size=300)
    assert isinstance(fat_mount, FatFuseMount)
    assert fat_mount.offset == 200
    assert fat_mount.size == 300

    with pytest.raises(errors.MountError, match="Unsupported filesystem"):
        mount_partition(img_path, "ntfs")


def test_composite_mount_and_unmount_order(mocker, tmp_path: Path):
    mount_a = mocker.MagicMock(spec=BaseMount)
    mount_b = mocker.MagicMock(spec=BaseMount)
    call_sequence: list[str] = []

    mount_a.mount.side_effect = lambda: call_sequence.append("mount_a")
    mount_b.mount.side_effect = lambda: call_sequence.append("mount_b")
    mount_a.unmount.side_effect = lambda **_: call_sequence.append("unmount_a")
    mount_b.unmount.side_effect = lambda **_: call_sequence.append("unmount_b")

    composite = CompositeMount(
        [
            ("boot/efi", mount_b),
            ("", mount_a),
        ],
        mountpoint=tmp_path / "rootfs",
    )

    root = composite.mount()
    assert root == tmp_path / "rootfs"
    assert composite.is_mounted

    composite.unmount()
    assert not composite.is_mounted

    assert call_sequence == ["mount_a", "mount_b", "unmount_b", "unmount_a"]


def test_composite_mount_failure_rolls_back(mocker, tmp_path: Path):
    mount_a = mocker.MagicMock(spec=BaseMount)
    mount_b = mocker.MagicMock(spec=BaseMount)
    mount_b.mount.side_effect = errors.MountError("Failed B")

    composite = CompositeMount(
        [
            ("", mount_a),
            ("boot/efi", mount_b),
        ],
        mountpoint=tmp_path / "rootfs",
    )

    with pytest.raises(
        errors.MountError,
        match="Failed to mount composite mount hierarchy",
    ):
        composite.mount()

    assert not composite.is_mounted
    mount_a.unmount.assert_called_once()


def test_mount_volume_gpt(mocker, gpt_volume, tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    disk_path.touch()

    mocker.patch(
        "imagecraft.pack.gptutil.get_partition_sector_offset",
        side_effect=lambda _, name: 2048 if name == "efi" else 526336,
    )
    mocker.patch(
        "imagecraft.pack.gptutil.get_partition_size_sectors",
        side_effect=lambda _, name: 524288 if name == "efi" else 8388608,
    )

    vol_mount = mount_volume(gpt_volume, disk_path, fakeroot=True)

    assert len(vol_mount._mount_entries) == 2
    paths_and_mounts = {p: type(m) for p, m in vol_mount._mount_entries}
    assert paths_and_mounts == {
        "boot/efi": FatFuseMount,
        "": ExtFuseMount,
    }
    ext_m = next(m for p, m in vol_mount._mount_entries if p == "")
    assert isinstance(ext_m, ExtFuseMount)
    assert ext_m.fakeroot is True


def test_mount_volume_mbr(mocker, mbr_volume, tmp_path: Path):
    disk_path = tmp_path / "disk.img"
    disk_path.touch()

    mocker.patch(
        "imagecraft.pack.gptutil.get_partition_sector_offset_by_number",
        side_effect=lambda _, num: 2048 if num == 1 else 2459648,
    )
    mocker.patch(
        "imagecraft.pack.gptutil.get_partition_size_sectors_by_number",
        side_effect=lambda _, num: 2457600 if num == 1 else 4194304,
    )

    vol_mount = mount_volume(
        mbr_volume,
        disk_path,
        mountpoint_overrides={"ubuntu-seed": "seed"},
    )

    assert len(vol_mount._mount_entries) == 2
    paths_and_mounts = {p: type(m) for p, m in vol_mount._mount_entries}
    assert paths_and_mounts == {
        "seed": FatFuseMount,
        "": ExtFuseMount,
    }


SECTOR_SIZE = 512
PART_TABLE = {
    "device": "/dev/loop0",
    "sectorsize": SECTOR_SIZE,
    "partitions": [
        {"node": "/dev/loop0p1", "start": 2048, "size": 65536},
        {"node": "/dev/loop0p2", "start": 67584, "size": 131072},
    ],
}


@pytest.fixture
def mock_partition_table(mocker):
    return mocker.patch(
        "imagecraft.pack.gptutil.get_partition_table",
        return_value=PART_TABLE,
    )


@pytest.fixture
def mock_which(mocker):
    return mocker.patch(
        "imagecraft.utils.mount.shutil.which",
        side_effect=lambda cmd: f"/usr/bin/{cmd}",
    )


@pytest.fixture
def dev_dir(tmp_path: Path) -> Path:
    path = tmp_path / "dev"
    path.mkdir()
    return path


@pytest.fixture
def image_path(tmp_path: Path) -> Path:
    path = tmp_path / "disk.img"
    path.touch()
    return path


def _assert_image_dev_dir_cleaned_up(
    devdir: ImageDevDir, dev_dir: Path, *, expect_partition_table_empty: bool = True
) -> None:
    """Assert that an ImageDevDir instance is fully unmounted and cleaned up."""
    assert not devdir.is_mounted
    assert devdir._devices is None
    if expect_partition_table_empty:
        assert devdir.partition_table is None
    assert list(dev_dir.iterdir()) == []


def test_image_dev_dir_mount(
    mock_run, mock_partition_table, image_path: Path, dev_dir: Path
):
    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)
    assert not devdir.is_mounted

    devices = devdir.mount()

    assert devdir.is_mounted
    assert devices[None] == dev_dir / "loop0"
    assert devices[1] == dev_dir / "loop0p1"
    assert devices[2] == dev_dir / "loop0p2"
    # Partitions are addressable by both number and node name.
    assert devices["loop0p1"] == devices[1]
    assert devices["loop0p2"] == devices[2]
    assert all(path.exists() for path in devices.values())

    assert [call.args for call in mock_run.call_args_list] == [
        ("mount", "--bind", str(image_path), str(dev_dir / "loop0")),
        (
            "fusefile",
            str(dev_dir / "loop0p1"),
            f"{image_path}/{2048 * SECTOR_SIZE}+{65536 * SECTOR_SIZE}",
        ),
        (
            "fusefile",
            str(dev_dir / "loop0p2"),
            f"{image_path}/{67584 * SECTOR_SIZE}+{131072 * SECTOR_SIZE}",
        ),
    ]


def test_image_dev_dir_mount_twice_raises(
    mock_run, mock_partition_table, image_path: Path, dev_dir: Path
):
    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)
    devdir.mount()

    with pytest.raises(errors.MountError, match="already mounted"):
        devdir.mount()


def test_image_dev_dir_unmount_not_mounted_raises(
    mock_run, image_path: Path, dev_dir: Path
):
    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)

    with pytest.raises(errors.MountError, match="Not mounted"):
        devdir.unmount()
    mock_run.assert_not_called()


def test_image_dev_dir_unmount_removes_created_devices(
    mock_run, mock_which, mock_partition_table, image_path: Path, dev_dir: Path
):
    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)
    devices = devdir.mount()
    created = set(devices.values())

    devdir.unmount()

    _assert_image_dev_dir_cleaned_up(
        devdir, dev_dir, expect_partition_table_empty=False
    )
    assert all(not path.exists() for path in created)
    unmounted = {
        call.args[2]
        for call in mock_run.call_args_list
        if call.args[0] == "fusermount3"
    }
    assert unmounted == {str(path.resolve()) for path in created}


def test_image_dev_dir_unmount_keeps_preexisting_devices(
    mock_run, mock_which, mock_partition_table, image_path: Path, dev_dir: Path
):
    preexisting = dev_dir / "loop0p1"
    preexisting.touch()

    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)
    devdir.mount()
    devdir.unmount()

    assert preexisting.exists()
    assert list(dev_dir.iterdir()) == [preexisting]


def test_image_dev_dir_remount_after_unmount(
    mock_run, mock_which, mock_partition_table, image_path: Path, dev_dir: Path
):
    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)
    first = dict(devdir.mount())
    devdir.unmount()

    assert devdir._devices is None
    assert devdir.partition_table is None

    second = devdir.mount()

    assert devdir.is_mounted
    assert second == first


def test_image_dev_dir_context_manager(
    mock_run, mock_which, mock_partition_table, image_path: Path, dev_dir: Path
):
    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)

    with devdir as devices:
        assert devdir.is_mounted
        assert set(devices) == {None, 1, 2, "loop0p1", "loop0p2"}

    _assert_image_dev_dir_cleaned_up(devdir, dev_dir)


@pytest.mark.parametrize(
    ("scenario", "side_effect", "match"),
    [
        pytest.param(
            "bind_mount_fails",
            subprocess.CalledProcessError(1, "fusefile"),
            "Error bind-mounting",
            id="bind_mount_fails",
        ),
        pytest.param(
            "partition_2_fails",
            None,
            "Error mounting partition 2",
            id="partition_2_fails",
        ),
    ],
)
def test_image_dev_dir_mount_failure_propagates(
    mock_run,
    mock_partition_table,
    image_path: Path,
    dev_dir: Path,
    scenario: str,
    side_effect: Any,
    match: str,
):
    if side_effect is None:
        failing_fragment = f"{image_path}/{67584 * SECTOR_SIZE}+{131072 * SECTOR_SIZE}"

        def _side_effect(*args, **kwargs):
            if args[0] == "fusefile" and args[2] == failing_fragment:
                raise subprocess.CalledProcessError(1, "fusefile")
            return CompletedProcess(args=list(args), returncode=0, stdout="")

        mock_run.side_effect = _side_effect
    else:
        mock_run.side_effect = side_effect

    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)
    assert devdir.is_mounted is False

    with pytest.raises(errors.MountError, match=match):
        devdir.mount()

    _assert_image_dev_dir_cleaned_up(devdir, dev_dir)

    if scenario == "partition_2_fails":
        unmounted = {
            call.args[-1]
            for call in mock_run.call_args_list
            if call.args[0] in ("fusermount3", "fusermount", "umount")
        }
        created = {dev_dir / "loop0", dev_dir / "loop0p1", dev_dir / "loop0p2"}
        assert unmounted == {str(path.resolve()) for path in created}


def test_image_dev_dir_unmount_failure_continues_cleanup(
    mock_run, mock_partition_table, image_path: Path, dev_dir: Path
):
    failing_unmount_path = str((dev_dir / "loop0p2").resolve())

    def _side_effect(*args, **kwargs):
        if (
            args[0] in ("fusermount3", "fusermount", "umount")
            and args[-1] == failing_unmount_path
        ):
            raise subprocess.CalledProcessError(1, args[0])
        return CompletedProcess(args=list(args), returncode=0, stdout="")

    mock_run.side_effect = _side_effect
    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)
    devices = devdir.mount()
    created = set(devices.values())

    with pytest.raises(errors.MountError, match="Errors occurred while unmounting"):
        devdir.unmount()

    _assert_image_dev_dir_cleaned_up(devdir, dev_dir)
    unmounted = {
        call.args[-1]
        for call in mock_run.call_args_list
        if call.args[0] in ("fusermount3", "fusermount", "umount")
    }
    assert unmounted == {str(path.resolve()) for path in created}


def test_image_dev_dir_mount_empty_partition_table(
    mock_partition_table, mock_run, image_path: Path, dev_dir: Path
):
    mock_partition_table.return_value = {
        "device": "/dev/loop0",
        "sectorsize": SECTOR_SIZE,
        "partitions": [],
    }
    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)

    devices = devdir.mount()

    assert devices == {None: dev_dir / "loop0"}
    mock_run.assert_called_once_with(
        "mount", "--bind", str(image_path), str(dev_dir / "loop0")
    )
    assert devdir.is_mounted


def test_image_dev_dir_context_manager_exception_still_unmounts(
    mock_run, mock_which, mock_partition_table, image_path: Path, dev_dir: Path
):
    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)

    def _raise_inside_context() -> None:
        with devdir as devices:
            assert devdir.is_mounted
            assert devices is not None
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        _raise_inside_context()

    _assert_image_dev_dir_cleaned_up(devdir, dev_dir)


def test_image_dev_dir_mount_preexisting_directory_fails_cleanly(
    mock_run, mock_partition_table, image_path: Path, dev_dir: Path
):
    (dev_dir / "loop0p1").mkdir()
    devdir = ImageDevDir(image_path=image_path, dev_dir=dev_dir)

    with pytest.raises(errors.MountError, match="Error creating device file"):
        devdir.mount()

    assert not devdir.is_mounted
    assert (dev_dir / "loop0p1").exists()
    assert (dev_dir / "loop0p1").is_dir()


def test_image_dev_dir_multiple_images_same_dev_dir(
    mock_run, mock_partition_table, image_path: Path, dev_dir: Path
):
    def make_partition_table(device: str) -> dict[str, Any]:
        return {
            "device": device,
            "sectorsize": SECTOR_SIZE,
            "partitions": [
                {"node": f"{device}p1", "start": 2048, "size": 65536},
            ],
        }

    mock_partition_table.side_effect = [
        make_partition_table("/dev/loop0"),
        make_partition_table("/dev/loop1"),
    ]
    image_path_2 = image_path.parent / "disk2.img"
    image_path_2.touch()

    devdir_a = ImageDevDir(image_path=image_path, dev_dir=dev_dir)
    devdir_b = ImageDevDir(image_path=image_path_2, dev_dir=dev_dir)

    devices_a = devdir_a.mount()
    devices_b = devdir_b.mount()

    assert devdir_a.is_mounted
    assert devdir_b.is_mounted
    assert {devices_a[None].name, devices_b[None].name} == {"loop0", "loop1"}
    assert devices_a[1] == devices_a["loop0p1"] == dev_dir / "loop0p1"
    assert devices_b[1] == devices_b["loop1p1"] == dev_dir / "loop1p1"

    devdir_a.unmount()
    devdir_b.unmount()
    assert list(dev_dir.iterdir()) == []
