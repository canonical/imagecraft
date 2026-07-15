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
from typing import cast

import pytest
from craft_application import ServiceFactory
from craft_cli import CraftError
from imagecraft.pack import diskutil
from imagecraft.services.image import ImageService
from imagecraft.services.pack import ImagecraftPackService


@pytest.fixture
def mock_image_service(default_factory: ServiceFactory, tmp_path):
    """ImageService with image state pre-populated.

    The default project (see tests/conftest.py) has two partitions: efi
    (256M aligned to 524288 sectors -- but spec says 500M) and rootfs
    (6G). We expose stub partition geometry below so pack() can run
    without invoking sfdisk on a real image.
    """
    svc = cast(ImageService, default_factory.get("image"))
    # Pre-populate image state so pack() doesn't need to call create_images().
    svc._images = {"pc": tmp_path / ".pc.img.tmp"}
    return svc


def _geometry_for(structure_item, partition_number, start_sector=2048):
    """Build a PartitionGeometry that matches the structure's requested size."""
    sector_size = 512
    sectors = diskutil.bytes_to_sectors(structure_item.size, sector_size)
    return diskutil.PartitionGeometry(
        sector_offset=start_sector + partition_number * 10_000,
        sector_count=sectors,
        sector_size=sector_size,
    )


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

    project = default_factory.get("project").get()
    volume = project.volumes["pc"]

    # Mock image service methods so we don't actually touch loop devices/files.
    mock_create = mocker.patch.object(mock_image_service, "create_images")
    mock_verify = mocker.patch.object(mock_image_service, "verify_images")
    mock_finalize = mocker.patch.object(
        mock_image_service,
        "finalize_images",
        return_value={"pc": tmp_path / "dest" / "pc.img"},
    )

    # Provide geometry that matches each partition's structure size.
    geometries = {
        item.name: _geometry_for(item, idx)
        for idx, item in enumerate(volume.structure, start=1)
    }

    def fake_geometry(*, imagepath, partition_number):
        # partition_number is 1-based; structure positions are 1-based.
        item = volume.structure[partition_number - 1]
        return geometries[item.name]

    mock_get_geometry = mocker.patch(
        "imagecraft.services.pack.diskutil.get_partition_geometry",
        side_effect=fake_geometry,
    )
    mock_format_populate = mocker.patch(
        "imagecraft.services.pack.diskutil.format_populate_partition",
    )
    mock_grubutil = mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mock_image_cls = mocker.patch("imagecraft.services.pack.Image", autospec=True)

    # losetup-style methods must NOT be reached from the build path.
    mock_attach = mocker.patch.object(mock_image_service, "attach_images")
    mock_detach = mocker.patch.object(mock_image_service, "detach_images")

    result = pack_service.pack(prime_dir=prime_dir, dest=dest_path)

    # create_images is still called (it's idempotent).
    mock_create.assert_called_once()

    # One format-and-populate per partition (efi + rootfs).
    assert mock_format_populate.call_count == len(volume.structure)
    assert mock_get_geometry.call_count == len(volume.structure)

    # Each format_populate call writes directly into the disk image at the
    # partition's geometry, using the structure's fstype/label.
    for call_args, structure_item in zip(
        mock_format_populate.call_args_list, volume.structure, strict=True
    ):
        kwargs = call_args.kwargs
        assert kwargs["fstype"] == structure_item.filesystem
        assert kwargs["label"] == structure_item.filesystem_label
        # partitionpath is the disk image itself (no intermediate temp file).
        assert kwargs["partitionpath"] == tmp_path / ".pc.img.tmp"
        assert kwargs["geometry"] == geometries[structure_item.name]

    mock_verify.assert_called_once()
    mock_finalize.assert_called_once_with(dest_path)

    # grubutil called on the final image.
    mock_grubutil.setup_grub.assert_called_once()
    mock_image_cls.assert_called_once()

    # losetup-style methods must NOT have been called from pack().
    mock_attach.assert_not_called()
    mock_detach.assert_not_called()

    assert result == [dest_path / "pc.img"]


def test_pack_size_mismatch_raises(
    tmp_path,
    enable_features,
    default_factory: ServiceFactory,
    pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    """If sfdisk reports a partition size that disagrees with the structure
    spec, pack() must raise instead of silently truncating data."""
    dest_path = tmp_path / "dest"

    mocker.patch.object(mock_image_service, "create_images")
    mocker.patch.object(mock_image_service, "verify_images")
    mocker.patch.object(mock_image_service, "finalize_images")
    mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mocker.patch("imagecraft.services.pack.Image", autospec=True)

    # Return geometry with a wrong sector count.
    bogus_geometry = diskutil.PartitionGeometry(
        sector_offset=2048,
        sector_count=1,  # deliberately wrong
        sector_size=512,
    )
    mocker.patch(
        "imagecraft.services.pack.diskutil.get_partition_geometry",
        return_value=bogus_geometry,
    )
    mocker.patch("imagecraft.services.pack.diskutil.format_populate_partition")

    with pytest.raises(CraftError, match="does not match the requested size"):
        pack_service.pack(prime_dir=tmp_path / "prime", dest=dest_path)
