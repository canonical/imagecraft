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

import fcntl
import subprocess
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from craft_application import ServiceFactory
from imagecraft.models import Project, Volume
from imagecraft.models.volume import GPTStructureItem, MBRVolume, PartitionSchema
from imagecraft.services.image import ImageService


@pytest.fixture
def image_service(default_factory: ServiceFactory):
    svc = cast(ImageService, default_factory.get("image"))
    yield svc
    # Prevent atexit handlers registered during tests from firing with real devices.
    svc._loop_devices.clear()


@pytest.fixture
def project_dir(image_service: ImageService):
    return image_service._project_dir


@pytest.fixture
def mock_project():
    vol = MagicMock(spec=Volume)
    vol.volume_schema = PartitionSchema.GPT
    vol.structure = [
        MagicMock(spec=GPTStructureItem, name="efi", partition_number=None),
        MagicMock(spec=GPTStructureItem, name="rootfs", partition_number=2),
    ]
    vol.structure[0].name = "efi"
    vol.structure[1].name = "rootfs"

    project = MagicMock(spec=Project)
    project.volumes = {"pc": vol}
    return project


def test_get_images_uninitialized(image_service):
    with pytest.raises(
        ValueError, match="Images must be created before they can be retrieved"
    ):
        image_service.get_images()


def test_create_images_success(
    image_service, default_factory, mock_project, project_dir, mocker
):
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )

    with patch("imagecraft.pack.gptutil.create_empty_gpt_image") as mock_create:
        images = image_service.create_images()

        expected_path = project_dir / ".pc.img.tmp"
        assert images == {"pc": expected_path}
        assert image_service.get_images() == {"pc": expected_path}
        mock_create.assert_called_once()


