#  This file is part of imagecraft.
#
#  Copyright 2026 Canonical Ltd.
#
#  This program is free software: you can redistribute it and/or modify it
#  under the terms of the GNU General Public License version 3, as
#  published by the Free Software Foundation.
#
#  This program is distributed in the hope that it will be useful, but WITHOUT
#  ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
#  SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.
#  See the GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License along
#  with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Integration tests for the mmdebstrap plugin."""

from pathlib import Path

import pytest
from imagecraft import application


@pytest.fixture
def custom_project_file(default_project_file: Path):
    yaml_content = (Path(__file__).parent / "mmdebstrap/imagecraft.yaml").read_text()
    default_project_file.write_text(yaml_content)
    return default_project_file


@pytest.mark.slow
@pytest.mark.requires_root
def test_mmdebstrap_cleanup(
    project_path: Path,
    custom_project_file: Path,
    imagecraft_app: application.Imagecraft,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test that mmdebstrap plugin cleans up /sys, /proc and /dev."""
    monkeypatch.setattr(
        "sys.argv",
        ["imagecraft", "build", "--destructive-mode", "--verbosity", "debug"],
    )
    result = imagecraft_app.run()

    assert result == 0

    install_dir = project_path / "parts/rootfs/install"

    for subdir in ["sys", "proc", "dev"]:
        path = install_dir / subdir
        if path.exists():
            assert list(path.iterdir()) == []
