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

import pathlib
import typing
from typing import cast

from craft_application import AppMetadata, PackageService, errors, models
from craft_application.models import BuildInfo
from overrides import override  # type: ignore[reportUnknownVariableType]

from imagecraft.models import Project
from imagecraft.pack import packer

if typing.TYPE_CHECKING:
    from imagecraft.services import ImagecraftServiceFactory


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
    def pack(self, prime_dir: pathlib.Path, dest: pathlib.Path) -> list[pathlib.Path]:
        """Pack the image.

        :param prime_dir: Directory path to the prime directory.
        :param dest: Directory into which to write the package(s).
        :returns: A list of paths to created packages.
        """

        if not self._build_plan:
            raise errors.EmptyBuildPlanError

        if len(self._build_plan) > 1:
            raise errors.MultipleBuildsError

        platform = self._build_plan[0].platform
        self._filename = f"{self._project.name}_{self._project.version}_{platform}.raw"

        dest_path = dest / self._filename

        packer(
            prime_dir=prime_dir,
            work_dir=self._services.lifecycle.project_info.dirs.work_dir,
            imagepath=dest_path,
            project=cast(Project, self._project),
        )

        return [dest_path]

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
