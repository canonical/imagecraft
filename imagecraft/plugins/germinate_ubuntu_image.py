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

"""Germinate/Ubuntu-image plugin."""

from typing import TYPE_CHECKING, Any, cast

from craft_parts import plugins
from pydantic import conlist
from typing_extensions import Self

from imagecraft.errors import NoValidSeriesError
from imagecraft.ubuntu_image import ubuntu_image_cmds_build_rootfs
from imagecraft.utils import craft_base_to_ubuntu_series

# A workaround for mypy false positives
# see https://github.com/samuelcolvin/pydantic/issues/975#issuecomment-551147305
# fmt: off
if TYPE_CHECKING:
    UniqueStrList = list[str]
else:
    UniqueStrList = conlist(str, unique_items=True, min_items=1)


class GerminateUbuntuImagePluginProperties(plugins.PluginProperties):
    """Supported attributes for the 'GerminateUbuntuImage' plugin."""

    germinate_sources: UniqueStrList
    germinate_source_branch: str | None
    germinate_seeds: UniqueStrList
    germinate_components: UniqueStrList
    germinate_pocket: str = "updates"

    # Optional, only to the ubuntu-image germination plugin
    germinate_extra_snaps: UniqueStrList | None = None
    germinate_active_kernel: str | None = None

    @classmethod
    def unmarshal(cls, data: dict[str, Any]) -> Self:
        """Populate properties from the part specification.

        :param data: A dictionary containing part properties.

        :return: The populated plugin properties data object.

        :raise pydantic.ValidationError: If validation fails.
        """
        plugin_data = plugins.base.extract_plugin_properties(
            data, plugin_name="germinate",
        )
        return cls(**plugin_data)


class GerminateUbuntuImagePlugin(plugins.Plugin):
    """Calls germinate through ubuntu-image to get a list of packages to install."""

    properties_class = GerminateUbuntuImagePluginProperties

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
        options = cast(GerminateUbuntuImagePluginProperties, self._options)

        germinate_arch = self._part_info.target_arch
        germinate_series = craft_base_to_ubuntu_series(
            self._part_info.project_info.base)
        if not germinate_series:
            raise NoValidSeriesError
        germinate_source_branch = options.germinate_source_branch

        if not germinate_source_branch:
            germinate_source_branch = germinate_series

        # The ubuntu-image germinate plugin operates on generating a
        # special image-definition file for the given germinate part
        # and then executing ubuntu-image only up until the stage where
        # the rootfs is generated
        germinate_cmd = ubuntu_image_cmds_build_rootfs(
            germinate_series,
            germinate_arch,
            options.germinate_sources,
            germinate_source_branch,
            options.germinate_seeds,
            options.germinate_components,
            options.germinate_pocket,
            options.germinate_active_kernel,
            options.germinate_extra_snaps,
        )

        # We also need to make sure to prepare a proper fstab entry
        # as ubuntu-image doesn't do that for us
        germinate_cmd.append(
            'echo "LABEL=writable   /    ext4   defaults    0 0\n"'
            " >$CRAFT_PART_BUILD/work/chroot/etc/fstab")

        return germinate_cmd
