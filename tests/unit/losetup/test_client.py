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

"""Unit tests for imagecraft/losetup/__init__.py (the losetup client)."""

import json
import pathlib
import subprocess
from unittest.mock import MagicMock

import pytest

import imagecraft.losetup as losetup_module
from imagecraft.losetup import (
    _LXD_GUEST_SOCK,
    _LOOPSERVER_SOCK,
    _is_lxd_container,
    _loopserver_request,
    _losetup_attach,
    _losetup_detach,
    attach,
    detach,
)


# ─── constants ────────────────────────────────────────────────────────────────


def test_lxd_guest_sock_constant():
    assert _LXD_GUEST_SOCK == "/dev/lxd/sock"


def test_loopserver_sock_constant():
    assert _LOOPSERVER_SOCK == "/dev/losetup/sock"


# ─── _is_lxd_container ────────────────────────────────────────────────────────


class TestIsLxdContainer:
    def test_returns_false_when_sock_missing(self, mocker, tmp_path):
        mocker.patch("imagecraft.losetup._LXD_GUEST_SOCK", str(tmp_path / "nonexistent"))
        mocker.patch("craft_cli.emit.debug")
        assert _is_lxd_container() is False

    def test_returns_true_when_instance_type_container(self, mocker, tmp_path):
        sock_path = tmp_path / "sock"
        sock_path.touch()
        mocker.patch("imagecraft.losetup._LXD_GUEST_SOCK", str(sock_path))
        mocker.patch("craft_cli.emit.debug")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"instance_type": "container"}
        ).encode()
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value = mock_response
        mocker.patch(
            "imagecraft.losetup.http.client.HTTPConnection", return_value=mock_conn
        )
        mocker.patch("imagecraft.losetup.socket.socket")

        assert _is_lxd_container() is True

    def test_returns_false_when_instance_type_vm(self, mocker, tmp_path):
        sock_path = tmp_path / "sock"
        sock_path.touch()
        mocker.patch("imagecraft.losetup._LXD_GUEST_SOCK", str(sock_path))
        mocker.patch("craft_cli.emit.debug")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"instance_type": "virtual-machine"}
        ).encode()
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value = mock_response
        mocker.patch(
            "imagecraft.losetup.http.client.HTTPConnection", return_value=mock_conn
        )
        mocker.patch("imagecraft.losetup.socket.socket")

        assert _is_lxd_container() is False

    def test_returns_false_when_instance_type_missing(self, mocker, tmp_path):
        sock_path = tmp_path / "sock"
        sock_path.touch()
        mocker.patch("imagecraft.losetup._LXD_GUEST_SOCK", str(sock_path))
        mocker.patch("craft_cli.emit.debug")

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({}).encode()
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value = mock_response
        mocker.patch(
            "imagecraft.losetup.http.client.HTTPConnection", return_value=mock_conn
        )
        mocker.patch("imagecraft.losetup.socket.socket")

        assert _is_lxd_container() is False

    def test_returns_false_on_connection_error(self, mocker, tmp_path):
        sock_path = tmp_path / "sock"
        sock_path.touch()
        mocker.patch("imagecraft.losetup._LXD_GUEST_SOCK", str(sock_path))
        mocker.patch("craft_cli.emit.debug")

        mock_sock = MagicMock()
        mock_sock.connect.side_effect = ConnectionRefusedError("refused")
        mocker.patch("imagecraft.losetup.socket.socket", return_value=mock_sock)
        mocker.patch("imagecraft.losetup.http.client.HTTPConnection")

        assert _is_lxd_container() is False

    def test_returns_false_on_json_error(self, mocker, tmp_path):
        sock_path = tmp_path / "sock"
        sock_path.touch()
        mocker.patch("imagecraft.losetup._LXD_GUEST_SOCK", str(sock_path))
        mocker.patch("craft_cli.emit.debug")

        mock_response = MagicMock()
        mock_response.read.return_value = b"not-json"
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value = mock_response
        mocker.patch(
            "imagecraft.losetup.http.client.HTTPConnection", return_value=mock_conn
        )
        mocker.patch("imagecraft.losetup.socket.socket")

        assert _is_lxd_container() is False

    def test_never_raises_on_connection_failure(self, mocker, tmp_path):
        """Exceptions during the HTTP call (inside the try block) never propagate."""
        sock_path = tmp_path / "sock"
        sock_path.touch()
        mocker.patch("imagecraft.losetup._LXD_GUEST_SOCK", str(sock_path))
        mocker.patch("craft_cli.emit.debug")

        mock_conn = MagicMock()
        mock_conn.getresponse.side_effect = OSError("pipe broken")
        mocker.patch(
            "imagecraft.losetup.http.client.HTTPConnection", return_value=mock_conn
        )
        mocker.patch("imagecraft.losetup.socket.socket")

        result = _is_lxd_container()
        assert result is False


# ─── _loopserver_request ──────────────────────────────────────────────────────


