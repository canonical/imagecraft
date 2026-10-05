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
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from craft_application import ServiceFactory
from imagecraft import errors
from imagecraft.models import Project, Volume
from imagecraft.models.volume import GPTStructureItem, MBRVolume, PartitionSchema
from imagecraft.services.image import ImageService


@pytest.fixture
def image_service(default_factory: ServiceFactory):
    svc = cast(ImageService, default_factory.get("image"))
    yield svc
    # Prevent atexit handlers registered during tests from firing with real devices.
    for vdev in svc._vdev_managers.values():
        with contextlib.suppress(Exception):
            vdev.unmount()
    svc._vdev_managers.clear()


@pytest.fixture
def project_dir(image_service: ImageService):
    return image_service._project_dir


@pytest.fixture
def attachable(
    image_service, default_factory, mock_project, project_dir, mocker
) -> MagicMock:
    """ImageService with one image created and the virtual devices mocked out.

    Yields the ``VirtualDeviceManager`` mock so tests can set ``mount()``'s
    return value or side effect.
    """
    image_service._images = {"pc": project_dir / ".pc.img.tmp"}
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )
    mocker.patch(
        "imagecraft.pack.gptutil.get_partition_slices",
        return_value={"efi": (1048576, 524288), "rootfs": (1572864, 1073741824)},
    )
    mock_vdev = mocker.patch(
        "imagecraft.services.image.VirtualDeviceManager", autospec=True
    )
    mock_vdev.return_value.mount.return_value = {
        "pc_efi": project_dir / ".devices" / "pc_efi.img",
        "pc_rootfs": project_dir / ".devices" / "pc_rootfs.img",
    }
    return mock_vdev


@pytest.fixture
def mock_project():
    vol = MagicMock(spec=Volume)
    vol.volume_schema = PartitionSchema.GPT
    vol.structure = [
        MagicMock(spec=GPTStructureItem, name="efi", number=None),
        MagicMock(spec=GPTStructureItem, name="rootfs", number=2),
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


def test_attach_images_new(attachable, image_service, project_dir, mocker):
    with patch("atexit.register") as mock_atexit:
        image_service.attach_images()

    assert list(image_service._vdev_managers) == ["pc"]
    attachable.assert_called_once_with(
        image_path=project_dir / ".pc.img.tmp",
        slices={
            "pc_efi": (1048576, 524288),
            "pc_rootfs": (1572864, 1073741824),
        },
        target_dir=project_dir / ".devices",
    )
    mock_atexit.assert_called_once_with(image_service.detach_images)


def test_attach_images_is_idempotent(attachable, image_service):
    image_service.attach_images()
    first_managers = dict(image_service._vdev_managers)
    image_service.attach_images()

    assert image_service._vdev_managers == first_managers
    assert attachable.call_count == 1


def test_attach_images_uncreated(image_service):
    with pytest.raises(ValueError, match="Images must be created before attaching"):
        image_service.attach_images()


def test_attach_images_failure(attachable, image_service):
    attachable.return_value.mount.side_effect = errors.MountError("no fuse for you")

    with pytest.raises(errors.MountError, match="no fuse for you"):
        image_service.attach_images()

    assert image_service._vdev_managers == {}


def test_attach_images_multivolume_failure_rolls_back(
    image_service, default_factory, mock_project, project_dir, mocker
):
    image_service._images = {
        "vol1": project_dir / ".vol1.img.tmp",
        "vol2": project_dir / ".vol2.img.tmp",
    }
    mock_project.volumes = {"vol1": mocker.Mock(), "vol2": mocker.Mock()}
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )
    mocker.patch("imagecraft.pack.gptutil.get_partition_slices", return_value={})

    mock_vdev1 = mocker.Mock()
    mock_vdev2 = mocker.Mock()
    mock_vdev2.mount.side_effect = errors.MountError("vol2 mount failed")

    mocker.patch(
        "imagecraft.services.image.VirtualDeviceManager",
        side_effect=[mock_vdev1, mock_vdev2],
    )

    with pytest.raises(errors.MountError, match="vol2 mount failed"):
        image_service.attach_images()

    mock_vdev1.mount.assert_called_once()
    mock_vdev1.unmount.assert_called_once()
    assert image_service._vdev_managers == {}


