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

"""Gadget plugin."""

from typing import Any, Literal, cast

from craft_parts import plugins


class GadgetPluginProperties(plugins.PluginProperties, frozen=True):
    """Supported attributes for the 'gadget' plugin."""

    plugin: Literal["gadget"] = "gadget"

    gadget_target: str | None = None
    source: str  # pyright: ignore[reportGeneralTypeIssues]


class GadgetPlugin(plugins.Plugin):
    """Builds the gadget containing bootloader configuration."""

    properties_class = GadgetPluginProperties

    def get_build_snaps(self) -> set[str]:
        """Return a set of required snaps to install in the build environment."""
        return set()

    def get_build_packages(self) -> set[str]:
        """Return a set a packages needed to build the gadget.

        More specific packages to the actual gadget build should be added manually by users.
        """
        return {"make"}

    def get_build_environment(self) -> dict[str, Any]:
        """Return a dictionary with the environment to use in the build step."""
        gadget_arch = self._part_info.target_arch
        gadget_series = self._part_info.project_info.series
        return {"ARCH": gadget_arch, "SERIES": gadget_series}

    def get_build_commands(self) -> list[str]:
        """Return a list of commands to run during the build step."""
        options = cast(GadgetPluginProperties, self._options)

        gadget_target = options.gadget_target
        if gadget_target is None:
            gadget_target = ""

        return [
            f"make {gadget_target}",
            f"mv {self._part_info.part_build_dir}/install {self._part_info.part_install_dir}/gadget",
        ]
