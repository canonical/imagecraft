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

"""Unit tests for imagecraft/services/provider.py – Provider.instance override."""

import pathlib
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from craft_application import AppMetadata, ServiceFactory
from craft_application.services.provider import ProviderService
from craft_providers.lxd import LXDInstance, LXDProvider
from craft_providers.multipass import MultipassProvider

from imagecraft.services.provider import Provider


# ─── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_lxd_inst():
    """A mock pylxd instance (returned by _client.instances.get())."""
    inst = MagicMock()
    inst.devices = {}
    return inst


@pytest.fixture
def mock_instance(mock_lxd_inst):
    """A mock LXDInstance with a wired-up pylxd _client."""
    m = MagicMock(spec=LXDInstance)
    m.instance_name = "test-container"
    m._client = MagicMock()
    m._client.instances.get.return_value = mock_lxd_inst
    return m


@pytest.fixture
def provider(tmp_path):
    app = MagicMock(spec=AppMetadata)
    services = MagicMock(spec=ServiceFactory)
    return Provider(app, services, work_dir=tmp_path)


# ─── helpers ──────────────────────────────────────────────────────────────────


def _patch_super_instance(mocker, mock_inst):
    """Patch ProviderService.instance to yield *mock_inst*."""

    @contextmanager
    def fake_instance(self, build_info, *, work_dir, **kwargs):
        yield mock_inst

    mocker.patch.object(ProviderService, "instance", fake_instance)


# ─── tests ────────────────────────────────────────────────────────────────────


class TestProviderInstance:
    def test_lxd_with_snap_data_mounts_losetup(
        self, mocker, provider, mock_instance, mock_lxd_inst, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("SNAP_DATA", str(tmp_path))
        _patch_super_instance(mocker, mock_instance)
        mocker.patch.object(
            provider, "get_provider", return_value=MagicMock(spec=LXDProvider)
        )
        mocker.patch("craft_cli.emit.debug")

        build_info = MagicMock()
        with provider.instance(build_info, work_dir=tmp_path) as inst:
            assert inst is mock_instance

        assert "disk-dev-losetup" in mock_lxd_inst.devices
        device = mock_lxd_inst.devices["disk-dev-losetup"]
        assert device["type"] == "disk"
        assert device["path"] == "/dev/losetup"
        assert device["source"] == str(tmp_path / "losetup")
        assert device["shift"] == "true"
        mock_lxd_inst.save.assert_called_once_with(wait=True)

    def test_lxd_with_snap_data_creates_losetup_dir(
        self, mocker, provider, mock_instance, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("SNAP_DATA", str(tmp_path))
        _patch_super_instance(mocker, mock_instance)
        mocker.patch.object(
            provider, "get_provider", return_value=MagicMock(spec=LXDProvider)
        )
        mocker.patch("craft_cli.emit.debug")

        build_info = MagicMock()
        with provider.instance(build_info, work_dir=tmp_path):
            pass

        assert (tmp_path / "losetup").is_dir()

    def test_lxd_without_snap_data_does_not_mount(
        self, mocker, provider, mock_instance, mock_lxd_inst, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("SNAP_DATA", raising=False)
        _patch_super_instance(mocker, mock_instance)
        mocker.patch.object(
            provider, "get_provider", return_value=MagicMock(spec=LXDProvider)
        )
        mocker.patch("craft_cli.emit.debug")

        build_info = MagicMock()
        with provider.instance(build_info, work_dir=tmp_path) as inst:
            assert inst is mock_instance

        mock_lxd_inst.save.assert_not_called()

    def test_non_lxd_provider_does_not_mount(
        self, mocker, provider, mock_instance, mock_lxd_inst, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("SNAP_DATA", str(tmp_path))
        _patch_super_instance(mocker, mock_instance)
        mocker.patch.object(
            provider, "get_provider", return_value=MagicMock(spec=MultipassProvider)
        )
        mocker.patch("craft_cli.emit.debug")

        build_info = MagicMock()
        with provider.instance(build_info, work_dir=tmp_path) as inst:
            assert inst is mock_instance

        mock_lxd_inst.save.assert_not_called()

    def test_already_mounted_does_not_add_duplicate(
        self, mocker, provider, mock_instance, mock_lxd_inst, tmp_path, monkeypatch
    ):
        """If disk-dev-losetup already exists in devices, save() is not called again."""
        monkeypatch.setenv("SNAP_DATA", str(tmp_path))
        _patch_super_instance(mocker, mock_instance)
        mocker.patch.object(
            provider, "get_provider", return_value=MagicMock(spec=LXDProvider)
        )
        mocker.patch("craft_cli.emit.debug")
        mock_lxd_inst.devices["disk-dev-losetup"] = {
            "type": "disk",
            "path": "/dev/losetup",
            "source": str(tmp_path / "losetup"),
            "shift": "true",
        }

        build_info = MagicMock()
        with provider.instance(build_info, work_dir=tmp_path):
            pass

        mock_lxd_inst.save.assert_not_called()

    def test_yields_instance_from_super(
        self, mocker, provider, mock_instance, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("SNAP_DATA", raising=False)
        _patch_super_instance(mocker, mock_instance)
        mocker.patch.object(
            provider, "get_provider", return_value=MagicMock(spec=MultipassProvider)
        )
        mocker.patch("craft_cli.emit.debug")

        build_info = MagicMock()
        with provider.instance(build_info, work_dir=tmp_path) as inst:
            assert inst is mock_instance
