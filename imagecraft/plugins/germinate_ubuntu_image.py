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

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, cast
from pydantic import conlist
from craft_parts import plugins


from imagecraft.ubuntu_image import ubuntu_image_cmds_build_rootfs
from imagecraft.utils import craft_base_to_ubuntu_series

# A workaround for mypy false positives
# see https://github.com/samuelcolvin/pydantic/issues/975#issuecomment-551147305
# fmt: off
if TYPE_CHECKING:
    UniqueStrList = List[str]
else:
    UniqueStrList = conlist(str, unique_items=True, min_items=1)


class GerminateUbuntuImagePluginProperties(plugins.PluginProperties):
    germinate_sources: UniqueStrList
    germinate_source_branch: Optional[str]
    germinate_seeds: UniqueStrList
    germinate_components: UniqueStrList
    germinate_pocket: Optional[str] = "updates"

    # Optional, only to the ubuntu-image germination plugin
    germinate_extra_snaps: Optional[UniqueStrList] = None
    germinate_active_kernel: Optional[str] = None

    @classmethod
    def unmarshal(cls, data: Dict[str, Any]):
        plugin_data = plugins.base.extract_plugin_properties(
            data, plugin_name="germinate"
        )
        return cls(**plugin_data)


class GerminateUbuntuImagePlugin(plugins.Plugin):
    properties_class = GerminateUbuntuImagePluginProperties

    def get_build_snaps(self) -> Set[str]:
        return set("ubuntu-image")

    def get_build_packages(self) -> Set[str]:
        return set()

    def get_build_environment(self) -> Dict[str, str]:
        return {}

    def get_build_commands(self) -> List[str]:
        options = cast(GerminateUbuntuImagePluginProperties, self._options)

        germinate_arch = self._part_info.target_arch
        germinate_series = craft_base_to_ubuntu_series(
            self._part_info.project_info.base)
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
            "echo \"LABEL=writable   /    ext4   defaults    0 0\n\""
            " >$CRAFT_PART_BUILD/work/chroot/etc/fstab")

        return germinate_cmd