def test_create_images_mbr(image_service, default_factory, project_dir, mocker):
    mbr_vol = MBRVolume.unmarshal(
        {
            "schema": "mbr",
            "structure": [
                {
                    "name": "boot",
                    "role": "system-boot",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "256M",
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
    mock_project = MagicMock(spec=Project)
    mock_project.volumes = {"pi": mbr_vol}
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )

    with patch("imagecraft.pack.mbrutil.create_empty_mbr_image") as mock_create:
        images = image_service.create_images()

        expected_path = project_dir / ".pi.img.tmp"
        assert images == {"pi": expected_path}
        mock_create.assert_called_once()


def test_create_images_idempotent(image_service, default_factory, mock_project, mocker):
    project_service = default_factory.get("project")
    mock_get = mocker.patch.object(project_service, "get", return_value=mock_project)

    with patch("imagecraft.pack.gptutil.create_empty_gpt_image"):
        first_call = image_service.create_images()
        second_call = image_service.create_images()

        assert first_call is second_call
        mock_get.assert_called_once()  # Only called once


def test_attach_images_new(image_service, project_dir, mocker):
    image_service._images = {"pc": project_dir / ".pc.img.tmp"}

    mock_run = mocker.patch("imagecraft.services.image.run")
    # Mock _get_all_loop_devices returns empty
    mocker.patch.object(image_service, "_get_all_loop_devices", return_value=[])

    mock_run.return_value.stdout = "/dev/loop8\n"
    mock_flock = mocker.patch("fcntl.flock")
    mocker.patch("builtins.open", return_value=mocker.MagicMock())

    with patch("atexit.register") as mock_atexit:
        devices = image_service.attach_images()

        assert devices == {"pc": "/dev/loop8"}
        mock_run.assert_called_with(
            "losetup",
            "--find",
            "--show",
            "--partscan",
            str(project_dir / ".pc.img.tmp"),
        )
        mock_atexit.assert_called_once_with(image_service.detach_images)

    mock_flock.assert_called_once_with(mocker.ANY, fcntl.LOCK_SH)


def test_attach_images_reuse(image_service, project_dir, mocker):
    image_path = project_dir / ".pc.img.tmp"
    image_path.touch()
    image_service._images = {"pc": image_path}

    # Mock existing loop device
    mocker.patch.object(
        image_service,
        "_get_all_loop_devices",
        return_value=[{"name": "/dev/loop9", "back-file": str(image_path)}],
    )

    # Mock samefile to return True
    mocker.patch("pathlib.Path.samefile", return_value=True)
    mock_run = mocker.patch("imagecraft.services.image.run")
    mock_flock = mocker.patch("fcntl.flock")
    mocker.patch("builtins.open", return_value=mocker.MagicMock())

    devices = image_service.attach_images()

    assert devices == {"pc": "/dev/loop9"}
    mock_run.assert_not_called()  # Should not call losetup attach

    mock_flock.assert_called_once_with(mocker.ANY, fcntl.LOCK_SH)


def test_attach_images_stale_inode(image_service, project_dir, mocker):
    image_path = project_dir / ".pc.img.tmp"
    image_path.touch()
    image_service._images = {"pc": image_path}

    # Mock existing loop device
    mocker.patch.object(
        image_service,
        "_get_all_loop_devices",
        return_value=[{"name": "/dev/loop10", "back-file": str(image_path)}],
    )

    # Mock samefile to raise FileNotFoundError (stale inode)
    mocker.patch("pathlib.Path.samefile", side_effect=FileNotFoundError)
    mock_run = mocker.patch("imagecraft.services.image.run")
    mock_run.return_value.stdout = "/dev/loop11\n"
    mocker.patch("fcntl.flock")
    mocker.patch("builtins.open", return_value=mocker.MagicMock())

    devices = image_service.attach_images()

    assert devices == {"pc": "/dev/loop11"}
    # Should detach stale
    mock_run.assert_any_call("losetup", "-d", "/dev/loop10")
    # Should attach new
    mock_run.assert_any_call(
        "losetup", "--find", "--show", "--partscan", str(image_path)
    )


def test_attach_images_flock_sync_and_release(image_service, project_dir, mocker):
    """attach_images() acquires a shared flock briefly to sync with udev, then releases."""
    image_service._images = {"pc": project_dir / ".pc.img.tmp"}

    mocker.patch.object(image_service, "_get_all_loop_devices", return_value=[])
    mock_run = mocker.patch("imagecraft.services.image.run")
    mock_run.return_value.stdout = "/dev/loop8\n"
    mock_flock = mocker.patch("fcntl.flock")
    mock_fd = mocker.MagicMock()
    mock_fd.__enter__ = mocker.MagicMock(return_value=mock_fd)
    mock_fd.__exit__ = mocker.MagicMock(return_value=False)
    mocker.patch("builtins.open", return_value=mock_fd)

    with patch("atexit.register"):
        image_service.attach_images()

    # Flock was acquired
    mock_flock.assert_called_once_with(mock_fd, fcntl.LOCK_SH)
    # fd was closed (lock released) immediately via the context manager
    mock_fd.__exit__.assert_called_once()


def test_detach_images_success(image_service, mocker):
    image_service._loop_devices = {"pc": "/dev/loop8"}
    mock_run = mocker.patch("imagecraft.services.image.run")

    image_service.detach_images()

    mock_run.assert_called_once_with("losetup", "-d", "/dev/loop8")
    assert image_service._loop_devices == {}


def test_detach_images_retry(image_service, mocker):
    image_service._loop_devices = {"pc": "/dev/loop8"}
    mock_run = mocker.patch("imagecraft.services.image.run")

    # Fail twice, then succeed
    mock_run.side_effect = [
        subprocess.CalledProcessError(1, "losetup"),
        subprocess.CalledProcessError(1, "losetup"),
        MagicMock(),
    ]

    mocker.patch("time.monotonic", side_effect=[0, 1, 2, 3, 4])
    mocker.patch("time.sleep")

    image_service.detach_images()

    assert mock_run.call_count == 3
    assert image_service._loop_devices == {}


def test_get_loop_paths(image_service, default_factory, mock_project, mocker):
    image_service._loop_devices = {"pc": "/dev/loop8"}
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )

    mapping = image_service.get_loop_paths()

    assert mapping == {
        "pc": "/dev/loop8",
        "pc/efi": "/dev/loop8p1",
        "pc/rootfs": "/dev/loop8p2",
    }


def test_get_loop_paths_mbr_plain(image_service, default_factory, mocker):
    """MBR with ≤4 partitions: numbers are plain 1-based positions."""
    vol = MBRVolume.unmarshal(
        {
            "schema": "mbr",
            "structure": [
                {
                    "name": "boot",
                    "role": "system-boot",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "256M",
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
    mock_project = MagicMock(spec=Project)
    mock_project.volumes = {"pi": vol}
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )
    image_service._loop_devices = {"pi": "/dev/loop8"}

    mapping = image_service.get_loop_paths()

    assert mapping == {
        "pi": "/dev/loop8",
        "pi/boot": "/dev/loop8p1",
        "pi/rootfs": "/dev/loop8p2",
    }


def test_get_loop_paths_mbr_extended(image_service, default_factory, mocker):
    """MBR with >4 partitions: logical partitions start at 5, skipping slot 4."""
    vol = MBRVolume.unmarshal(
        {
            "schema": "mbr",
            "structure": [
                {
                    "name": "boot",
                    "role": "system-boot",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "256M",
                },
                {
                    "name": "p2",
                    "role": "system-boot",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "256M",
                },
                {
                    "name": "p3",
                    "role": "system-boot",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "256M",
                },
                {
                    "name": "logical1",
                    "role": "system-boot",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "256M",
                },
                {
                    "name": "logical2",
                    "role": "system-data",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "1G",
                },
            ],
        }
    )
    mock_project = MagicMock(spec=Project)
    mock_project.volumes = {"pi": vol}
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )
    image_service._loop_devices = {"pi": "/dev/loop8"}

    mapping = image_service.get_loop_paths()

    assert mapping == {
        "pi": "/dev/loop8",
        "pi/boot": "/dev/loop8p1",
        "pi/p2": "/dev/loop8p2",
        "pi/p3": "/dev/loop8p3",
        "pi/logical1": "/dev/loop8p5",
        "pi/logical2": "/dev/loop8p6",
    }


def test_verify_images_gpt(
    image_service, default_factory, mock_project, project_dir, mocker
):
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )
    image_service._images = {"pc": project_dir / ".pc.img.tmp"}

    with patch("imagecraft.pack.gptutil.verify_partition_tables") as mock_verify:
        image_service.verify_images()
        mock_verify.assert_called_once_with(project_dir / ".pc.img.tmp")


def test_verify_images_mbr(image_service, default_factory, project_dir, mocker):
    mbr_vol = MBRVolume.unmarshal(
        {
            "schema": "mbr",
            "structure": [
                {
                    "name": "boot",
                    "role": "system-boot",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "256M",
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
    mock_project = MagicMock(spec=Project)
    mock_project.volumes = {"pi": mbr_vol}
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )
    image_service._images = {"pi": project_dir / ".pi.img.tmp"}

    with patch("imagecraft.pack.mbrutil.verify_partition_tables") as mock_verify:
        image_service.verify_images()
        mock_verify.assert_called_once_with(project_dir / ".pi.img.tmp")


def test_finalize_images(image_service, project_dir, mocker):
    hidden = project_dir / ".pc.img.tmp"
    hidden.touch()
    image_service._images = {"pc": hidden}

    dest = project_dir / "dest"
    mock_move = mocker.patch("imagecraft.services.image.shutil.move")

    result = image_service.finalize_images(dest)

    final_path = dest / "pc.img"
    mock_move.assert_called_once_with(str(hidden), final_path)
    assert result == {"pc": final_path}
    assert dest.exists()


def test_finalize_images_multiple_volumes(image_service, project_dir, mocker):
    hidden_pc = project_dir / ".pc.img.tmp"
    hidden_rpi = project_dir / ".rpi.img.tmp"
    hidden_pc.touch()
    hidden_rpi.touch()
    image_service._images = {"pc": hidden_pc, "rpi": hidden_rpi}

    dest = project_dir / "dest"
    mock_move = mocker.patch("imagecraft.services.image.shutil.move")

    result = image_service.finalize_images(dest)

    mock_move.assert_any_call(str(hidden_pc), dest / "pc.img")
    mock_move.assert_any_call(str(hidden_rpi), dest / "rpi.img")
    assert mock_move.call_count == 2
    assert result == {"pc": dest / "pc.img", "rpi": dest / "rpi.img"}


def test_finalize_images_creates_dest(image_service, project_dir, mocker):
    hidden = project_dir / ".pc.img.tmp"
    image_service._images = {"pc": hidden}

    dest = project_dir / "nonexistent" / "nested" / "dest"
    mocker.patch("imagecraft.services.image.shutil.move")

    image_service.finalize_images(dest)

    assert dest.exists()
