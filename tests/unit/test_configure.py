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

"""Unit tests for snap/hooks/configure – setup_losetup_dir()."""

import importlib.util
import os
import pathlib
import sys
import types

import pytest


def _load_configure_hook() -> types.ModuleType:
    """Load snap/hooks/configure as a Python module (no .py extension)."""
    import importlib.machinery

    hook_path = (
        pathlib.Path(__file__).parent.parent.parent.parent / "snap" / "hooks" / "configure"
    )
    loader = importlib.machinery.SourceFileLoader("snap_configure", str(hook_path))
    spec = importlib.util.spec_from_loader("snap_configure", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def configure_module():
    return _load_configure_hook()


class TestSetupLosetupDir:
    def test_creates_directory(self, configure_module, tmp_path, monkeypatch):
        monkeypatch.setenv("SNAP_DATA", str(tmp_path))

        configure_module.setup_losetup_dir()

        assert (tmp_path / "losetup").is_dir()

    def test_does_not_raise_if_directory_exists(
        self, configure_module, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("SNAP_DATA", str(tmp_path))
        (tmp_path / "losetup").mkdir()  # pre-create

        # Should not raise
        configure_module.setup_losetup_dir()

    def test_chowns_when_lxd_group_exists(
        self, configure_module, tmp_path, monkeypatch, mocker
    ):
        monkeypatch.setenv("SNAP_DATA", str(tmp_path))

        mock_gr = mocker.MagicMock()
        mock_gr.gr_gid = 1234
        mocker.patch.object(configure_module.grp, "getgrnam", return_value=mock_gr)
        mock_chown = mocker.patch.object(configure_module.os, "chown")

        configure_module.setup_losetup_dir()

        losetup_dir = os.path.join(str(tmp_path), "losetup")
        mock_chown.assert_called_once_with(losetup_dir, -1, 1234)

    def test_no_chown_when_lxd_group_missing(
        self, configure_module, tmp_path, monkeypatch, mocker
    ):
        monkeypatch.setenv("SNAP_DATA", str(tmp_path))

        mocker.patch.object(
            configure_module.grp, "getgrnam", side_effect=KeyError("lxd")
        )
        mock_chown = mocker.patch.object(configure_module.os, "chown")

        configure_module.setup_losetup_dir()

        mock_chown.assert_not_called()
