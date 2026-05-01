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

"""Integration tests for imagecraft/losetup/server/_server.py.

Full round-trip: real socket pair, real HTTP request/response cycle,
with mocked LXD API and losetup calls so no LXD daemon is required.
Tests that need real losetup are marked requires_root.
"""

import json
import os
import socket
import threading

import pytest

from imagecraft.losetup.server._server import (
    _RequestHandler,
    _handle_attach,
    _handle_detach,
    main,
)


# ─── helpers ──────────────────────────────────────────────────────────────────


def _make_request(method: str, path: str) -> bytes:
    return (
        f"{method} {path} HTTP/1.0\r\n"
        f"Host: localhost\r\n"
        f"\r\n"
    ).encode()


def _send_and_recv(request_bytes: bytes, project: str, container: str) -> tuple[int, dict]:
    """Send *request_bytes* to a _RequestHandler and return (status, body)."""
    client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.sendall(request_bytes)
        _RequestHandler(project, container, server, ("", 0), None)
    finally:
        server.close()

    raw = b""
    client.settimeout(3.0)
    try:
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            raw += chunk
    except socket.timeout:
        pass
    finally:
        client.close()

    header_end = raw.find(b"\r\n\r\n")
    header_section = raw[:header_end].decode()
    body_bytes = raw[header_end + 4:]
    status_code = int(header_section.split("\r\n")[0].split()[1])
    return status_code, json.loads(body_bytes)


# ─── full HTTP round-trip (mocked LXD + subprocess) ──────────────────────────


class TestServerRoundTrip:
    def test_attach_full_cycle(self, mocker):
        mocker.patch(
            "imagecraft.losetup.server._server._handle_attach",
            return_value=["/dev/imagecraft-loop0", "/dev/imagecraft-loop0p1"],
        )

        req = _make_request("POST", "/1.0/attach?path=/root/project/disk.img")
        code, body = _send_and_recv(req, "imagecraft", "my-container")

        assert code == 200
        assert body["status_code"] == 200
        assert "/dev/imagecraft-loop0" in body["metadata"]
        assert "/dev/imagecraft-loop0p1" in body["metadata"]

    def test_detach_full_cycle(self, mocker):
        mocker.patch(
            "imagecraft.losetup.server._server._handle_detach",
            return_value=["/dev/imagecraft-loop0", "/dev/imagecraft-loop0p1"],
        )

        req = _make_request("POST", "/1.0/detach?path=/dev/imagecraft-loop0")
        code, body = _send_and_recv(req, "imagecraft", "my-container")

        assert code == 200
        assert "/dev/imagecraft-loop0" in body["metadata"]

    def test_missing_path_param(self):
        req = _make_request("POST", "/1.0/attach")
        code, body = _send_and_recv(req, "imagecraft", "my-container")

        assert code == 400
        assert body["error_code"] == 400

    def test_unknown_endpoint(self):
        req = _make_request("POST", "/1.0/badendpoint?path=/foo")
        code, body = _send_and_recv(req, "imagecraft", "my-container")

        assert code == 404

    def test_handler_exception_returns_500(self, mocker):
        mocker.patch(
            "imagecraft.losetup.server._server._handle_attach",
            side_effect=ValueError("boom"),
        )

        req = _make_request("POST", "/1.0/attach?path=/root/disk.img")
        code, body = _send_and_recv(req, "imagecraft", "my-container")

        assert code == 500
        assert "boom" in body["error"]


# ─── main() – non-imagecraft connection is silently rejected ──────────────────


class TestMainRejectsNonImagecraft:
    def test_non_imagecraft_project_closes_without_dispatch(self, mocker, tmp_path):
        """main() reads cgroup, finds project != 'imagecraft', returns immediately."""
        sock_path = tmp_path / "server.sock"

        # Create a listening socket ourselves
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(sock_path))
        listener.listen(1)

        mocker.patch(
            "imagecraft.losetup.server._server._get_listening_socket",
            return_value=listener,
        )
        # Peer cgroup claims a non-imagecraft project
        mocker.patch(
            "imagecraft.losetup.server._server.peer_cgroup",
            return_value="0::/lxc.payload.snapcraft_some-container\n",
        )
        mock_handler = mocker.patch(
            "imagecraft.losetup.server._server._RequestHandler"
        )

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(sock_path))

        main()

        client.close()
        listener.close()

        # Handler should NOT have been called
        mock_handler.assert_not_called()

    def test_imagecraft_project_dispatches_to_handler(self, mocker, tmp_path):
        """main() dispatches to _RequestHandler when project == 'imagecraft'."""
        sock_path = tmp_path / "server.sock"

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(sock_path))
        listener.listen(1)

        mocker.patch(
            "imagecraft.losetup.server._server._get_listening_socket",
            return_value=listener,
        )
        mocker.patch(
            "imagecraft.losetup.server._server.peer_cgroup",
            return_value="0::/lxc.payload.imagecraft_my-container\n",
        )
        mock_handler = mocker.patch(
            "imagecraft.losetup.server._server._RequestHandler"
        )

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(sock_path))

        main()

        client.close()
        listener.close()

        mock_handler.assert_called_once()
        call_args = mock_handler.call_args[0]
        assert call_args[0] == "imagecraft"
        assert call_args[1] == "my-container"

    def test_none_location_closes_without_dispatch(self, mocker, tmp_path):
        """main() returns immediately when parse_lxd_location returns None."""
        sock_path = tmp_path / "server.sock"

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(sock_path))
        listener.listen(1)

        mocker.patch(
            "imagecraft.losetup.server._server._get_listening_socket",
            return_value=listener,
        )
        mocker.patch(
            "imagecraft.losetup.server._server.peer_cgroup",
            return_value="0::/\n",  # not in container
        )
        mock_handler = mocker.patch(
            "imagecraft.losetup.server._server._RequestHandler"
        )

        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(str(sock_path))

        main()

        client.close()
        listener.close()

        mock_handler.assert_not_called()
