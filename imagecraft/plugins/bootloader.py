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

"""Bootloader plugin."""

from typing import Any, Literal, cast

from craft_parts import plugins


class BootloaderPluginProperties(plugins.PluginProperties, frozen=True):
    """Supported attributes for the 'bootloader' plugin."""

    plugin: Literal["bootloader"] = "bootloader"

    bootloader_target: str | None = None
    source: str  # pyright: ignore[reportGeneralTypeIssues]


class BootloaderPlugin(plugins.Plugin):
    """Builds the bootloader containing bootloader configuration."""

    properties_class = BootloaderPluginProperties

    def get_build_snaps(self) -> set[str]:
        """Return a set of required snaps to install in the build environment."""
        return set()

    def get_build_packages(self) -> set[str]:
        """Return a set a packages needed to build the bootloader.

        More specific packages to the actual bootloader build should be added manually by users.
        """
        return {"make"}

    def get_build_environment(self) -> dict[str, Any]:
        """Return a dictionary with the environment to use in the build step."""
        bootloader_arch = self._part_info.target_arch
        bootloader_series = "noble"
        return {"ARCH": bootloader_arch, "SERIES": bootloader_series}

    def get_build_commands(self) -> list[str]:
        """Return a list of commands to run during the build step."""
        options = cast(BootloaderPluginProperties, self._options)

        bootloader_target = options.bootloader_target
        if bootloader_target is None:
            bootloader_target = ""

        return [
            f"make {bootloader_target}",
            f"mv {self._part_info.part_build_dir}/install/* {self._part_info.part_install_dir}",
        ]
