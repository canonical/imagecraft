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

"""cgroup v2 helpers for determining LXD container membership."""

import socket
import struct


def peer_cgroup(conn: socket.socket) -> str:
    """Return the cgroup v2 string for the process on the other end of *conn*."""
    cred = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    pid, _uid, _gid = struct.unpack("3i", cred)
    with open(f"/proc/{pid}/cgroup") as f:
        return f.read()


def parse_lxd_location(cgroup: str) -> tuple[str, str] | None:
    """Return (project, container) from a cgroup v2 string, or None.

    The cgroup v2 entry always has the form ``0::$PATH``.  Within that path we
    walk the components in reverse to find the innermost one that begins with
    ``lxc.payload.``, then split it to recover the LXD project and container.
    LXD project names are restricted to [a-zA-Z0-9-] (no underscores), so the
    first ``_`` is always the delimiter between project and container name.
    """
    for line in cgroup.splitlines():
        if not line.startswith("0::"):
            continue
        path = line[len("0::"):]
        for component in reversed(path.split("/")):
            if not component.startswith("lxc.payload."):
                continue
            project_container = component.split(".")[-1]
            parts = project_container.split("_", 1)
            if len(parts) == 2:
                return parts[0], parts[1]
        break  # found the v2 line but no lxc.payload component
    return None
