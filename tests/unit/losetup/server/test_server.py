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

"""Unit tests for imagecraft/losetup/server/_server.py."""

import json
import pathlib
import socket
from unittest.mock import MagicMock, call

import pytest

from imagecraft.losetup.server._server import (
    _RequestHandler,
    _handle_attach,
    _handle_detach,
)


# ─── helpers ──────────────────────────────────────────────────────────────────


def _make_http_request(
    method: str,
    path: str,
    version: str = "HTTP/1.0",
    extra_headers: str = "",
) -> bytes:
    return (
        f"{method} {path} {version}\r\n"
        f"Host: localhost\r\n"
        f"{extra_headers}"
        f"\r\n"
    ).encode()


def _run_handler(
    project: str, container: str, request_bytes: bytes
) -> tuple[int, dict]:
    """
    Feed *request_bytes* into a _RequestHandler via a real socketpair.
    Returns (status_code, parsed_json_body).
    """
    client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.sendall(request_bytes)
        _RequestHandler(project, container, server, ("127.0.0.1", 0), None)
    finally:
        server.close()

    raw = b""
    client.settimeout(2.0)
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

    # Parse HTTP response: status line + headers + blank line + body
    header_end = raw.find(b"\r\n\r\n")
    header_section = raw[:header_end].decode()
    body = raw[header_end + 4 :]
    status_line = header_section.split("\r\n")[0]
    status_code = int(status_line.split()[1])
    return status_code, json.loads(body)


# ─── _handle_attach ───────────────────────────────────────────────────────────


class TestHandleAttach:
    def _setup(
        self,
        mocker,
        loop_dev="/dev/loop133",
        partitions=("loop133p1", "loop133p2"),
        existing_devices=None,
    ):
        mocker.patch(
            "imagecraft.losetup.server._server.convert_container_path_to_host_path",
            return_value=pathlib.Path("/host/disk.img"),
        )

        losetup_result = MagicMock()
        losetup_result.stdout = loop_dev + "\n"
        part_children = [{"name": p, "type": "part"} for p in partitions]
        loop_name = pathlib.Path(loop_dev).name
        lsblk_result = MagicMock()
        lsblk_result.stdout = json.dumps(
            {
                "blockdevices": [
                    {"name": loop_name, "type": "loop", "children": part_children}
                ]
            }
        )
        mock_run = mocker.patch(
            "imagecraft.losetup.server._server.subprocess.run",
            side_effect=[losetup_result, lsblk_result],
        )

        current_devs = existing_devices or {}
        mocker.patch(
            "imagecraft.losetup.server._server.lxd_get",
            return_value={"metadata": {"expanded_devices": current_devs}},
        )
        mock_patch = mocker.patch("imagecraft.losetup.server._server.lxd_patch")

        return mock_run, mock_patch

    def test_returns_device_paths(self, mocker):
        self._setup(mocker)

        result = _handle_attach("imagecraft", "my-container", "/root/disk.img")

        assert "/dev/imagecraft-loop0" in result
        assert "/dev/imagecraft-loop0p1" in result
        assert "/dev/imagecraft-loop0p2" in result

    def test_uses_slot_zero_when_no_existing_devices(self, mocker):
        self._setup(mocker, existing_devices={})

        result = _handle_attach("imagecraft", "my-container", "/root/disk.img")

        assert all("loop0" in p for p in result)

    def test_uses_next_free_slot_when_slot_zero_taken(self, mocker):
        existing = {
            "imagecraft-loop0": {"type": "unix-block", "path": "/dev/imagecraft-loop0"},
            "imagecraft-loop0p1": {
                "type": "unix-block",
                "path": "/dev/imagecraft-loop0p1",
            },
        }
        self._setup(mocker, existing_devices=existing)

        result = _handle_attach("imagecraft", "my-container", "/root/disk.img")

        assert any("loop1" in p for p in result)
        assert not any("loop0p" in p for p in result) or any(
            "loop1" in p for p in result
        )

    def test_patches_lxd_with_new_devices(self, mocker):
        _, mock_patch = self._setup(mocker, partitions=["loop133p1"])

        _handle_attach("imagecraft", "my-container", "/root/disk.img")

        mock_patch.assert_called_once()
        call_args = mock_patch.call_args
        devices_arg = call_args[0][1]["devices"]
        names = list(devices_arg.keys())
        assert any("imagecraft-loop" in n for n in names)

    def test_losetup_called_with_host_path(self, mocker):
        mock_run, _ = self._setup(mocker, partitions=[])

        _handle_attach("imagecraft", "my-container", "/root/disk.img")

        losetup_cmd = mock_run.call_args_list[0][0][0]
        assert losetup_cmd == [
            "losetup",
            "--find",
            "--show",
            "--partscan",
            "/host/disk.img",
        ]

    def test_no_partitions(self, mocker):
        self._setup(mocker, partitions=[])

        result = _handle_attach("imagecraft", "my-container", "/root/disk.img")

        assert result == ["/dev/imagecraft-loop0"]


# ─── _handle_detach ───────────────────────────────────────────────────────────


