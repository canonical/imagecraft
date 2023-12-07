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

from typing import Optional, cast
from craft_parts import plugins

from imagecraft.utils import craft_base_to_ubuntu_series


class GadgetPluginProperties(plugins.PluginProperties):
    gadget_target: Optional[str] = None

    @classmethod
    def unmarshal(cls, data):
        plugin_data = plugins.base.extract_plugin_properties(
            data, plugin_name="gadget"
        )
        return cls(**plugin_data)


class GadgetPlugin(plugins.Plugin):
    properties_class = GadgetPluginProperties

    def get_build_snaps(self):
        return {}

    def get_build_packages(self):
        # This list here should include all the base packages that are needed
        # to build the gadget. More specific packages to the actual gadget
        # build should be added manually by users.
        return {"make"}

    def get_build_environment(self):
        gadget_arch = self._part_info.target_arch
        gadget_series = craft_base_to_ubuntu_series(
            self._part_info.project_info.base)
        return {"ARCH": gadget_arch, "SERIES": gadget_series}

    def get_build_commands(self):
        options = cast(GadgetPluginProperties, self._options)

        gadget_target = options.gadget_target
        if gadget_target is None:
            gadget_target = ""

        gadget_cmd = [
            f"make {gadget_target}",
            "cp -a $CRAFT_PART_BUILD/install/* $CRAFT_PART_INSTALL/",
            # Temporary before we change ubuntu-image
            "cp $CRAFT_PART_INSTALL/meta/gadget.yaml $CRAFT_PART_INSTALL/",
        ]

        return gadget_cmd
