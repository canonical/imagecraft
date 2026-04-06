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

"""Unit tests for imagecraft/losetup/server/_cgroup.py."""

import pytest

from imagecraft.losetup.server._cgroup import parse_lxd_location


class TestParseLxdLocation:
    @pytest.mark.parametrize(
        "cgroup, expected",
        [
            # Happy path: project_container
            (
                "0::/lxc.payload.snapcraft_snapcraft-imagecraft-amd64-40774607"
                "/user.slice/user@0.service/init.scope\n",
                ("snapcraft", "snapcraft-imagecraft-amd64-40774607"),
            ),
            # Root cgroup – not in a container
            ("0::/\n", None),
            # User slice – no lxc.payload component
            ("0::/user.slice/user@1000.service\n", None),
            # Empty string
            ("", None),
            # No 0:: line at all
            ("1::/some/path\n2::/other\n", None),
            # Exact imagecraft project
            (
                "0::/lxc.payload.imagecraft_my-container\n",
                ("imagecraft", "my-container"),
            ),
        ],
    )
    def test_parse_various_inputs(self, cgroup, expected):
        assert parse_lxd_location(cgroup) == expected

    def test_innermost_wins_with_nested_containers(self):
        """Walk in reverse so the innermost lxc.payload wins."""
        cgroup = (
            "0::/lxc.payload.outer_cont1"
            "/lxc.payload.inner_cont2"
            "/some.scope\n"
        )
        assert parse_lxd_location(cgroup) == ("inner", "cont2")

    def test_picks_0_double_colon_line_only(self):
        """Lines that don't start with '0::' are ignored."""
        cgroup = "0::/some/path\n1::/other\n"
        # "some/path" has no lxc.payload component → None
        assert parse_lxd_location(cgroup) is None

    def test_multiple_lines_uses_0_line(self):
        """When multiple cgroup lines are present, 0:: is the one parsed."""
        cgroup = (
            "1::/lxc.payload.sneaky_container\n"
            "0::/lxc.payload.real_mybox\n"
        )
        assert parse_lxd_location(cgroup) == ("real", "mybox")

    def test_no_underscore_separator_returns_none(self):
        """If the component after lxc.payload has no underscore, skip it."""
        cgroup = "0::/lxc.payload.nounderscorehere\n"
        assert parse_lxd_location(cgroup) is None

    def test_container_name_may_contain_hyphens(self):
        cgroup = "0::/lxc.payload.myproject_my-long-container-name-01\n"
        assert parse_lxd_location(cgroup) == ("myproject", "my-long-container-name-01")
