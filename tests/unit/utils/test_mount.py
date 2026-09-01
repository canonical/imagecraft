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

import pytest
from imagecraft import errors
from imagecraft.models import GPTVolume, MBRVolume
from imagecraft.utils.mount import (
    BaseMount,
    CompositeMount,
    ExtFuseMount,
    FatFuseMount,
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


def test_mount_partition_factory(mocker, tmp_path: Path):
    img_path = tmp_path / "test.img"
    img_path.touch()

    ext_mount = mount_partition(img_path, "ext4", fakeroot=True)
    assert isinstance(ext_mount, ExtFuseMount)
    assert ext_mount.offset == 0
    assert ext_mount.fakeroot is True

    mocker.patch(
        "imagecraft.pack.gptutil.get_partition_sector_offset_by_number",
        return_value=2048,
    )
    mocker.patch(
        "imagecraft.pack.gptutil.get_partition_size_sectors_by_number",
        return_value=65536,
    )
    fat_mount = mount_partition(img_path, "vfat", partition=2)
    assert isinstance(fat_mount, FatFuseMount)
    assert fat_mount.offset == 2048 * 512
    assert fat_mount.size == 65536 * 512

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
        "imagecraft.pack.gptutil.get_partition_sector_offset_by_number",
        side_effect=lambda _, num: 2048 if num == 1 else 526336,
    )
    mocker.patch(
        "imagecraft.pack.gptutil.get_partition_size_sectors_by_number",
        side_effect=lambda _, num: 524288 if num == 1 else 8388608,
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


def test_mount_volume_mbr_extended_partition_numbering(mocker, tmp_path: Path):
    """Logical partitions (5+) must resolve their on-disk numbers, not positions."""
    volume = MBRVolume.unmarshal(
        {
            "schema": "mbr",
            "structure": [
                {
                    "name": name,
                    "role": "system-data",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "1G",
                }
                for name in ["p1", "p2", "p3", "p4", "p5"]
            ],
        }
    )
    disk_path = tmp_path / "disk.img"
    disk_path.touch()

    offset_mock = mocker.patch(
        "imagecraft.pack.gptutil.get_partition_sector_offset_by_number",
        return_value=2048,
    )
    mocker.patch(
        "imagecraft.pack.gptutil.get_partition_size_sectors_by_number",
        return_value=2097152,
    )

    vol_mount = mount_volume(volume, disk_path)

    # The 4th and 5th structure items are logical partitions 5 and 6: slot 4
    # is reserved for the extended container.
    assert [c.args[1] for c in offset_mock.call_args_list] == [1, 2, 3, 5, 6]
    assert len(vol_mount._mount_entries) == 5
