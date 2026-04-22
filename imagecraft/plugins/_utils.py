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

from craft_application.models.constraints import PROJECT_NAME_COMPILED_REGEX

VALID_RISKS = ["stable", "candidate", "beta", "edge"]


def validate_snap_refs(snaps: list[str]) -> list[str]:
    for snap in snaps:
        if snap.endswith(".snap"):
            continue

        parts = snap.split("/")

        name = parts[0]
        if not PROJECT_NAME_COMPILED_REGEX.match(name):
            raise ValueError(f"Invalid snap reference {snap}")

        if (channel_parts := parts[1:]) and (
            len(channel_parts) > 1 and not any(p in VALID_RISKS for p in channel_parts)
        ):
            raise ValueError(f"Invalid snap reference {snap}")

    return snaps


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
