# Copyright 2023-2025 Canonical Ltd.
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


import pytest
from craft_application import ServiceFactory
from imagecraft.services.image import ImageService
from imagecraft.services.pack import ImagecraftPackService


@pytest.fixture
def mock_image_service(default_factory: ServiceFactory, tmp_path):
    """ImageService with losetup operations mocked out."""
    svc = default_factory.get("image")
    # Pre-populate state so pack() doesn't need to call losetup
    svc._images = {"pc": tmp_path / ".pc.img.tmp"}
    svc._loop_devices = {"pc": "/dev/loop8"}
    svc._atexit_registered = True
    yield svc
    svc._loop_devices.clear()


def test_pack(
    tmp_path,
    enable_features,
    default_factory: ServiceFactory,
    pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    prime_dir = tmp_path / "prime"
    dest_path = tmp_path / "dest"

    # Mock out all system calls
    mocker.patch.object(mock_image_service, "create_images")
    mocker.patch.object(mock_image_service, "attach_images")
    mock_verify = mocker.patch.object(mock_image_service, "verify_images")
    mock_detach = mocker.patch.object(mock_image_service, "detach_images")
    mock_finalize = mocker.patch.object(mock_image_service, "finalize_images")
    mock_diskutil = mocker.patch("imagecraft.services.pack.diskutil", autospec=True)
    mock_grubutil = mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mock_image_cls = mocker.patch("imagecraft.services.pack.Image", autospec=True)

    # After finalize, get_images() should return dest paths
    mock_finalize.side_effect = lambda dest: mock_image_service._images.update(
        {"pc": dest / "pc.img"}
    )

    result = pack_service.pack(prime_dir=prime_dir, dest=dest_path)

    # format_device called for each partition (efi + rootfs), populate_device is not a separate call
    assert mock_diskutil.format_device.call_count == 2

    # Verify called before detach
    mock_verify.assert_called_once()
    mock_detach.assert_called_once()
    mock_finalize.assert_called_once_with(dest_path)

    # grubutil called on the final image
    mock_grubutil.setup_grub.assert_called_once()
    mock_image_cls.assert_called_once()

    # Old functions must NOT be called
    mock_diskutil.create_zero_image.assert_not_called()
    mock_diskutil.inject_partition_into_image.assert_not_called()
    mock_diskutil.format_populate_partition.assert_not_called()

    assert result == [dest_path / "pc.img"]


def test_pack_detaches_on_error(
    tmp_path,
    enable_features,
    default_factory: ServiceFactory,
    pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    """detach_images() must be called even if format_device raises."""
    dest_path = tmp_path / "dest"

    mocker.patch.object(mock_image_service, "create_images")
    mocker.patch.object(mock_image_service, "attach_images")
    mock_detach = mocker.patch.object(mock_image_service, "detach_images")
    mocker.patch.object(mock_image_service, "verify_images")
    mocker.patch.object(mock_image_service, "finalize_images")
    mocker.patch(
        "imagecraft.services.pack.diskutil.format_device",
        side_effect=RuntimeError("disk full"),
    )
    mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mocker.patch("imagecraft.services.pack.Image", autospec=True)

    with pytest.raises(RuntimeError, match="disk full"):
        pack_service.pack(prime_dir=tmp_path / "prime", dest=dest_path)

    mock_detach.assert_called_once()