class TestHandleDetach:
    def _make_devices(self, loop_alias="imagecraft-loop0", loop_dev="/dev/loop133"):
        return {
            loop_alias: {
                "type": "unix-block",
                "path": f"/dev/{loop_alias}",
                "source": loop_dev,
            },
            f"{loop_alias}p1": {
                "type": "unix-block",
                "path": f"/dev/{loop_alias}p1",
                "source": f"{loop_dev}p1",
            },
            f"{loop_alias}p2": {
                "type": "unix-block",
                "path": f"/dev/{loop_alias}p2",
                "source": f"{loop_dev}p2",
            },
        }

    def _setup(self, mocker, devices=None):
        if devices is None:
            devices = self._make_devices()
        mocker.patch(
            "imagecraft.losetup.server._server.lxd_get",
            return_value={"metadata": {"expanded_devices": devices}},
        )
        mock_patch = mocker.patch("imagecraft.losetup.server._server.lxd_patch")
        mock_run = mocker.patch("imagecraft.losetup.server._server.subprocess.run")
        return mock_patch, mock_run

    def test_returns_removed_paths(self, mocker):
        mock_patch, _ = self._setup(mocker)

        result = _handle_detach(
            "imagecraft", "my-container", "/dev/imagecraft-loop0"
        )

        assert set(result) == {
            "/dev/imagecraft-loop0",
            "/dev/imagecraft-loop0p1",
            "/dev/imagecraft-loop0p2",
        }

    def test_runs_losetup_detach_on_host_device(self, mocker):
        _, mock_run = self._setup(mocker)

        _handle_detach("imagecraft", "my-container", "/dev/imagecraft-loop0")

        mock_run.assert_called_once_with(
            ["losetup", "--detach", "/dev/loop133"], check=True
        )

    def test_patches_lxd_with_none_to_remove_devices(self, mocker):
        mock_patch, _ = self._setup(mocker)

        _handle_detach("imagecraft", "my-container", "/dev/imagecraft-loop0")

        mock_patch.assert_called_once()
        devices_arg = mock_patch.call_args[0][1]["devices"]
        # All removed devices mapped to None
        assert all(v is None for v in devices_arg.values())
        assert "imagecraft-loop0" in devices_arg

    def test_raises_when_path_not_found(self, mocker):
        self._setup(mocker)

        with pytest.raises(ValueError, match="no unix-block device with path"):
            _handle_detach(
                "imagecraft", "my-container", "/dev/imagecraft-loop99"
            )

    def test_removes_partition_devices_with_loop_prefix(self, mocker):
        """Partition sources like /dev/loop133p1 are matched by prefix."""
        mock_patch, _ = self._setup(mocker)

        _handle_detach("imagecraft", "my-container", "/dev/imagecraft-loop0")

        devices_removed = mock_patch.call_args[0][1]["devices"]
        # Both the main device and its partitions should be removed
        assert "imagecraft-loop0p1" in devices_removed
        assert "imagecraft-loop0p2" in devices_removed

    def test_does_not_remove_unrelated_devices(self, mocker):
        devices = {
            **self._make_devices("imagecraft-loop0", "/dev/loop133"),
            "imagecraft-loop1": {
                "type": "unix-block",
                "path": "/dev/imagecraft-loop1",
                "source": "/dev/loop134",
            },
        }
        mock_patch, _ = self._setup(mocker, devices=devices)

        _handle_detach("imagecraft", "my-container", "/dev/imagecraft-loop0")

        devices_removed = mock_patch.call_args[0][1]["devices"]
        assert "imagecraft-loop1" not in devices_removed


# ─── _RequestHandler (via socket pair) ────────────────────────────────────────


class TestRequestHandler:
    def test_valid_attach_returns_200(self, mocker):
        mocker.patch(
            "imagecraft.losetup.server._server._handle_attach",
            return_value=["/dev/imagecraft-loop0", "/dev/imagecraft-loop0p1"],
        )

        req = _make_http_request("POST", "/1.0/attach?path=/root/disk.img")
        code, body = _run_handler("imagecraft", "my-container", req)

        assert code == 200
        assert body["metadata"] == ["/dev/imagecraft-loop0", "/dev/imagecraft-loop0p1"]
        assert body["status_code"] == 200

    def test_valid_detach_returns_200(self, mocker):
        mocker.patch(
            "imagecraft.losetup.server._server._handle_detach",
            return_value=["/dev/imagecraft-loop0"],
        )

        req = _make_http_request("POST", "/1.0/detach?path=/dev/imagecraft-loop0")
        code, body = _run_handler("imagecraft", "my-container", req)

        assert code == 200
        assert body["metadata"] == ["/dev/imagecraft-loop0"]

    def test_missing_path_param_returns_400(self, mocker):
        req = _make_http_request("POST", "/1.0/attach")
        code, body = _run_handler("imagecraft", "my-container", req)

        assert code == 400
        assert "path" in body["error"]

    def test_unknown_endpoint_returns_404(self, mocker):
        req = _make_http_request("POST", "/1.0/unknown?path=/x")
        code, body = _run_handler("imagecraft", "my-container", req)

        assert code == 404

    def test_handler_exception_returns_500(self, mocker):
        mocker.patch(
            "imagecraft.losetup.server._server._handle_attach",
            side_effect=RuntimeError("unexpected failure"),
        )

        req = _make_http_request("POST", "/1.0/attach?path=/root/disk.img")
        code, body = _run_handler("imagecraft", "my-container", req)

        assert code == 500
        assert "unexpected failure" in body["error"]

    def test_attach_receives_correct_args(self, mocker):
        mock_attach = mocker.patch(
            "imagecraft.losetup.server._server._handle_attach",
            return_value=[],
        )

        req = _make_http_request("POST", "/1.0/attach?path=/root/disk.img")
        _run_handler("imagecraft", "my-container", req)

        mock_attach.assert_called_once_with(
            "imagecraft", "my-container", "/root/disk.img"
        )

    def test_detach_receives_correct_args(self, mocker):
        mock_detach = mocker.patch(
            "imagecraft.losetup.server._server._handle_detach",
            return_value=[],
        )

        req = _make_http_request("POST", "/1.0/detach?path=/dev/imagecraft-loop0")
        _run_handler("imagecraft", "my-container", req)

        mock_detach.assert_called_once_with(
            "imagecraft", "my-container", "/dev/imagecraft-loop0"
        )
