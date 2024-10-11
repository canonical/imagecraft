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

"""UbuntuBootstrap plugin."""

from typing import Literal, cast

from craft_application.models.constraints import UniqueList
from craft_cli import EmitterMode, emit
from craft_parts import plugins

from imagecraft.models.package_repository import (
    get_customization_package_repository,
    get_main_package_repository,
)
from imagecraft.ubuntu_image import ubuntu_image_cmds_build_rootfs


class GerminateProperties(plugins.PluginProperties, frozen=True):
    """Supported attributes for the 'Germinate' section of the UbuntuBootstrapPlugin plugin."""

    urls: UniqueList[str]
    branch: str | None = None
    names: UniqueList[str]
    vcs: bool | None = True


class UbuntuBootstrapPluginProperties(plugins.PluginProperties, frozen=True):
    """Supported attributes for the 'UbuntuBootstrapPlugin' plugin."""

    plugin: Literal["ubuntu-bootstrap"] = "ubuntu-bootstrap"

    ubuntu_bootstrap_pocket: str = "updates"
    ubuntu_bootstrap_germinate: GerminateProperties
    ubuntu_bootstrap_extra_snaps: UniqueList[str] | None = None
    ubuntu_bootstrap_extra_packages: UniqueList[str] | None = None
    ubuntu_bootstrap_kernel: str | None = None


class UbuntuBootstrapPlugin(plugins.Plugin):
    """Builds a rootfs via ubuntu-image."""

    properties_class = UbuntuBootstrapPluginProperties

    def get_build_snaps(self) -> set[str]:
        """Return a set of required snaps to install in the build environment."""
        return set("ubuntu-image")

    def get_build_packages(self) -> set[str]:
        """Return a set of required packages to install in the build environment."""
        return set()

    def get_build_environment(self) -> dict[str, str]:
        """Return a dictionary with the environment to use in the build step."""
        return {}

    def get_build_commands(self) -> list[str]:
        """Return a list of commands to run during the build step."""
        options = cast(UbuntuBootstrapPluginProperties, self._options)

        arch = self._part_info.target_arch

        series = self._part_info.project_info.series

        source_branch = series
        branch = options.ubuntu_bootstrap_germinate.branch
        if branch:
            source_branch = branch

        main_repo = get_main_package_repository(
            self._part_info.project_info.package_repositories_,
        )

        customize_repo = get_customization_package_repository(
            self._part_info.project_info.package_repositories_,
        )

        custom_components = None
        custom_pocket = None
        if customize_repo:
            custom_components = customize_repo.components
            custom_pocket = customize_repo.pocket.value

        debug = emit.get_mode() == EmitterMode.DEBUG

        return ubuntu_image_cmds_build_rootfs(
            series,
            arch,
            main_repo.pocket.value,
            options.ubuntu_bootstrap_germinate.urls,
            source_branch,
            options.ubuntu_bootstrap_germinate.names,
            main_repo.components,
            main_repo.flavor,
            main_repo.url,
            options.ubuntu_bootstrap_pocket,
            options.ubuntu_bootstrap_kernel,
            options.ubuntu_bootstrap_extra_snaps,
            options.ubuntu_bootstrap_extra_packages,
            custom_components,
            custom_pocket,
            debug=debug,
        )