class TestLoopserverRequest:
    def _make_conn(self, mocker, response_data: dict):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(response_data).encode()
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value = mock_response
        mocker.patch(
            "imagecraft.losetup.http.client.HTTPConnection", return_value=mock_conn
        )
        mocker.patch("imagecraft.losetup.socket.socket")
        return mock_conn

    def test_returns_metadata_on_success(self, mocker):
        expected = ["/dev/imagecraft-loop0", "/dev/imagecraft-loop0p1"]
        self._make_conn(mocker, {"status_code": 200, "metadata": expected})

        result = _loopserver_request("/1.0/attach", "/root/disk.img")

        assert result == expected

    def test_raises_on_error_code(self, mocker):
        self._make_conn(
            mocker,
            {"error_code": 500, "error": "losetup failed"},
        )

        with pytest.raises(RuntimeError, match="losetup failed"):
            _loopserver_request("/1.0/attach", "/root/disk.img")

    def test_raises_with_fallback_message_when_no_error_field(self, mocker):
        self._make_conn(mocker, {"error_code": 500})

        with pytest.raises(RuntimeError, match="unknown error from loopserver"):
            _loopserver_request("/1.0/attach", "/root/disk.img")

    def test_connects_to_loopserver_sock(self, mocker):
        mock_sock = MagicMock()
        mocker.patch("imagecraft.losetup.socket.socket", return_value=mock_sock)
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value.read.return_value = json.dumps(
            {"metadata": []}
        ).encode()
        mocker.patch(
            "imagecraft.losetup.http.client.HTTPConnection", return_value=mock_conn
        )

        _loopserver_request("/1.0/attach", "/some/path")

        mock_sock.connect.assert_called_once_with(_LOOPSERVER_SOCK)

    def test_path_encoded_in_query(self, mocker):
        mock_sock = MagicMock()
        mocker.patch("imagecraft.losetup.socket.socket", return_value=mock_sock)
        mock_conn = MagicMock()
        mock_conn.getresponse.return_value.read.return_value = json.dumps(
            {"metadata": []}
        ).encode()
        mocker.patch(
            "imagecraft.losetup.http.client.HTTPConnection", return_value=mock_conn
        )

        _loopserver_request("/1.0/attach", "/root/my image.img")

        url = mock_conn.request.call_args[0][1]
        assert "path=%2Froot%2Fmy+image.img" in url or "path=%2Froot%2Fmy%20image.img" in url


# ─── _losetup_attach ──────────────────────────────────────────────────────────


class TestLosetupAttach:
    def _make_run(self, mocker, loop_dev="/dev/loop8", partitions=None):
        partitions = partitions or []
        children = [{"name": f"loop8{p}", "type": "part"} for p in partitions]
        lsblk_output = json.dumps(
            {
                "blockdevices": [
                    {"name": "loop8", "type": "loop", "children": children}
                ]
            }
        )
        losetup_result = MagicMock()
        losetup_result.stdout = loop_dev + "\n"
        lsblk_result = MagicMock()
        lsblk_result.stdout = lsblk_output

        return mocker.patch(
            "imagecraft.losetup.subprocess.run",
            side_effect=[losetup_result, lsblk_result],
        )

    def test_returns_loop_device_no_partitions(self, mocker, tmp_path):
        img = tmp_path / "disk.img"
        self._make_run(mocker, loop_dev="/dev/loop8", partitions=[])

        result = _losetup_attach(img)

        assert result == ["/dev/loop8"]

    def test_returns_loop_and_partitions(self, mocker, tmp_path):
        img = tmp_path / "disk.img"
        self._make_run(mocker, loop_dev="/dev/loop8", partitions=["p1", "p2"])

        result = _losetup_attach(img)

        assert result == ["/dev/loop8", "/dev/loop8p1", "/dev/loop8p2"]

    def test_calls_losetup_find_show_partscan(self, mocker, tmp_path):
        img = tmp_path / "disk.img"
        mock_run = self._make_run(mocker, loop_dev="/dev/loop8")

        _losetup_attach(img)

        losetup_call = mock_run.call_args_list[0]
        assert losetup_call[0][0] == [
            "losetup",
            "--find",
            "--show",
            "--partscan",
            str(img),
        ]

    def test_calls_lsblk_on_loop_device(self, mocker, tmp_path):
        img = tmp_path / "disk.img"
        mock_run = self._make_run(mocker, loop_dev="/dev/loop8")

        _losetup_attach(img)

        lsblk_call = mock_run.call_args_list[1]
        cmd = lsblk_call[0][0]
        assert "lsblk" in cmd
        assert "/dev/loop8" in cmd

    def test_ignores_non_part_children(self, mocker, tmp_path):
        img = tmp_path / "disk.img"
        lsblk_output = json.dumps(
            {
                "blockdevices": [
                    {
                        "name": "loop8",
                        "type": "loop",
                        "children": [
                            {"name": "loop8p1", "type": "part"},
                            {"name": "dm-0", "type": "dm"},  # not a partition
                        ],
                    }
                ]
            }
        )
        losetup_result = MagicMock()
        losetup_result.stdout = "/dev/loop8\n"
        lsblk_result = MagicMock()
        lsblk_result.stdout = lsblk_output
        mocker.patch(
            "imagecraft.losetup.subprocess.run",
            side_effect=[losetup_result, lsblk_result],
        )

        result = _losetup_attach(img)

        assert "/dev/dm-0" not in result
        assert "/dev/loop8p1" in result


