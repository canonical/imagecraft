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

from imagecraft.plugins import gadget, ubuntu_bootstrap


def setup_plugins() -> None:
    """Register plugins specific to imagecraft."""
    plugins.register(
        {
            "gadget": gadget.GadgetPlugin,
            "ubuntu-bootstrap": ubuntu_bootstrap.UbuntuBootstrapPlugin,
        },
    )
