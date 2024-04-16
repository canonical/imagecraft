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

"""Imagecraft Lifecycle service."""

from typing import cast

from craft_application import AppMetadata, LifecycleService, ServiceFactory, util
from craft_parts import Features
from overrides import override  # type: ignore[reportUnknownVariableType]

from imagecraft.errors import ImagecraftError
from imagecraft.models.project import Project

# Enable the craft-parts features that we use
Features(enable_overlay=True)


class ImagecraftLifecycleService(LifecycleService):
    """Imagecraft-specific lifecycle service."""

    def __init__(  # noqa: PLR0913
        self,
        app: AppMetadata,
        services: ServiceFactory,
        *,
        cache_dir: str,
        work_dir: str,
        project: Project,
        build_for: str,
        platform: str | None,
    ) -> None:
        super().__init__(
            app,
            services,
            project=project,
            build_for=build_for,
            platform=platform,
            cache_dir=cache_dir,
            work_dir=work_dir,
        )
        self._platform = platform
        self._build_for = build_for

    @override
    def setup(self) -> None:
        """Initialize the LifecycleManager with previously-set arguments."""
        if self._platform is None:
            build_on = util.get_host_architecture()
            base_build_plan = self._project.get_build_plan()
            build_plan = [
                plan for plan in base_build_plan if plan.build_for == self._build_for
            ]
            build_plan = [plan for plan in build_plan if plan.build_on == build_on]

            if len(build_plan) != 1:
                message = "Unable to determine which platform to build."
                details = (
                    f"Possible values are: "
                    f"{[info.platform for info in base_build_plan]}."
                )
                resolution = 'Choose a platform with the "--platform" parameter.'
                raise ImagecraftError(
                    message=message,
                    details=details,
                    resolution=resolution,
                )

            self._platform = build_plan[0].platform

        # Configure extra args to the LifecycleManager
        project = cast(Project, self._project)
        project_vars = {"version": project.version}

        self._manager_kwargs.update(
            base=project.base,
            project_name=project.name,
            project_vars=project_vars,
        )

        super().setup()

