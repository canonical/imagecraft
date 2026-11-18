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

"""Extension mechanism for Imagecraft."""

from craft_application.extensions import (
    Extension,
    apply_extensions,
    get_extension_class,
    get_extension_names,
    get_extensions,
    register,
    reset,
    unregister,
)

__all__ = [
    "Extension",
    "apply_extensions",
    "get_extension_class",
    "get_extension_names",
    "get_extensions",
    "register",
    "reset",
    "unregister",
]
