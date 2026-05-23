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

"""Imagecraft Package service."""

import contextlib
import tempfile
from pathlib import Path
from typing import cast

from craft_application import PackageService, models
from craft_cli import CraftError, emit
from typing_extensions import override

from imagecraft.models import Project, get_partition_name
from imagecraft.pack import Image, diskutil, grubutil
from imagecraft.services.image import ImageService


class ImagecraftPackService(PackageService):
    """Package service subclass for Imagecraft."""

    @override
    def pack(self, prime_dir: Path, dest: Path) -> list[Path]:
        """Pack the image.

        :param prime_dir: Directory path to the prime directory.
        :param dest: Directory into which to write the package(s).
        :returns: A list of paths to created packages.
        """
        project = cast(Project, self._services.get("project").get())
        if len(project.volumes) != 1:
            raise AssertionError("This code can only handle one volume")
        volume_name, volume = next(iter(project.volumes.items()))

        image_service = cast(ImageService, self._services.get("image"))
        # create_images() is idempotent — the prologue hook will have run it
        # already during the lifecycle, but pack may be called standalone.
        image_service.create_images()

        project_dirs = self._services.get("lifecycle").project_info.dirs
        images = image_service.get_images()
        image_path = images[volume_name]
        partition_numbers = image_service._get_partition_numbers(volume)  # noqa: SLF001

        for structure_item in volume.structure:
            partition_name = get_partition_name(volume_name, structure_item)
            emit.progress(f"Preparing partition {partition_name}")
            partition_prime_dir = project_dirs.get_prime_dir(
                partition=partition_name
            )

            partition_number = partition_numbers[structure_item.name]
            geometry = diskutil.get_partition_geometry(
                imagepath=image_path,
                partition_number=partition_number,
            )

            # Sanity-check the on-disk size matches the structure spec.
            expected_sectors = diskutil.bytes_to_sectors(
                structure_item.size, geometry.sector_size
            )
            if geometry.sector_count != expected_sectors:
                raise CraftError(
                    f"Partition {partition_name!r} on-disk size "
                    f"({geometry.sector_count} sectors) does not match the "
                    f"requested size ({expected_sectors} sectors).",
                )

            # Build the partition contents in a temp file, then dd it into
            # the disk image at the partition's sector offset. This avoids
            # losetup entirely, which is needed so imagecraft can run inside
            # unprivileged LXD containers.
            safe_prefix = partition_name.replace("/", "_")
            with tempfile.NamedTemporaryFile(
                prefix=f".{safe_prefix}.part.",
                suffix=".tmp",
                dir=image_path.parent,
                delete=False,
            ) as tf:
                part_path = Path(tf.name)
            try:
                with part_path.open("wb") as fh:
                    fh.truncate(geometry.size_bytes)

                diskutil.format_populate_partition(
                    fstype=structure_item.filesystem,
                    content_dir=partition_prime_dir,
                    partitionpath=part_path,
                    label=structure_item.filesystem_label,
                )

                diskutil.inject_partition_into_image(
                    partition=part_path,
                    imagepath=image_path,
                    sector_offset=geometry.sector_offset,
                    disk_size=diskutil.DiskSize(
                        bytesize=geometry.size_bytes,
                        sector_size=geometry.sector_size,
                    ),
                )
            finally:
                with contextlib.suppress(FileNotFoundError):
                    part_path.unlink()

        image_service.verify_images()

        images = image_service.finalize_images(dest)

        filesystem_mount = self._services.get(
            "lifecycle"
        ).project_info.default_filesystem_mount
        arch = self._services.get("lifecycle").project_info.target_arch
        for volume_name, path in images.items():
            volume = project.volumes[volume_name]
            image = Image(volume=volume, disk_path=path)
            grubutil.setup_grub(
                image=image,
                workdir=project_dirs.work_dir,
                arch=arch,
                filesystem_mount=filesystem_mount,
            )

        return list(images.values())

    @property
    def metadata(self) -> models.BaseMetadata:
        """Get the metadata model for this project."""
        # nop (no metadata file for Imagecraft)
        return models.BaseMetadata()

    @override
    def write_metadata(self, path: Path) -> None:
        """Write the project metadata to metadata.yaml in the given directory.

        :param path: The path to the prime directory.
        """
        # nop (no metadata file for Imagecraft)
