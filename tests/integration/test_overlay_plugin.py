# This file is part of imagecraft.
#
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

from pathlib import Path
from typing import Literal

import pytest
from craft_parts import plugins
from craft_parts.plugins import Plugin, PluginProperties
from imagecraft import application
from imagecraft.plugins import get_app_plugins
from typing_extensions import override

IMAGECRAFT_YAML = """
name: overlay-plugin-test
version: "0.1"
summary: A test image
description: This image exists purely for testing purposes, yo!
base: bare
build-base: ubuntu@24.04
platforms:
  amd64:
    build-on: [amd64]
    build-for: [amd64]

parts:
  rootfs:
    plugin: mmdebstrap
    organize:
      "*": (overlay)/
    override-build: |
      craftctl default
      cat > $CRAFT_PART_INSTALL/etc/apt/sources.list << EOF
      deb http://archive.ubuntu.com/ubuntu noble main universe
      EOF

  overlay-part:
    plugin: overlay-test-plugin
    after: [rootfs]

volumes:
  pc:
    schema: gpt
    structure:
      - name: rootfs
        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
        filesystem: ext4
        filesystem-label: writable
        role: system-data
        size: 512M

filesystems:
  default:
  - mount: /
    device: (volume/pc/rootfs)
"""


@pytest.fixture
def custom_project_file(default_project_file: Path):
    default_project_file.write_text(IMAGECRAFT_YAML)

    return default_project_file


class OverlayTestPluginProperties(PluginProperties, frozen=True):
    plugin: Literal["overlay-test-plugin"] = "overlay-test-plugin"


class OverlayTestPlugin(Plugin):
    properties_class = OverlayTestPluginProperties
    uses_overlay = True

    @override
    def get_build_packages(self) -> set[str]:
        return set()

    @override
    def get_build_snaps(self) -> set[str]:
        return set()

    @override
    def get_build_environment(self) -> dict[str, str]:
        return {}

    @override
    def get_build_commands(self) -> list[str]:
        return []

    @override
    def get_overlay_packages(self) -> set[str]:
        return {"hello"}

    @override
    def get_overlay_chroot_commands(self) -> list[str]:
        return ["hello --greeting 'overlay-test-plugin' > /plugin-overlay.txt"]


@pytest.fixture(autouse=True)
def register_plugins(monkeypatch):
    plugins.register({"overlay-test-plugin": OverlayTestPlugin})
    imagecraft_plugins = get_app_plugins()
    monkeypatch.setattr(
        "imagecraft.plugins.get_app_plugins",
        lambda: {**imagecraft_plugins, "overlay-test-plugin": OverlayTestPlugin},
    )
    yield
    plugins.unregister("overlay-test-plugin")


@pytest.mark.requires_root
def test_overlay_plugin(
    project_path: Path,
    custom_project_file: Path,
    imagecraft_app: application.Imagecraft,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(
        "sys.argv",
        ["imagecraft", "pack", "--destructive-mode", "--verbosity", "debug"],
    )
    result = imagecraft_app.run()

    assert result == 0

    overlay_txt = project_path / "prime" / "plugin-overlay.txt"
    assert overlay_txt.exists()
    assert "overlay-test-plugin" in overlay_txt.read_text()
