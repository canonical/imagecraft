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

from craft_application import Application, AppMetadata
from craft_parts.plugins.plugins import PluginType

# type: ignore[reportUnknownVariableType]
from typing_extensions import override

from imagecraft import plugins
from imagecraft.models import project

APP_METADATA = AppMetadata(
    name="imagecraft",
    summary="A tool to create Ubuntu bootable images",
    ProjectClass=project.Project,
    enable_for_grammar=True,
    check_supported_base=True,
)


class Imagecraft(Application):
    """Imagecraft application definition."""

    @override
    def _get_app_plugins(self) -> dict[str, PluginType]:
        return plugins.get_app_plugins()

    @override
    def _enable_craft_parts_features(self) -> None:
        # pylint: disable=import-outside-toplevel
        from craft_parts.features import Features  # noqa: PLC0415

        Features(enable_partitions=True, enable_overlay=True)
