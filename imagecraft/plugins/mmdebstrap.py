# This file is part of imagecraft.
#
# Copyright 2024 Canonical Ltd.
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

"""The Mmdebstrap plugin."""

from typing import Literal

from craft_parts import plugins


class MmdebstrapPluginProperties(plugins.PluginProperties, frozen=True):
    """Supported attributes for the 'MmdebstrapPlugin' plugin."""

    plugin: Literal["mmdebstrap"] = "mmdebstrap"


class MmdebstrapPlugin(plugins.Plugin):
    """Bootstrap a rootfs with mmdebstrap."""

    properties_class = MmdebstrapPluginProperties

    def get_build_snaps(self) -> set[str]:
        """Return a set of required snaps to install in the build environment."""
        return set()

    def get_build_packages(self) -> set[str]:
        """Return a set of required packages to install in the build environment."""
        return {"mmdebstrap", "dpkg", "apt-utils", "arch-test"}

    def get_build_environment(self) -> dict[str, str]:
        """Return a dictionary with the environment to use in the build step."""
        return {}

    def get_build_commands(self) -> list[str]:
        """Return a list of commands to run during the build step."""
        return [
            (
                "mmdebstrap --arch amd64 --variant=minbase --mode=sudo "
                f"--include=apt --format=dir noble {self._part_info.part_install_dir} "
                "--include=ubuntu-minimal,ubuntu-standard "
                "http://archive.ubuntu.com/ubuntu/"
            )
        ]
