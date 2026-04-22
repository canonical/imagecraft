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
from imagecraft.plugins._utils import resolve_snap


@pytest.mark.parametrize(
    ("snap", "expected"),
    [
        # Plain snap name – unchanged
        ("core24", "core24"),
        # Leading/trailing whitespace is stripped
        ("  core24  ", "core24"),
        # Local .snap file path with a slash – unchanged (not a channel)
        ("./my-snap_1.0_amd64.snap", "./my-snap_1.0_amd64.snap"),
        # snap name with channel – converted to name=channel
        ("hello-world/latest/stable", "hello-world=latest/stable"),
        ("core24/stable", "core24=stable"),
        # snap name with channel and leading whitespace
        ("  hello-world/latest/stable  ", "hello-world=latest/stable"),
    ],
)
def test_resolve_snap(snap, expected):
    assert resolve_snap(snap) == expected
