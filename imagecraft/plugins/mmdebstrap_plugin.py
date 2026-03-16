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

from typing import Literal, cast, override

from craft_parts.plugins import Plugin
from craft_parts.plugins.properties import PluginProperties


class MmdebstrapPluginProperties(PluginProperties, frozen=True):
    """Properties for the mmdebstrap plugin."""

    plugin: Literal["mmdebstrap"] = "mmdebstrap"

    mmdebstrap_suite: str
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
    ] = "minbase"
    mmdebstrap_mode: Literal[
        "auto", "sudo", "root", "unshare", "fakeroot", "fakechroot", "chrootless"
    ] = "auto"
    mmdebstrap_format: Literal[
        "auto", "directory", "dir", "tar", "squashfs", "sqfs", "ext2", "null"
    ] = "dir"
    mmdebstrap_include: list[str] = []
    mmdebstrap_mirror: str | None = None


class MmdebstrapPlugin(Plugin):
    """A plugin to create a root filesystem using mmdebstrap.

    This plugin uses the following plugin-specific keywords:

    - mmdebstrap-suite
     (string, required)
     The suite to bootstrap (e.g. 'noble', 'jammy').

    - mmdebstrap-mode
      (string)
      The bootstrap variant. Default is 'minbase'.

    - mmdebstrap-mode
      (string)
      The execution mode. Default is 'auto'.

    - mmdebstrap-format
      (string)
      The output format. Default is 'dir'.

    - mmdebstrap-include
      (list of strings)
      Additional packages to include in the bootstrap.

    - mmdebstrap-mirror
      (string)
      The mirror URL. Defaults to "http://archive.ubuntu.com/ubuntu" or
      "http://ports.ubuntu.com/ubuntu-ports".
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

        mirror = options.mmdebstrap_mirror or self._get_default_mirror()
        cmd: list[str] = [
            "mmdebstrap",
            "--arch=$CRAFT_ARCH_BUILD_FOR",
            f"--mode={options.mmdebstrap_mode}",
            f"--variant={options.mmdebstrap_variant}",
            f"--format={options.mmdebstrap_format}",
            options.mmdebstrap_suite,
            '"$CRAFT_PART_INSTALL"',
            mirror,
        ]

        if options.mmdebstrap_include:
            cmd.append(f"--include={','.join(options.mmdebstrap_include)}")

        return [" ".join(cmd), 'rm -r "$CRAFT_PART_INSTALL"/dev/*']

    def _get_default_mirror(self) -> str:
        return (
            "http://archive.ubuntu.com/ubuntu"
            if self._part_info.project_info.target_arch in {"amd64", "i386"}
            else "http://ports.ubuntu.com/ubuntu-ports"
        )
