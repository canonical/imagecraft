# This file is part of imagecraft.
#
# Copyright 2026 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import pytest
from imagecraft.plugins._utils import resolve_snap, validate_snap_refs


@pytest.mark.parametrize(
    ("snap", "expected"),
    [
        ("core24", "core24"),
        ("  core24  ", "core24"),
        ("./my-snap_1.0_amd64.snap", "./my-snap_1.0_amd64.snap"),
        ("hello-world/latest/stable", "hello-world=latest/stable"),
        ("core24/stable", "core24=stable"),
        ("  hello-world/latest/stable  ", "hello-world=latest/stable"),
    ],
)
def test_resolve_snap(snap, expected):
    assert resolve_snap(snap) == expected


def test_validate_snap_ref_valid():
    valid_refs = [
        "hello-world",
        "hello-world/edge",
        "hello-world/24",
        "hello-world/stable/hotfix",
        "hello-world/24/beta/hotfix",
        "my-snap-123",
        "/path/to/local.snap",
    ]

    assert validate_snap_refs(valid_refs) == valid_refs


@pytest.mark.parametrize(
    "invalid_ref",
    [
        "123",
        "has--double-dash",
        "hello-world/track/notarisk",
        "this-is-too-long-123456789234567891234567",
        "hello-world/track/stable/branch/notallowed",
    ],
)
def test_validate_snap_ref_invalid(invalid_ref):
    with pytest.raises(ValueError, match="Invalid snap reference"):
        validate_snap_refs([invalid_ref])
