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

"""Imagecraft error definitions."""

from craft_cli import CraftError


class ImagecraftError(CraftError):
    """Base class for all imagecraft errors."""


class UbuntuImageError(ImagecraftError):
    """Raised when an error occurs while using ubuntu-image."""


class NoValidSeriesError(ImagecraftError):
    """Error finding project file."""

    def __init__(self) -> None:
        super().__init__("No valid series could be found for the given version")
