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
from pydantic import AnyUrl, conlist
from typing_extensions import Self

from imagecraft.models.package_repository import get_main_package_repository
from imagecraft.ubuntu_image import ubuntu_image_cmds_build_rootfs

# A workaround for mypy false positives
# see https://github.com/samuelcolvin/pydantic/issues/975#issuecomment-551147305
# fmt: off
if TYPE_CHECKING:
    UniqueStrList = list[str]
else:
    UniqueStrList = conlist(str, unique_items=True, min_items=1)

if TYPE_CHECKING:
    UniqueUrlList = list[str]
else:
    UniqueUrlList = conlist(AnyUrl, unique_items=True, min_items=1)

class GerminateProperties(plugins.PluginProperties):
    """Supported attributes for the 'Germinate' section of the UbuntuSeedPlugin plugin."""

    urls: UniqueUrlList
    branch: str | None
    names: UniqueStrList
    vcs: bool | None = True

class UbuntuSeedPluginProperties(plugins.PluginProperties):
    """Supported attributes for the 'UbuntuSeedPlugin' plugin."""

    ubuntu_seed_pocket: str = "updates"
    ubuntu_seed_germinate: GerminateProperties
    ubuntu_seed_extra_snaps: UniqueStrList | None = None
    ubuntu_seed_extra_packages: UniqueStrList | None = None
    ubuntu_seed_kernel: str | None = None

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

        series = self._part_info.project_info.series

        source_branch = series
        branch = options.ubuntu_seed_germinate.branch
        if branch:
            source_branch = branch

        version = self._part_info.project_info.get_project_var("version", raw_read=True)

        main_repo = get_main_package_repository(self._part_info.project_info.package_repositories)

        components: list[str] = []
        main_repo_components = main_repo.components
        if main_repo_components:
            components = main_repo_components

        ubuntu_seed_cmd = ubuntu_image_cmds_build_rootfs(
            series,
            version,
            arch,
            main_repo.pocket.value,
            options.ubuntu_seed_germinate.urls,
            source_branch,
            options.ubuntu_seed_germinate.names,
            components,
            main_repo.flavor,
            main_repo.url,
            options.ubuntu_seed_pocket,
            options.ubuntu_seed_kernel,
            options.ubuntu_seed_extra_snaps,
            options.ubuntu_seed_extra_packages,
        )

        # We also need to make sure to prepare a proper fstab entry
        # as ubuntu-image doesn't do that for us in this case.
        ubuntu_seed_cmd.append(
            'echo "LABEL=writable   /    ext4   defaults    0 0\n"'
            " >$CRAFT_PART_BUILD/work/chroot/etc/fstab")

        return ubuntu_seed_cmd
