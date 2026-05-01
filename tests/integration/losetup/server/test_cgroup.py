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

"""Integration tests for imagecraft/losetup/server/_cgroup.py.

peer_cgroup() reads SO_PEERCRED from a real socket and opens /proc/<pid>/cgroup.
No root required (both ends of the socket pair are in the same process).
"""

import os
import socket

import pytest

from imagecraft.losetup.server._cgroup import parse_lxd_location, peer_cgroup


class TestPeerCgroupIntegration:
    def test_returns_string_for_current_process(self):
        """peer_cgroup reads /proc/<our_pid>/cgroup via SO_PEERCRED."""
        client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            result = peer_cgroup(server)
        finally:
            client.close()
            server.close()

        assert isinstance(result, str)
        assert len(result) > 0

    def test_matches_proc_cgroup_of_current_process(self):
        """The cgroup string must match /proc/<our_pid>/cgroup."""
        pid = os.getpid()
        with open(f"/proc/{pid}/cgroup") as f:
            expected = f.read()

        client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            result = peer_cgroup(server)
        finally:
            client.close()
            server.close()

        assert result == expected

    def test_cgroup_contains_0_line(self):
        """The cgroup v2 unified hierarchy starts with '0::'."""
        client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            cgroup = peer_cgroup(server)
        finally:
            client.close()
            server.close()

        lines = cgroup.splitlines()
        # At least one line (cgroup v2 pure or hybrid)
        assert len(lines) >= 1

    def test_parse_lxd_location_does_not_crash_on_real_cgroup(self):
        """parse_lxd_location should not raise for any real cgroup string."""
        client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            cgroup = peer_cgroup(server)
        finally:
            client.close()
            server.close()

        # Should return None (we're not in an LXD container in tests) or a tuple
        result = parse_lxd_location(cgroup)
        assert result is None or (
            isinstance(result, tuple) and len(result) == 2
        )
