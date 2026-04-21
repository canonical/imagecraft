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

"""The snap-preseed plugin."""

from typing import Literal, cast

from craft_parts.plugins import Plugin, PluginProperties
from typing_extensions import override


class SnapPreseedPluginProperties(PluginProperties, frozen=True):
    """Properties for the 'snap-preseed' plugin."""

    plugin: Literal["snap-preseed"] = "snap-preseed"

    snap_preseed_snaps: list[str]
    snap_preseed_channel: str | None = None
    snap_preseed_model_assert: str = ""
    snap_preseed_validation: Literal["ignore", "enforce"] = "ignore"
    snap_preseed_assertions: list[str] = []
    snap_preseed_revisions: str | None = None


class SnapPreseedPlugin(Plugin):
    """Prepare snaps for Ubuntu Classic images using 'snap prepare-image'."""

    properties_class = SnapPreseedPluginProperties

    @override
    def get_build_snaps(self) -> set[str]:
        """Return a set of required snaps to install in the build environment."""
        return set()

    @override
    def get_build_packages(self) -> set[str]:
        """Return a set of required packages to install in the build environment."""
        return set()

    @override
    def get_build_environment(self) -> dict[str, str]:
        """Return a dictionary with the environment to use in the build step."""
        return {}

    @override
    def get_build_commands(self) -> list[str]:
        """Return a list of commands to run during the build step."""
        options = cast(SnapPreseedPluginProperties, self._options)
        cmd = [
            "snap",
            "prepare-image",
            "--classic",
            f"--arch={self._part_info.target_arch}",
            f"--validation={options.snap_preseed_validation}",
        ]
        if options.snap_preseed_channel:
            cmd.append(f"--channel={options.snap_preseed_channel}")

        if options.snap_preseed_revisions:
            cmd.append(f"--revisions={options.snap_preseed_revisions}")

        cmd.extend(
            f"--assert={assertion}" for assertion in options.snap_preseed_assertions
        )

        cmd.extend(
            f"--snap={self._resolve_snap(snap)}" for snap in options.snap_preseed_snaps
        )

        cmd.append(
            f'"{options.snap_preseed_model_assert}" {self._part_info.part_install_dir}'
        )
        return [" ".join(cmd)]

    def _resolve_snap(self, snap: str) -> str:
        snap = snap.strip()
        if "/" in snap and not snap.endswith(".snap"):
            name, channel = snap.split("/", 1)
            snap = f"{name}={channel}"
        return snap
