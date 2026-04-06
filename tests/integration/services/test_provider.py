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

"""Integration tests for Provider.instance with a live losetup server thread."""

import contextlib
import http.client
import json
import os
import pathlib
import socket
import threading
import urllib.parse
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from craft_application import AppMetadata, ServiceFactory
from craft_application.services.provider import ProviderService
from craft_providers.lxd import LXDInstance, LXDProvider

from imagecraft.losetup.server._server import _RequestHandler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_server_socket(path: pathlib.Path) -> socket.socket:
    """Create and bind a listening Unix socket at *path*."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    os.chmod(path, 0o666)
    sock.listen(1)
    return sock


class _LoopServerThread(threading.Thread):
    """Accept connections and dispatch to _RequestHandler in a background thread."""

    def __init__(self, sock: socket.socket, project: str, container: str) -> None:
        super().__init__(daemon=True)
        self._sock = sock
        self._project = project
        self._container = container
        self._stop_event = threading.Event()
        self._sock.settimeout(0.5)

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                conn, addr = self._sock.accept()
            except TimeoutError:
                continue
            try:
                _RequestHandler(self._project, self._container, conn, addr, None)
            finally:
                conn.close()

    def stop(self) -> None:
        self._stop_event.set()
        self.join(timeout=3)


def _http_post(sock_path: pathlib.Path, endpoint: str, path: str) -> dict:
    """Send a POST request to the loop server and return the parsed JSON."""
    query = urllib.parse.urlencode({"path": path})
    conn = http.client.HTTPConnection("loopserver")
    conn.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.sock.connect(str(sock_path))
    conn.request("POST", f"{endpoint}?{query}")
    return json.loads(conn.getresponse().read())


def _make_provider_service(
    mock_provider: object,
    mock_services: MagicMock,
    mock_app: MagicMock,
) -> "imagecraft.services.provider.Provider":
    """Construct a Provider service with the given provider pre-cached."""
    from imagecraft.services.provider import Provider

    svc = Provider(mock_app, mock_services, work_dir=pathlib.Path("/tmp"))
    svc._provider = mock_provider
    return svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def losetup_socket_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "snap_data" / "losetup"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def loop_server(
    losetup_socket_dir: pathlib.Path,
) -> Generator[tuple[pathlib.Path, _LoopServerThread], None, None]:
    """Start a _LoopServerThread on a temp socket. Yields (socket_path, thread)."""
    sock_path = losetup_socket_dir / "sock"
    srv_sock = _make_server_socket(sock_path)
    thread = _LoopServerThread(srv_sock, project="imagecraft", container="test-container")
    thread.start()
    yield sock_path, thread
    thread.stop()
    srv_sock.close()


@pytest.fixture
def mock_app() -> MagicMock:
    app = MagicMock(spec=AppMetadata)
    app.name = "imagecraft"
    return app


@pytest.fixture
def mock_services() -> MagicMock:
    svc = MagicMock(spec=ServiceFactory)
    project = MagicMock()
    project.name = "test-project"
    svc.get.return_value.get.return_value = project
    return svc


# ---------------------------------------------------------------------------
# Tests: Provider.instance losetup mount behaviour
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_lxd_inst():
    """A mock pylxd instance (returned by _client.instances.get())."""
    inst = MagicMock()
    inst.devices = {}
    return inst


@pytest.fixture
def mock_lxd_provider_instance(mock_lxd_inst):
    """A mock LXDInstance with a wired-up pylxd _client."""
    m = MagicMock(spec=LXDInstance)
    m.instance_name = "test-container"
    m._client = MagicMock()
    m._client.instances.get.return_value = mock_lxd_inst
    return m


@contextlib.contextmanager
def _fake_super_instance(self, build_info, *, work_dir, **kwargs):
    """Stub for ProviderService.instance that yields a fresh MagicMock."""
    yield MagicMock()


@pytest.mark.requires_root
def test_provider_instance_mounts_losetup_for_lxd(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    loop_server: tuple[pathlib.Path, _LoopServerThread],
    losetup_socket_dir: pathlib.Path,
    mock_app: MagicMock,
    mock_services: MagicMock,
    mock_lxd_inst: MagicMock,
    mock_lxd_provider_instance: MagicMock,
) -> None:
    """Provider.instance mounts $SNAP_DATA/losetup when using the LXD provider."""
    snap_data = losetup_socket_dir.parent
    monkeypatch.setenv("SNAP_DATA", str(snap_data))

    provider_svc = _make_provider_service(
        MagicMock(spec=LXDProvider), mock_services, mock_app
    )

    @contextlib.contextmanager
    def fake_super_with_lxd_instance(self, build_info, *, work_dir, **kwargs):
        yield mock_lxd_provider_instance

    with patch.object(ProviderService, "instance", fake_super_with_lxd_instance):
        with provider_svc.instance(MagicMock(), work_dir=tmp_path / "work"):
            pass

    expected_host = snap_data / "losetup"
    assert expected_host.exists()
    assert "disk-dev-losetup" in mock_lxd_inst.devices
    device = mock_lxd_inst.devices["disk-dev-losetup"]
    assert device["type"] == "disk"
    assert device["path"] == "/dev/losetup"
    assert device["source"] == str(expected_host)
    assert device["shift"] == "true"
    mock_lxd_inst.save.assert_called_once_with(wait=True)


def test_provider_instance_skips_losetup_when_no_snap_data(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_app: MagicMock,
    mock_services: MagicMock,
    mock_lxd_inst: MagicMock,
    mock_lxd_provider_instance: MagicMock,
) -> None:
    """Provider.instance does NOT mount losetup when SNAP_DATA is unset."""
    monkeypatch.delenv("SNAP_DATA", raising=False)

    provider_svc = _make_provider_service(
        MagicMock(spec=LXDProvider), mock_services, mock_app
    )

    @contextlib.contextmanager
    def fake_super_with_lxd_instance(self, build_info, *, work_dir, **kwargs):
        yield mock_lxd_provider_instance

    with patch.object(ProviderService, "instance", fake_super_with_lxd_instance):
        with provider_svc.instance(MagicMock(), work_dir=tmp_path / "work"):
            pass

    mock_lxd_inst.save.assert_not_called()


def test_provider_instance_skips_losetup_for_non_lxd(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_app: MagicMock,
    mock_services: MagicMock,
    mock_lxd_inst: MagicMock,
    mock_lxd_provider_instance: MagicMock,
) -> None:
    """Provider.instance does NOT mount losetup for non-LXD providers."""
    from craft_providers.multipass import MultipassProvider

    monkeypatch.setenv("SNAP_DATA", str(tmp_path / "snap_data"))

    provider_svc = _make_provider_service(
        MagicMock(spec=MultipassProvider), mock_services, mock_app
    )

    @contextlib.contextmanager
    def fake_super_with_lxd_instance(self, build_info, *, work_dir, **kwargs):
        yield mock_lxd_provider_instance

    with patch.object(ProviderService, "instance", fake_super_with_lxd_instance):
        with provider_svc.instance(MagicMock(), work_dir=tmp_path / "work"):
            pass

    mock_lxd_inst.save.assert_not_called()


# ---------------------------------------------------------------------------
# Test: full loopserver attach/detach round-trip via _LoopServerThread
# ---------------------------------------------------------------------------


@pytest.mark.requires_root
def test_loopserver_attach_detach_round_trip(
    tmp_path: pathlib.Path,
    loop_server: tuple[pathlib.Path, _LoopServerThread],
) -> None:
    """Full HTTP round-trip: attach an image, verify devices added, then detach."""
    import imagecraft.losetup.server._lxd as _lxd
    from imagecraft.pack import gptutil
    from unittest.mock import MagicMock

    sock_path, _ = loop_server

    # Create a minimal GPT image to attach.
    image_path = tmp_path / "test.img"
    gptutil.create_empty_gpt_image(
        imagepath=image_path,
        sector_size=512,
        layout=MagicMock(structure=[], volume_schema=None),
    )

    # Fake LXD device state so we don't need a real daemon.
    fake_devices: dict = {}

    def fake_lxd_get(path: str) -> dict:
        return {"metadata": {"expanded_devices": dict(fake_devices)}}

    def fake_lxd_patch(path: str, body: dict) -> dict:
        for name, dev in body.get("devices", {}).items():
            if dev is None:
                fake_devices.pop(name, None)
            else:
                fake_devices[name] = dev
        return {}

    with (
        patch.object(_lxd, "lxd_get", side_effect=fake_lxd_get),
        patch.object(_lxd, "lxd_patch", side_effect=fake_lxd_patch),
        patch(
            "imagecraft.losetup.server._server.convert_container_path_to_host_path",
            return_value=image_path,
        ),
    ):
        # Attach
        resp = _http_post(sock_path, "/1.0/attach", "/root/test.img")
        assert resp["status_code"] == 200, resp
        attached = resp["metadata"]
        assert attached, "expected at least the loop device in metadata"
        loop_alias = attached[0]
        assert loop_alias.startswith("/dev/imagecraft-loop")

        # Loop device should appear in the fake device table.
        assert any(dev.get("path") == loop_alias for dev in fake_devices.values())

        # Detach
        resp = _http_post(sock_path, "/1.0/detach", loop_alias)
        assert resp["status_code"] == 200, resp
        assert loop_alias in resp["metadata"]

        # All unix-block devices should be removed.
        assert not any(
            dev.get("type") == "unix-block" for dev in fake_devices.values()
        )
