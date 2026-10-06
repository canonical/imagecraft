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
from unittest.mock import call as mocker_call

import pytest
from imagecraft import errors
from imagecraft.models import GPTVolume, MBRVolume
from imagecraft.utils.mount import (
    BaseMount,
    CompositeMount,
    ExtFuseMount,
    FatFuseMount,
    VirtualDeviceManager,
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


@pytest.fixture
def offset_device(mock_run, tmp_path: Path) -> VirtualOffsetDevice:
    """A VirtualOffsetDevice over a 1 MiB offset, 64 MiB slice."""
    disk_path = tmp_path / "disk.img"
    disk_path.touch()
    return VirtualOffsetDevice(disk_path, offset=1048576, size=67108864)


def test_virtual_offset_device_mount_success(offset_device, mock_run, tmp_path: Path):
    vdev = offset_device

    assert not vdev.is_mounted
    part_file = vdev.mount()

    assert vdev.is_mounted
    assert part_file.name == "part.img"
    assert part_file.exists()
    mock_run.assert_called_once_with(
        "fusefile",
        str(part_file),
        f"{vdev.disk_path.resolve()}/1048576+67108864",
    )

    assert vdev.mount() == part_file
    assert mock_run.call_count == 1

    vdev.unmount()
    assert not vdev.is_mounted
    mock_run.assert_called_with("fusermount", "-u", str(part_file))


def test_virtual_offset_device_mount_failure(offset_device, mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(1, "fusefile")

    with pytest.raises(
        errors.MountError, match="Failed to create virtual offset device"
    ):
        offset_device.mount()

    assert not offset_device.is_mounted
    assert offset_device.part_file is None


def test_virtual_offset_device_unmount_lazy(offset_device, mock_run):
    part_file = offset_device.mount()

    offset_device.unmount(lazy=True)
    assert not offset_device.is_mounted
    mock_run.assert_called_with("fusermount", "-u", "-z", str(part_file))


def test_virtual_offset_device_unmount_not_mounted(offset_device, mock_run):
    offset_device.unmount()
    mock_run.assert_not_called()


def test_virtual_offset_device_context_manager(offset_device, mock_run):
    with offset_device as part_file:
        assert offset_device.is_mounted
        assert part_file.name == "part.img"

    assert not offset_device.is_mounted
    mock_run.assert_called_with("fusermount", "-u", str(part_file))


SLICES = {"pc_efi": (1048576, 524288), "pc_rootfs": (1048576 + 524288, 1048576)}


@pytest.fixture
def vdev_manager(mock_run, tmp_path: Path):
    disk_path = tmp_path / "pc.img"
    disk_path.touch()
    return VirtualDeviceManager(disk_path, SLICES, tmp_path / ".devices")


def test_virtual_device_manager_mount(vdev_manager, mock_run, tmp_path: Path):
    devices = vdev_manager.mount()

    assert devices == {
        "pc_efi": tmp_path / ".devices" / "pc_efi.img",
        "pc_rootfs": tmp_path / ".devices" / "pc_rootfs.img",
    }
    for part_file in devices.values():
        assert part_file.is_file()
    assert mock_run.call_args_list == [
        mocker_call(
            "fusefile", str(devices["pc_efi"]), f"{tmp_path}/pc.img/1048576+524288"
        ),
        mocker_call(
            "fusefile",
            str(devices["pc_rootfs"]),
            f"{tmp_path}/pc.img/1572864+1048576",
        ),
    ]

    # Idempotent: an already mounted manager does not mount again.
    assert vdev_manager.mount() == devices
    assert mock_run.call_count == 2


@pytest.mark.parametrize(
    ("lazy", "call_prefix"),
    [
        pytest.param(False, ("fusermount", "-u"), id="normal"),
        pytest.param(True, ("fusermount", "-u", "-z"), id="lazy"),
    ],
)
def test_virtual_device_manager_unmount(
    vdev_manager, mock_run, tmp_path: Path, *, lazy: bool, call_prefix: tuple[str, ...]
):
    devices = vdev_manager.mount()

    vdev_manager.unmount(lazy=lazy)

    for part_file in devices.values():
        mock_run.assert_any_call(*call_prefix, str(part_file))
    assert not (tmp_path / ".devices").exists()


def test_virtual_device_manager_unmount_not_mounted(vdev_manager, mock_run):
    vdev_manager.unmount()
    mock_run.assert_not_called()


def test_virtual_device_manager_mount_failure_rolls_back(
    vdev_manager, mock_run, tmp_path: Path
):
    mock_run.side_effect = [
        CompletedProcess(args=[], returncode=0, stdout=""),
        subprocess.CalledProcessError(1, "fusefile"),
        CompletedProcess(args=[], returncode=0, stdout=""),
    ]

    with pytest.raises(errors.MountError, match="Failed to create virtual device"):
        vdev_manager.mount()

    # The device that did mount is unmounted, and no files are left behind.
    mock_run.assert_called_with(
        "fusermount", "-u", str(tmp_path / ".devices/pc_efi.img")
    )
    assert not (tmp_path / ".devices").exists()


def test_virtual_device_manager_unmount_reports_errors(mocker, vdev_manager, mock_run):
    devices = vdev_manager.mount()
    mocker.patch("imagecraft.utils.mount.time.sleep")  # don't wait out the retries
    mock_run.side_effect = subprocess.CalledProcessError(1, "fusermount")

    with pytest.raises(
        errors.MountError, match="Errors occurred during virtual device"
    ):
        vdev_manager.unmount()

    # Every device is attempted, but failed mounts and directory are retained.
    commands = [args for args, _ in mock_run.call_args_list]
    for part_file in devices.values():
        assert ("fusermount", "-u", str(part_file)) in commands
        assert part_file.is_file()
    assert vdev_manager.devices == devices
    assert vdev_manager.target_dir.exists()


def test_virtual_device_manager_unmount_shared_target_dir(mock_run, tmp_path: Path):
    target_dir = tmp_path / ".devices"
    disk1 = tmp_path / "d1.img"
    disk2 = tmp_path / "d2.img"
    disk1.touch()
    disk2.touch()

    vdev1 = VirtualDeviceManager(disk1, {"vol1_part": (0, 1024)}, target_dir)
    vdev2 = VirtualDeviceManager(disk2, {"vol2_part": (0, 1024)}, target_dir)

    devs1 = vdev1.mount()
    devs2 = vdev2.mount()

    assert devs1["vol1_part"].is_file()
    assert devs2["vol2_part"].is_file()

    # Unmounting vdev1 removes only its own file; vdev2's file and dir remain.
    vdev1.unmount()
    assert not devs1["vol1_part"].exists()
    assert devs2["vol2_part"].is_file()
    assert target_dir.exists()

    # Unmounting vdev2 removes its file and now cleans up the empty target_dir.
    vdev2.unmount()
    assert not devs2["vol2_part"].exists()
    assert not target_dir.exists()


def test_virtual_device_manager_unmount_partial_failure_retry(
    mocker, vdev_manager, mock_run, tmp_path: Path
):
    devices = vdev_manager.mount()
    mocker.patch("imagecraft.utils.mount.time.sleep")

    # First unmount: pc_efi succeeds, pc_rootfs fails
    def mock_fusermount(*args, **kwargs):
        if str(devices["pc_rootfs"]) in args:
            raise subprocess.CalledProcessError(1, "fusermount")
        return CompletedProcess(args=args, returncode=0, stdout="")

    mock_run.side_effect = mock_fusermount

    with pytest.raises(errors.MountError):
        vdev_manager.unmount()

    assert not devices["pc_efi"].exists()
    assert devices["pc_rootfs"].is_file()
    assert set(vdev_manager.devices) == {"pc_rootfs"}
    assert (tmp_path / ".devices").exists()

    # Retry unmount: now pc_rootfs succeeds
    mock_run.side_effect = None
    mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="")
    vdev_manager.unmount()

    assert not devices["pc_rootfs"].exists()
    assert vdev_manager.devices == {}
    assert not (tmp_path / ".devices").exists()


def test_virtual_device_manager_context_manager(vdev_manager, mock_run, tmp_path: Path):
    with vdev_manager as devices:
        assert (tmp_path / ".devices/pc_efi.img").is_file()
        assert set(devices) == set(SLICES)

    assert not (tmp_path / ".devices").exists()
    mock_run.assert_any_call("fusermount", "-u", str(devices["pc_efi"]))


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