def test_attach_images_raises_on_partial_attach(image_service, project_dir, mocker):
    image_service._images = {
        "vol1": project_dir / ".vol1.img.tmp",
        "vol2": project_dir / ".vol2.img.tmp",
    }
    image_service._vdev_managers = {"vol1": mocker.Mock()}

    with pytest.raises(
        errors.MountError, match="Unexpected partially-attached state found."
    ):
        image_service.attach_images()


def test_detach_images_unmounts_managers(image_service, project_dir, mocker):
    mock_vdev = mocker.Mock()
    mock_vdev.unmount = mocker.Mock()
    image_service._vdev_managers = {"pc": mock_vdev}

    image_service.detach_images()

    mock_vdev.unmount.assert_called_once_with()
    assert image_service._vdev_managers == {}


def test_detach_images_warns_on_failure(image_service, project_dir, mocker):
    """A failing unmount is reported, not raised, and manager is retained for retry."""
    mock_vdev = mocker.Mock()
    mock_vdev.unmount.side_effect = errors.MountError("device is busy")
    image_service._vdev_managers = {"pc": mock_vdev}
    mock_warning = mocker.patch("imagecraft.services.image.emit.warning")

    image_service.detach_images()

    assert "device is busy" in mock_warning.call_args[0][0]
    assert image_service._vdev_managers == {"pc": mock_vdev}

    # Subsequent successful unmount clears the manager
    mock_vdev.unmount.side_effect = None
    image_service.detach_images()
    assert image_service._vdev_managers == {}


def test_cleanup_temporary_images(image_service, project_dir, mocker):
    hidden = project_dir / ".pc.img.tmp"
    hidden.touch()
    image_service._images = {"pc": hidden}
    mock_detach = mocker.patch.object(image_service, "detach_images")

    image_service.cleanup_temporary_images()

    mock_detach.assert_called_once_with()
    assert not hidden.exists()
    assert image_service._images is None


def test_cleanup_temporary_images_noop(image_service, mocker):
    mock_detach = mocker.patch.object(image_service, "detach_images")

    image_service.cleanup_temporary_images()

    mock_detach.assert_not_called()


def test_get_device_paths(
    image_service, default_factory, mock_project, project_dir, mocker
):
    image_service._images = {"pc": project_dir / ".pc.img.tmp"}
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )
    mock_vdev = mocker.Mock()
    mock_vdev.devices = {
        "pc_efi": project_dir / ".devices" / "pc_efi.img",
        "pc_rootfs": project_dir / ".devices" / "pc_rootfs.img",
    }
    image_service._vdev_managers = {"pc": mock_vdev}

    mapping = image_service.get_device_paths()

    assert mapping == {
        "pc": project_dir / ".pc.img.tmp",
        "pc/efi": project_dir / ".devices" / "pc_efi.img",
        "pc/rootfs": project_dir / ".devices" / "pc_rootfs.img",
    }


def test_get_device_paths_unattached(image_service):
    assert image_service.get_device_paths() == {}


def test_get_device_paths_raises_on_partial_attach(
    image_service, default_factory, mock_project, project_dir, mocker
):
    """A partially unmounted volume must not yield a silently incomplete map."""
    mocker.patch.object(
        default_factory.get("project"), "get", return_value=mock_project
    )
    image_service._images = {"pc": project_dir / ".pc.img.tmp"}
    vdev = mocker.Mock()
    # efi is gone; rootfs is still mounted.
    vdev.devices = {"pc_rootfs": project_dir / ".devices" / "pc_rootfs.img"}
    image_service._vdev_managers = {"pc": vdev}

    with pytest.raises(errors.MountError, match="pc_efi"):
        image_service.get_device_paths()


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
