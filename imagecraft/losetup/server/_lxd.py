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

"""LXD REST API helpers and path translation."""

import http.client
import json
import os
import pathlib
import socket

LXD_SOCKET = "/var/snap/lxd/common/lxd/unix.socket"


def _lxd_connect() -> http.client.HTTPConnection:
    conn = http.client.HTTPConnection("lxd")
    conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.sock.connect(LXD_SOCKET)
    return conn


def lxd_get(path: str) -> dict:
    """Make a GET request to the LXD REST API and return the parsed response."""
    conn = _lxd_connect()
    conn.request("GET", path)
    return json.loads(conn.getresponse().read())


def lxd_patch(path: str, body: dict) -> dict:
    """Make a PATCH request to the LXD REST API and return the parsed response."""
    conn = _lxd_connect()
    data = json.dumps(body).encode()
    conn.request("PATCH", path, body=data, headers={"Content-Type": "application/json"})
    return json.loads(conn.getresponse().read())


def find_free_loop_slot(devices: dict) -> int:
    """Find the smallest N such that no ``imagecraft-loopN*`` device exists."""
    used: set[int] = set()
    for name in devices:
        if name.startswith("imagecraft-loop"):
            num_str = name[len("imagecraft-loop"):].split("p")[0]
            if num_str.isdigit():
                used.add(int(num_str))
    n = 0
    while n in used:
        n += 1
    return n


def convert_container_path_to_host_path(
    project: str, container: str, container_path: str
) -> pathlib.Path:
    """Translate *container_path* to an absolute path on the host.

    Queries the LXD API for the container's disk devices, finds the one with
    the longest ``path`` prefix that matches *container_path* and has a
    ``source``, then substitutes that source for the prefix.

    Raises ``ValueError`` if no sourced device covers the given path.
    """
    data = lxd_get(f"/1.0/instances/{container}?project={project}")
    devices = data["metadata"]["expanded_devices"]

    # Collect disk devices that bind-mount a host source path.
    sourced = [
        (dev["path"].rstrip("/"), dev["source"])
        for dev in devices.values()
        if dev.get("type") == "disk" and "source" in dev
    ]

    # Normalise the container path and find the longest matching mount prefix.
    norm = os.path.normpath(container_path)
    best_mount = best_source = None
    for mount, source in sourced:
        if norm == mount or norm.startswith(mount + "/"):
            if best_mount is None or len(mount) > len(best_mount):
                best_mount = mount
                best_source = source

    if best_mount is None:
        raise ValueError(
            f"{container_path!r} is not under any sourced device in {container!r}"
        )

    relative = norm[len(best_mount):]  # may be "" if exact match
    return pathlib.Path(best_source + relative)
