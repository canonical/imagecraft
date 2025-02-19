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

import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

from craft_application import AppMetadata, PackageService, models
from craft_application.models import BuildInfo
from overrides import override  # type: ignore[reportUnknownVariableType]

from imagecraft.models import Project, get_partition_name
from imagecraft.pack import diskutil, gptutil

if TYPE_CHECKING:
    from imagecraft.services import ImagecraftServiceFactory


SECTOR_SIZE = 512


class ImagecraftPackService(PackageService):
    """Package service subclass for Imagecraft."""

    def __init__(
        self,
        app: AppMetadata,
        services: "ImagecraftServiceFactory",
        *,
        project: Project,
        build_plan: list[BuildInfo],
    ) -> None:
        super().__init__(app, services, project=project)

        self._build_plan = build_plan

    @override
    def pack(self, prime_dir: Path, dest: Path) -> list[Path]:  # noqa: ARG002
        """Pack the image.

        :param prime_dir: Directory path to the prime directory.
        :param dest: Directory into which to write the package(s).
        :returns: A list of paths to created packages.
        """
        # Pydantic has already validated that there is only a single volume before now
        project = cast(Project, self._project)
        if len(project.volumes) != 1:
            raise AssertionError("This code can only handle one volume")
        volume_name, volume = next(iter(project.volumes.items()))
        disk_image_file = dest / (volume_name + os.extsep + "img")

        # Create empty image
        gptutil.create_empty_gpt_image(
            imagepath=disk_image_file,
            sector_size=SECTOR_SIZE,
            layout=volume,
        )

        # Create partition images with filesystems.  These are always recreated, but we
        # may want to revisit that once this is solved:
        # https://github.com/canonical/craft-parts/issues/665
        project_dirs = self._services.lifecycle.project_info.dirs
        with tempfile.TemporaryDirectory() as tmp_dir:
            for structure_item in volume.structure:
                partition_name = get_partition_name(volume_name, structure_item)
                partition_prime_dir = project_dirs.get_prime_dir(
                    partition=partition_name
                )
                partition_img = (
                    Path(tmp_dir) / f"{volume_name}.{structure_item.name}.img"
                )
                partition_size = diskutil.DiskSize(
                    bytesize=structure_item.size,
                    sector_size=SECTOR_SIZE,
                )

                diskutil.format_populate_partition(
                    fstype=structure_item.filesystem,
                    content_dir=partition_prime_dir,
                    partitionpath=partition_img,
                    disk_size=partition_size,
                    label=structure_item.filesystem_label,
                )
                diskutil.inject_partition_into_image(
                    partition=partition_img,
                    imagepath=disk_image_file,
                    sector_offset=gptutil.get_partition_sector_offset(
                        disk_image_file,
                        structure_item.name,
                    ),
                    disk_size=partition_size,
                )
        gptutil.verify_partition_tables(disk_image_file)
        return [disk_image_file]

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
