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

"""Imagecraft Project service."""

from typing import Any, cast

import craft_cli
import craft_platforms
from craft_application import ProjectService
from overrides import override  # type: ignore[reportUnknownVariableType]

from imagecraft import grammar
from imagecraft.models import VolumeProject


class ImagecraftProjectService(ProjectService):
    """Imagecraft-specific project service."""

    @override
    @staticmethod
    def _app_preprocess_project(
        project: dict[str, Any],
        *,
        build_on: str,
        build_for: str,
        platform: str,  # noqa: ARG004
    ) -> None:
        transform_yaml(build_on=build_on, build_for=build_for, yaml_data=project)

    @override
    def get_partitions_for(
        self,
        *,
        platform: str,
        build_for: str,
        build_on: craft_platforms.DebianArchitecture,
    ) -> list[str] | None:
        project = self._preprocess(
            build_for=build_for, build_on=cast(str, build_on), platform=platform
        )
        volumes = VolumeProject.unmarshal(project)

        return volumes.get_partitions()


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
