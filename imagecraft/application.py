# This file is part of imagecraft.
#
# Copyright 2023-2025 Canonical Ltd.
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

from typing import Any

import craft_cli
from craft_application import Application, AppMetadata
from craft_parts.plugins.plugins import PluginType
from overrides import override  # type: ignore[reportUnknownVariableType]

from imagecraft import grammar, plugins
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
    def _extra_yaml_transform(
        self,
        yaml_data: dict[str, Any],
        *,
        build_on: str,
        build_for: str | None,
    ) -> dict[str, Any]:
        return transform_yaml(
            build_on=build_on, build_for=build_for, yaml_data=yaml_data
        )

    @override
    def _configure_services(self, provider_name: str | None) -> None:
        self.services.update_kwargs(
            "package",
            build_plan=self._build_plan,
        )
        self.services.update_kwargs(
            "lifecycle",
            cache_dir=self.cache_dir,
            work_dir=self._work_dir,
            build_plan=self._build_plan,
        )
        super()._configure_services(provider_name)

    @override
    def _get_app_plugins(self) -> dict[str, PluginType]:
        return plugins.get_app_plugins()

    @override
    def _enable_craft_parts_features(self) -> None:
        # pylint: disable=import-outside-toplevel
        from craft_parts.features import Features

        Features(enable_partitions=True)

    @override
    def _setup_partitions(self, yaml_data: dict[str, Any]) -> list[str] | None:  # noqa: ARG002
        return ["default"]


def transform_yaml(
    build_on: str, build_for: str | None, yaml_data: dict[str, Any]
) -> dict[str, Any]:
    """Resolve the grammar in the Volumes section."""
    build_for = build_for or build_on
    if "volumes" in yaml_data:
        craft_cli.emit.debug(f"Processing grammar (on {build_on} for {build_for})")
        yaml_data["volumes"] = grammar.process_volumes(
            volumes_yaml_data=yaml_data["volumes"],
            arch=build_on,
            target_arch=build_for,
        )

    return yaml_data
