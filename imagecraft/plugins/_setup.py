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

from craft_parts.plugins import register
from craft_parts.plugins.plugins import PluginType

from .bootloader import BootloaderPlugin
from .mmdebstrap import MmdebstrapPlugin


def get_app_plugins() -> dict[str, PluginType]:
    """Get Imagecraft-specific craft-parts plugins.

    :returns: A dict mapping plugin names to plugins
    """
    return {
        "mmdebstrap": MmdebstrapPlugin,
        "bootloader": BootloaderPlugin,
    }


def setup_plugins() -> None:
    """Register plugins specific to imagecraft."""
    register(get_app_plugins())