# ─── _losetup_detach ──────────────────────────────────────────────────────────


class TestLosetupDetach:
    def _setup(self, mocker, device="/dev/loop8", partitions=None):
        partitions = partitions or []
        children = [{"name": f"loop8{p}", "type": "part"} for p in partitions]
        lsblk_output = json.dumps(
            {"blockdevices": [{"name": "loop8", "type": "loop", "children": children}]}
        )
        lsblk_result = MagicMock()
        lsblk_result.stdout = lsblk_output
        detach_result = MagicMock()

        return mocker.patch(
            "imagecraft.losetup.subprocess.run",
            side_effect=[lsblk_result, detach_result],
        )

    def test_returns_device_no_partitions(self, mocker):
        self._setup(mocker, device="/dev/loop8", partitions=[])

        result = _losetup_detach("/dev/loop8")

        assert result == ["/dev/loop8"]

    def test_returns_device_and_partitions(self, mocker):
        self._setup(mocker, device="/dev/loop8", partitions=["p1", "p2"])

        result = _losetup_detach("/dev/loop8")

        assert result == ["/dev/loop8", "/dev/loop8p1", "/dev/loop8p2"]

    def test_calls_losetup_detach(self, mocker):
        mock_run = self._setup(mocker)

        _losetup_detach("/dev/loop8")

        detach_call = mock_run.call_args_list[1]
        assert detach_call[0][0] == ["losetup", "--detach", "/dev/loop8"]

    def test_ignores_non_part_children(self, mocker):
        lsblk_output = json.dumps(
            {
                "blockdevices": [
                    {
                        "name": "loop8",
                        "type": "loop",
                        "children": [
                            {"name": "loop8p1", "type": "part"},
                            {"name": "dm-0", "type": "dm"},
                        ],
                    }
                ]
            }
        )
        lsblk_result = MagicMock()
        lsblk_result.stdout = lsblk_output
        mocker.patch(
            "imagecraft.losetup.subprocess.run",
            side_effect=[lsblk_result, MagicMock()],
        )

        result = _losetup_detach("/dev/loop8")

        assert "/dev/dm-0" not in result


# ─── attach / detach (high-level) ─────────────────────────────────────────────


class TestAttach:
    def test_delegates_to_loopserver_when_lxd_container(self, mocker):
        mocker.patch("imagecraft.losetup._is_lxd_container", return_value=True)
        mock_req = mocker.patch(
            "imagecraft.losetup._loopserver_request",
            return_value=["/dev/imagecraft-loop0"],
        )
        mocker.patch("craft_cli.emit.debug")

        result = attach(pathlib.Path("/root/disk.img"))

        mock_req.assert_called_once_with("/1.0/attach", "/root/disk.img")
        assert result == ["/dev/imagecraft-loop0"]

    def test_delegates_to_losetup_when_not_container(self, mocker):
        mocker.patch("imagecraft.losetup._is_lxd_container", return_value=False)
        mock_attach = mocker.patch(
            "imagecraft.losetup._losetup_attach",
            return_value=["/dev/loop8"],
        )
        mocker.patch("craft_cli.emit.debug")

        result = attach(pathlib.Path("/root/disk.img"))

        mock_attach.assert_called_once_with(pathlib.Path("/root/disk.img"))
        assert result == ["/dev/loop8"]


class TestDetach:
    def test_delegates_to_loopserver_when_lxd_container(self, mocker):
        mocker.patch("imagecraft.losetup._is_lxd_container", return_value=True)
        mock_req = mocker.patch(
            "imagecraft.losetup._loopserver_request",
            return_value=["/dev/imagecraft-loop0"],
        )
        mocker.patch("craft_cli.emit.debug")

        result = detach("/dev/imagecraft-loop0")

        mock_req.assert_called_once_with("/1.0/detach", "/dev/imagecraft-loop0")
        assert result == ["/dev/imagecraft-loop0"]

    def test_delegates_to_losetup_when_not_container(self, mocker):
        mocker.patch("imagecraft.losetup._is_lxd_container", return_value=False)
        mock_detach = mocker.patch(
            "imagecraft.losetup._losetup_detach",
            return_value=["/dev/loop8"],
        )
        mocker.patch("craft_cli.emit.debug")

        result = detach("/dev/loop8")

        mock_detach.assert_called_once_with("/dev/loop8")
        assert result == ["/dev/loop8"]
