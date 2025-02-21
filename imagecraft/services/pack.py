# Copyright 2023 Canonical Ltd.
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

from imagecraft.models import Project
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
        volume_name, volume = next(iter(cast(Project, self._project).volumes.items()))
        disk_image_file = dest / (volume_name + os.extsep + "img")

        # Create empty image
        gptutil.create_empty_gpt_image(
            imagepath=disk_image_file,
            sector_size=SECTOR_SIZE,
            layout=volume,
        )

        # Create filesystems
        project_dirs = self._services.lifecycle.project_info.dirs
        with tempfile.TemporaryDirectory() as partition_dir:
            for structure_item in volume.structure:
                partition_name = f"volume/{volume_name}/{structure_item.name}"
                partition_prime_dir = project_dirs.get_prime_dir(
                    partition=partition_name
                )

                partition_img = (
                    Path(partition_dir) / f"{volume_name}.{structure_item.name}.img"
                )
                sector_count = diskutil.bytes_to_sectors(
                    structure_item.size, SECTOR_SIZE
                )
                diskutil.format_install_partition(
                    fstype=structure_item.filesystem,
                    content_dir=partition_prime_dir,
                    partitionpath=partition_img,
                    sector_size=SECTOR_SIZE,
                    sector_count=sector_count,
                    label=structure_item.filesystem_label,
                )
                diskutil.inject_partition_into_image(
                    partition=partition_img,
                    imagepath=disk_image_file,
                    sector_size=SECTOR_SIZE,
                    sector_offset=gptutil.get_partition_sector_offset(
                        disk_image_file,
                        structure_item.name,
                    ),
                    sector_count=sector_count,
                )
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
