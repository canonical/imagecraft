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

"""Shared plugin utilities."""


def resolve_snap(snap: str) -> str:
    """Resolve a snap reference to the format expected by snap prepare-image.

    If the snap reference contains a channel (e.g. ``name/track/risk``), it is
    converted to the ``name=track/risk`` form that ``snap prepare-image``
    expects.  Plain snap names and local ``.snap`` file paths are returned
    unchanged.
    """
    snap = snap.strip()
    if "/" in snap and not snap.endswith(".snap"):
        name, channel = snap.split("/", 1)
        snap = f"{name}={channel}"
    return snap
