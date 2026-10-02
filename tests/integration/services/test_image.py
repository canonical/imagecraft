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
import pytest
from craft_application import ServiceFactory
from imagecraft.services.image import ImageService

pytestmark = [pytest.mark.usefixtures("enable_features")]


@pytest.fixture
def image_service(default_factory: ServiceFactory, enable_features):
    svc = default_factory.get("image")
    assert isinstance(svc, ImageService)
    yield svc
    svc.detach_images()


def test_create_images_produces_hidden_files(image_service: ImageService, new_dir):
    """create_images() creates a hidden .{name}.img.tmp file per volume."""
    images = image_service.create_images()

    assert set(images.keys()) == {"pc"}
    hidden_path = image_service._project_dir / ".pc.img.tmp"
    assert images["pc"] == hidden_path
    assert hidden_path.exists()
    assert hidden_path.stat().st_size > 0


def test_create_images_is_idempotent(image_service: ImageService, new_dir):
    """Calling create_images() twice returns the same mapping without re-creating."""
    first = image_service.create_images()
    mtime_after_first = (image_service._project_dir / ".pc.img.tmp").stat().st_mtime

    second = image_service.create_images()
    mtime_after_second = (image_service._project_dir / ".pc.img.tmp").stat().st_mtime

    assert first is second
    assert mtime_after_first == mtime_after_second


def test_create_images_gpt_table(image_service: ImageService, new_dir):
    """create_images() produces a valid GPT-partitioned image."""
    from imagecraft.pack import gptutil  # noqa: PLC0415

    image_service.create_images()
    # If the GPT table is broken sfdisk will raise; this should pass cleanly.
    gptutil.verify_partition_tables(image_service._project_dir / ".pc.img.tmp")


def test_verify_images(image_service: ImageService, new_dir):
    """verify_images() passes for freshly created images."""
    image_service.create_images()
    # Should not raise.
    image_service.verify_images()


def test_finalize_images_moves_files(image_service: ImageService, new_dir, tmp_path):
    """finalize_images() moves images to dest and updates internal paths."""
    image_service.create_images()
    hidden_path = image_service._project_dir / ".pc.img.tmp"
    assert hidden_path.exists()

    dest = tmp_path / "output"
    image_service.finalize_images(dest)

    final_path = dest / "pc.img"
    assert final_path.exists()
    assert not hidden_path.exists()


def test_finalize_images_creates_dest_dir(
    image_service: ImageService, new_dir, tmp_path
):
    """finalize_images() creates the destination directory if it doesn't exist."""
    image_service.create_images()
    dest = tmp_path / "deeply" / "nested" / "output"

    image_service.finalize_images(dest)

    assert dest.exists()
    assert (dest / "pc.img").exists()


@pytest.mark.requires_root
def test_attach_and_detach_images(image_service: ImageService, new_dir):
    """attach_images() provides virtual devices; detach_images() removes them."""
    image_service.create_images()
    image_service.attach_images()

    assert "pc" in image_service._vdev_managers
    devices = image_service._vdev_managers["pc"].devices
    assert set(devices) == {"pc_efi", "pc_rootfs"}
    for part_file in devices.values():
        assert part_file.is_file()

    image_service.detach_images()

    assert image_service._vdev_managers == {}
    assert not (image_service._project_dir / ".devices").exists()


@pytest.mark.requires_root
def test_attach_images_is_idempotent(image_service: ImageService, new_dir):
    """Calling attach_images() twice reuses the existing virtual devices."""
    image_service.create_images()
    image_service.attach_images()
    first_devices = dict(image_service._vdev_managers["pc"].devices)

    image_service.attach_images()
    assert image_service._vdev_managers["pc"].devices == first_devices

    image_service.detach_images()


@pytest.mark.requires_root
def test_get_partition_device_paths(image_service: ImageService, new_dir):
    """get_device_paths() returns the image file and virtual partition files."""
    image_service.create_images()
    image_service.attach_images()

    paths = image_service.get_device_paths()

    # Volume-level device is the raw image file.
    assert paths["pc"] == image_service._project_dir / ".pc.img.tmp"
    assert paths["pc"].is_file()

    # default_project_yaml has efi and rootfs partitions
    assert paths["pc/efi"] == image_service._project_dir / ".devices" / "pc_efi.img"
    assert (
        paths["pc/rootfs"] == image_service._project_dir / ".devices" / "pc_rootfs.img"
    )
    for key in ("pc/efi", "pc/rootfs"):
        assert paths[key].is_file()
        assert paths[key].stat().st_size > 0

    image_service.detach_images()
