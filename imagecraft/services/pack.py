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
import pathlib
import typing

from craft_application import AppMetadata, PackageService, models
from overrides import override  # type: ignore[reportUnknownVariableType]

from imagecraft.ubuntu_image import ubuntu_image_pack

if typing.TYPE_CHECKING:
    from imagecraft.services import ImagecraftServiceFactory


class ImagecraftPackService(PackageService):
    """Package service subclass for Imagecraft."""

    def __init__(  # noqa: PLR0913
        self,
        app: AppMetadata,
        services: "ImagecraftServiceFactory",
        *,
        project: models.Project,
        platform: str | None,
        build_for: str,
    ) -> None:
        super().__init__(app, services, project=project)
        self._platform = platform
        self._build_for = build_for

    @override
    def pack(self, prime_dir: pathlib.Path, dest: pathlib.Path) -> list[pathlib.Path]:
        """Pack the image.

        :param dest: Directory into which to write the gadget
        """
        gadget_path = "$CRAFT_PART_INSTALL/install"

        # Create per-platform output directories
        platform_output = pathlib.Path(dest, self._platform if self._platform else "")
        os.makedirs(platform_output, exist_ok=True)

        ubuntu_image_pack(str(prime_dir), gadget_path, str(dest))

        return []

    @property
    def metadata(self) -> models.BaseMetadata:
        """Get the metadata model for this project."""
        # nop (no metadata file for Imagecraft)
        return models.BaseMetadata()

    @override
    def write_metadata(self, path: pathlib.Path) -> None:
        """Write the project metadata to metadata.yaml in the given directory.

        :param path: The path to the prime directory.
        """
        # nop (no metadata file for Imagecraft)
