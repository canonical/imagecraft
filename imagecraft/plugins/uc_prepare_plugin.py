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

"""The uc-prepare plugin."""

from typing import Literal, cast

from craft_parts.plugins import Plugin, PluginProperties
from pydantic import model_validator
from typing_extensions import Self, override

from ._utils import resolve_snap


class UcPreparePluginProperties(PluginProperties, frozen=True):
    """Properties for the uc-prepare plugin."""

    plugin: Literal["uc-prepare"] = "uc-prepare"

    uc_prepare_model_assert: str
    uc_prepare_snaps: list[str] = []
    uc_prepare_channel: str | None = None
    uc_prepare_validation: Literal["ignore", "enforce"] = "ignore"
    uc_prepare_assertions: list[str] = []
    uc_prepare_revisions: str | None = None
    uc_prepare_preseed: bool = False
    uc_prepare_preseed_sign_key: str | None = None
    uc_prepare_apparmor_features_dir: str | None = None
    uc_prepare_sysfs_overlay: str | None = None

    @model_validator(mode="after")
    def sign_key_requires_preseed(self) -> Self:
        """preseed-sign-key requires preseed to be enabled."""
        if self.uc_prepare_preseed_sign_key and not self.uc_prepare_preseed:
            raise ValueError(
                "uc-prepare-preseed-sign-key cannot be used without uc-prepare-preseed"
            )
        return self

    @model_validator(mode="after")
    def sysfs_overlay_requires_preseed(self) -> Self:
        """sysfs-overlay requires preseed to be enabled."""
        if self.uc_prepare_sysfs_overlay and not self.uc_prepare_preseed:
            raise ValueError(
                "uc-prepare-sysfs-overlay cannot be used without uc-prepare-preseed"
            )
        return self


class UcPreparePlugin(Plugin):
    """Prepare snaps for Ubuntu Core using 'snap prepare-image'."""

    properties_class = UcPreparePluginProperties

    @override
    def get_build_snaps(self) -> set[str]:
        """Return a set of required snaps to install in the build environment."""
        return set()

    @override
    def get_build_packages(self) -> set[str]:
        """Return a set of required packages to install in the build environment."""
        options = cast(UcPreparePluginProperties, self._options)
        if (
            options.uc_prepare_preseed
            and self._part_info.host_arch != self._part_info.target_arch
        ):
            return {"qemu-user-static"}
        return set()

    @override
    def get_build_environment(self) -> dict[str, str]:
        """Return a dictionary with the environment to use in the build step."""
        return {}

    @override
    def get_build_commands(self) -> list[str]:
        """Return a list of commands to run during the build step."""
        options = cast(UcPreparePluginProperties, self._options)

        cmd = ["snap", "prepare-image"]

        if options.uc_prepare_preseed:
            cmd.append("--preseed")

        if options.uc_prepare_preseed_sign_key:
            cmd.append(f"--preseed-sign-key={options.uc_prepare_preseed_sign_key}")

        if options.uc_prepare_apparmor_features_dir:
            cmd.append(
                f"--apparmor-features-dir={options.uc_prepare_apparmor_features_dir}"
            )

        if options.uc_prepare_sysfs_overlay:
            cmd.append(f"--sysfs-overlay={options.uc_prepare_sysfs_overlay}")

        cmd.append(f"--validation={options.uc_prepare_validation}")

        if options.uc_prepare_channel:
            cmd.append(f"--channel={options.uc_prepare_channel}")

        if options.uc_prepare_revisions:
            cmd.append(f"--revisions={options.uc_prepare_revisions}")

        cmd.extend(
            f"--assert={assertion}" for assertion in options.uc_prepare_assertions
        )

        cmd.extend(
            f"--snap={resolve_snap(snap)}" for snap in options.uc_prepare_snaps
        )

        cmd.append(
            f"{options.uc_prepare_model_assert} {self._part_info.part_install_dir}"
        )

        return [" ".join(cmd)]
