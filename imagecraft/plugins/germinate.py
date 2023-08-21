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

from craft_parts import plugins

class GerminatePluginProperties(plugins.PluginProperties):
    @classmethod
    def unmarshal(cls, data):
        plugin_data = plugins.base.extract_plugin_properties(
            data, plugin_name="germinate"
        )
        return cls(**plugin_data)


class GerminatePlugin(plugins.Plugin):
    properties_class = GerminatePluginProperties

    def get_build_snaps(self):
        return []

    def get_build_packages(self):
        return []

    def get_build_environment(self):
        return {}

    def get_build_commands(self):
        return ["echo 'We will be germinating soon!'"]