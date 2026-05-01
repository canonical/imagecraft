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

"""losetup server: accept one connection, handle a loopback device request, then exit.

Socket activation is used (systemd passes a pre-bound socket via LISTEN_FDS).
"""

import http.server
import json
import os
import pathlib
import socket
import subprocess
import urllib.parse

from imagecraft.losetup.server._cgroup import parse_lxd_location, peer_cgroup
from imagecraft.losetup.server._lxd import (
    convert_container_path_to_host_path,
    find_free_loop_slot,
    lxd_get,
    lxd_patch,
)

_SD_LISTEN_FDS_START = 3


def _get_listening_socket() -> socket.socket:
    """Return the listening socket passed by systemd socket activation."""
    listen_pid = int(os.environ.get("LISTEN_PID", 0))
    listen_fds = int(os.environ.get("LISTEN_FDS", 0))
    if listen_pid != os.getpid() or listen_fds < 1:
        raise RuntimeError(
            f"expected socket activation (LISTEN_PID={listen_pid}, "
            f"LISTEN_FDS={listen_fds}, pid={os.getpid()})"
        )
    return socket.fromfd(_SD_LISTEN_FDS_START, socket.AF_UNIX, socket.SOCK_STREAM)


def _handle_attach(project: str, container: str, container_path: str) -> list[str]:
    host_path = convert_container_path_to_host_path(project, container, container_path)

    # Attach the image file as a loop device.
    loop_dev = subprocess.run(
        ["losetup", "--find", "--show", "--partscan", str(host_path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # Discover partitions via lsblk.
    lsblk_data = json.loads(
        subprocess.run(
            ["lsblk", "--json", "--output", "NAME,TYPE", loop_dev],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    loop_name = pathlib.Path(loop_dev).name  # e.g. "loop133"
    partitions = [
        child["name"]
        for child in lsblk_data["blockdevices"][0].get("children", [])
        if child.get("type") == "part"
    ]

    # Find a free in-container imagecraft-loopN slot.
    instance_data = lxd_get(f"/1.0/instances/{container}?project={project}")
    current_devices = instance_data["metadata"]["expanded_devices"]
    slot = find_free_loop_slot(current_devices)
    loop_alias = f"imagecraft-loop{slot}"  # e.g. "imagecraft-loop0"

    # Build the new device entries to add to the container.
    new_devices: dict[str, dict] = {
        loop_alias: {
            "type": "unix-block",
            "path": f"/dev/{loop_alias}",
            "source": loop_dev,
        }
    }
    for part_name in partitions:
        part_suffix = part_name[len(loop_name):]  # e.g. "p1"
        dev_alias = f"{loop_alias}{part_suffix}"
        new_devices[dev_alias] = {
            "type": "unix-block",
            "path": f"/dev/{dev_alias}",
            "source": f"/dev/{part_name}",
        }

    lxd_patch(f"/1.0/instances/{container}?project={project}", {"devices": new_devices})

    return [dev["path"] for dev in new_devices.values()]


def _handle_detach(project: str, container: str, container_dev_path: str) -> list[str]:
    # Find the LXD device name matching this in-container path.
    instance_data = lxd_get(f"/1.0/instances/{container}?project={project}")
    current_devices = instance_data["metadata"]["expanded_devices"]

    loop_dev = next(
        (
            dev["source"]
            for dev in current_devices.values()
            if dev.get("type") == "unix-block" and dev.get("path") == container_dev_path
        ),
        None,
    )
    if loop_dev is None:
        raise ValueError(
            f"no unix-block device with path {container_dev_path!r} in {container!r}"
        )

    # Remove all container devices backed by this loop device or its partitions.
    devices_to_remove = {
        name: None
        for name, dev in current_devices.items()
        if dev.get("type") == "unix-block"
        and (
            dev.get("source") == loop_dev
            or dev.get("source", "").startswith(loop_dev + "p")
        )
    }
    removed_paths = [current_devices[name]["path"] for name in devices_to_remove]
    lxd_patch(
        f"/1.0/instances/{container}?project={project}",
        {"devices": devices_to_remove},
    )

    subprocess.run(["losetup", "--detach", loop_dev], check=True)

    return removed_paths


class _RequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the loopserver REST API."""

    def __init__(self, project: str, container: str, *args, **kwargs) -> None:
        self._project = project
        self._container = container
        super().__init__(*args, **kwargs)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        path_values = params.get("path", [])
        if not path_values:
            self._send_error(400, "missing 'path' query parameter")
            return
        path = path_values[0]

        try:
            if parsed.path == "/1.0/attach":
                devices = _handle_attach(self._project, self._container, path)
            elif parsed.path == "/1.0/detach":
                devices = _handle_detach(self._project, self._container, path)
            else:
                self._send_error(404, f"unknown endpoint {parsed.path!r}")
                return
        except Exception as exc:  # noqa: BLE001
            self._send_error(500, str(exc))
            return

        self._send_json(200, {"status": "Success", "status_code": 200, "metadata": devices})

    def _send_json(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, code: int, message: str) -> None:
        self._send_json(code, {"error": message, "error_code": code})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # suppress default stderr logging


def main() -> None:
    """Entry point for the losetup server daemon."""
    sock = _get_listening_socket()
    conn, addr = sock.accept()
    with conn:
        location = parse_lxd_location(peer_cgroup(conn))
        if location is None or location[0] != "imagecraft":
            return
        project, container = location
        _RequestHandler(project, container, conn, addr, None)
    sock.close()
