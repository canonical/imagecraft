# This file is part of imagecraft.
#
# Copyright 2023 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Main Imagecraft Application."""

from craft_application import Application, AppMetadata
from overrides import override  # type: ignore[reportUnknownVariableType]

from imagecraft.models import project

APP_METADATA = AppMetadata(
    name="imagecraft",
    summary="A tool to create Ubuntu bootable images",
    ProjectClass=project.Project,
    BuildPlannerClass=project.BuildPlanner,
)


class Imagecraft(Application):
    """Imagecraft application definition."""

    @override
    def _configure_services(self, provider_name: str | None) -> None:
        self.services.set_kwargs(
            "package",
            build_plan=self._build_plan,
        )
        self.services.set_kwargs(
            "lifecycle",
            cache_dir=self.cache_dir,
            work_dir=self._work_dir,
            build_plan=self._build_plan,
        )
        super()._configure_services(provider_name)
