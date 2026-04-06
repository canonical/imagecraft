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

"""losetup client: attach/detach loop devices via the loopserver REST API when
running inside an LXD container, or via the real losetup binary otherwise.
"""

import http.client
import json
import pathlib
import socket
import subprocess
import urllib.parse

from craft_cli import emit

_LXD_GUEST_SOCK = "/dev/lxd/sock"
_LOOPSERVER_SOCK = "/dev/losetup/sock"


def _is_lxd_container() -> bool:
    """Return True if we are running inside an LXD container."""
    if not pathlib.Path(_LXD_GUEST_SOCK).exists():
        emit.debug(f"LXD guest socket {_LXD_GUEST_SOCK!r} not found; not in a container")
        return False
    try:
        conn = http.client.HTTPConnection("lxd")
        conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        conn.sock.connect(_LXD_GUEST_SOCK)
        conn.request("GET", "/1.0")
        data = json.loads(conn.getresponse().read())
        instance_type = data.get("instance_type")
        if instance_type == "container":
            emit.debug(
                f"Detected LXD container via {_LXD_GUEST_SOCK!r} "
                f"(instance_type={instance_type!r})"
            )
            return True
        emit.debug(
            f"LXD guest socket present but instance_type={instance_type!r}; "
            "not treating as container"
        )
        return False
    except Exception as exc:  # noqa: BLE001
        emit.debug(
            f"Failed to query LXD guest socket {_LXD_GUEST_SOCK!r}: {exc}; "
            "assuming not in a container"
        )
        return False


def _loopserver_request(endpoint: str, path: str) -> list[str]:
    """POST to the loopserver REST API and return the metadata list."""
    query = urllib.parse.urlencode({"path": path})
    conn = http.client.HTTPConnection("loopserver")
    conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.sock.connect(_LOOPSERVER_SOCK)
    conn.request("POST", f"{endpoint}?{query}")
    response = json.loads(conn.getresponse().read())
    if response.get("error_code"):
        raise RuntimeError(response.get("error", "unknown error from loopserver"))
    return response["metadata"]


def _losetup_attach(path: pathlib.Path) -> list[str]:
    """Attach *path* as a loop device using the real losetup, return all device paths."""
    loop_dev = subprocess.run(
        ["losetup", "--find", "--show", "--partscan", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    lsblk_data = json.loads(
        subprocess.run(
            ["lsblk", "--json", "--output", "NAME,TYPE", loop_dev],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    devices = [loop_dev]
    for child in lsblk_data["blockdevices"][0].get("children", []):
        if child.get("type") == "part":
            devices.append(f"/dev/{child['name']}")
    return devices


def _losetup_detach(device: str) -> list[str]:
    """Detach *device* using the real losetup, return all device paths that were removed."""
    lsblk_data = json.loads(
        subprocess.run(
            ["lsblk", "--json", "--output", "NAME,TYPE", device],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    devices = [device]
    for child in lsblk_data["blockdevices"][0].get("children", []):
        if child.get("type") == "part":
            devices.append(f"/dev/{child['name']}")

    subprocess.run(["losetup", "--detach", device], check=True)
    return devices


def attach(path: pathlib.Path) -> list[str]:
    """Attach *path* as a loop device and return all device paths (loop + partitions).

    When running inside an LXD container, delegates to the loopserver REST API.
    Otherwise calls the real losetup binary directly.
    """
    if _is_lxd_container():
        emit.debug(f"Attaching {path} via loopserver at {_LOOPSERVER_SOCK!r}")
        return _loopserver_request("/1.0/attach", str(path))
    emit.debug(f"Attaching {path} via losetup directly")
    return _losetup_attach(path)


def detach(device: str) -> list[str]:
    """Detach the loop device *device* and return all device paths that were removed.

    When running inside an LXD container, delegates to the loopserver REST API.
    Otherwise calls the real losetup binary directly.
    """
    if _is_lxd_container():
        emit.debug(f"Detaching {device} via loopserver at {_LOOPSERVER_SOCK!r}")
        return _loopserver_request("/1.0/detach", device)
    emit.debug(f"Detaching {device} via losetup directly")
    return _losetup_detach(device)


__all__ = ["attach", "detach"]
