# This file is part of imagecraft.
#
# Copyright 2026 Canonical Ltd.
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

"""The mmdebstrap plugin."""

from typing import Literal, cast

import distro
from craft_parts.plugins import Plugin
from craft_parts.plugins.properties import PluginProperties
from typing_extensions import override


class MmdebstrapPluginProperties(PluginProperties, frozen=True):
    """Properties for the mmdebstrap plugin."""

    plugin: Literal["mmdebstrap"] = "mmdebstrap"

    mmdebstrap_suite: str | None = None
    mmdebstrap_variant: Literal[
        "extract",
        "custom",
        "essential",
        "apt",
        "required",
        "minbase",
        "buildd",
        "important",
        "debootstrap",
        "standard",
    ] = "apt"
    mmdebstrap_packages: list[str] = []


class MmdebstrapPlugin(Plugin):
    """A plugin to create a root filesystem using mmdebstrap.

    This plugin uses the following plugin-specific keywords:

    - mmdebstrap-suite
     (string)
     The suite to bootstrap (e.g. 'noble').

    - mmdebstrap-variant
      (string)
      The bootstrap variant. Default is 'apt'.

    - mmdebstrap-packages
      (list of strings)
      Additional packages to include in the bootstrap.
    """

    properties_class = MmdebstrapPluginProperties

    @override
    def get_build_snaps(self) -> set[str]:
        """Return a set of required snaps to install in the build environment."""
        return set()

    @override
    def get_build_packages(self) -> set[str]:
        """Return a set of required packages to install in the build environment."""
        return {"mmdebstrap"}

    @override
    def get_build_environment(self) -> dict[str, str]:
        """Return a dictionary with the environment to use in the build step."""
        return {}

    @override
    def get_build_commands(self) -> list[str]:
        """Return a list of commands to run during the build step."""
        options = cast(MmdebstrapPluginProperties, self._options)

        cmd: list[str] = [
            "mmdebstrap",
            f"--arch={self._part_info.target_arch}",
            "--mode=fakeroot",
            f"--variant={options.mmdebstrap_variant}",
            "--format=dir",
        ]

        if options.mmdebstrap_packages:
            cmd.append(f"--include={','.join(options.mmdebstrap_packages)}")

        suite = options.mmdebstrap_suite or self._get_build_base_suite()
        cmd.append(f'{suite} "$CRAFT_PART_INSTALL" {self._get_default_mirror()}')
        return [
            " ".join(cmd),
            'rm -rf "$CRAFT_PART_INSTALL"/dev/*',
            'rm -rf "$CRAFT_PART_INSTALL"/etc/apt/sources.list.d/*',
            'rm -f "$CRAFT_PART_INSTALL"/etc/apt/sources.list',
        ]

    def _get_default_mirror(self) -> str:
        return (
            "http://archive.ubuntu.com/ubuntu"
            if self._part_info.target_arch in {"amd64", "i386"}
            else "http://ports.ubuntu.com/ubuntu-ports"
        )

    def _get_build_base_suite(self) -> str:
        if suite := distro.codename():
            return suite
        raise ValueError(
            "Suite could not be determined from /etc/os-release. Set 'mmdebstrap-suite' key."
        )
