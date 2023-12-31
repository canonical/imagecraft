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

"""UbuntuSeed plugin."""

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


class UbuntuSeedPluginProperties(plugins.PluginProperties):
    """Supported attributes for the 'UbuntuSeedPlugin' plugin."""

    ubuntu_seed_sources: UniqueStrList
    ubuntu_seed_source_branch: str | None
    ubuntu_seed_seeds: UniqueStrList
    ubuntu_seed_components: UniqueStrList
    ubuntu_seed_pocket: str = "updates"

    ubuntu_seed_extra_snaps: UniqueStrList | None = None
    ubuntu_seed_active_kernel: str | None = None

    @classmethod
    def unmarshal(cls, data: dict[str, Any]) -> Self:
        """Populate properties from the part specification.

        :param data: A dictionary containing part properties.

        :return: The populated plugin properties data object.

        :raise pydantic.ValidationError: If validation fails.
        """
        plugin_data = plugins.base.extract_plugin_properties(
            data, plugin_name="ubuntu-seed",
        )
        return cls(**plugin_data)


class UbuntuSeedPlugin(plugins.Plugin):
    """Builds a rootfs via ubuntu-image."""

    properties_class = UbuntuSeedPluginProperties

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
        options = cast(UbuntuSeedPluginProperties, self._options)

        arch = self._part_info.target_arch
        series = craft_base_to_ubuntu_series(
            self._part_info.project_info.base)
        if not series:
            raise NoValidSeriesError

        source_branch = options.ubuntu_seed_source_branch
        if not source_branch:
            source_branch = series

        ubuntu_seed_cmd = ubuntu_image_cmds_build_rootfs(
            series,
            arch,
            options.ubuntu_seed_sources,
            source_branch,
            options.ubuntu_seed_seeds,
            options.ubuntu_seed_components,
            options.ubuntu_seed_pocket,
            options.ubuntu_seed_active_kernel,
            options.ubuntu_seed_extra_snaps,
        )

        # We also need to make sure to prepare a proper fstab entry
        # as ubuntu-image doesn't do that for us in this case.
        ubuntu_seed_cmd.append(
            'echo "LABEL=writable   /    ext4   defaults    0 0\n"'
            " >$CRAFT_PART_BUILD/work/chroot/etc/fstab")

        return ubuntu_seed_cmd
