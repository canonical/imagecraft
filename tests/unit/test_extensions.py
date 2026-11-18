# This file is part of imagecraft.
#
# Copyright 2026 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Unit tests for Imagecraft extensions infrastructure."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from craft_application import ServiceFactory
from imagecraft import cli, extensions
from imagecraft.application import APP_METADATA
from imagecraft.services.project import ImagecraftProjectService
from typing_extensions import override

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence


class SampleImagecraftExtension(extensions.Extension):
    """Sample extension for Imagecraft tests."""

    name = "sample"

    @staticmethod
    @override
    def get_supported_bases() -> Sequence[str]:
        return ("devel", "ubuntu@22.04", "ubuntu@24.04")

    @staticmethod
    @override
    def is_experimental(base: str | None) -> bool:
        return False

    @override
    def get_parts_snippet(self) -> dict[str, Any]:
        return {
            f"{self.name}/boot-helper": {
                "plugin": "nil",
                "stage-packages": ["busybox"],
            }
        }


def test_extensions_exports():
    assert hasattr(extensions, "Extension")
    assert hasattr(extensions, "apply_extensions")
    assert hasattr(extensions, "register")
    assert hasattr(extensions, "unregister")
    assert hasattr(extensions, "get_extension_class")
    assert hasattr(extensions, "get_extension_names")
    assert hasattr(extensions, "get_extensions")


def test_cli_registers_extension_commands():
    app = cli._create_app()
    command_names = [cmd.name for group in app.command_groups for cmd in group.commands]
    assert "list-extensions" in command_names
    assert "expand-extensions" in command_names
    assert "extensions" in command_names


def test_project_service_applies_extensions(tmp_path: pathlib.Path, enable_features):
    extensions.register("sample", SampleImagecraftExtension)

    project_file = tmp_path / "imagecraft.yaml"
    project_file.write_text(
        """\
name: test-image
version: "1"
summary: Test image
description: Test image with extensions
base: bare
build-base: devel
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
extensions:
  - sample
filesystems:
  default:
    - mount: /
      device: (volume/pc/rootfs)
volumes:
  pc:
    schema: gpt
    structure:
      - name: rootfs
        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
        filesystem: ext4
        filesystem-label: writable
        role: system-data
        size: 1G
"""
    )

    services = ServiceFactory(app=APP_METADATA)
    project_service = ImagecraftProjectService(
        app=APP_METADATA,
        services=services,
        project_dir=tmp_path,
    )
    project_service.configure(platform="amd64", build_for="amd64")

    project = project_service.get()
    assert project.extensions == ["sample"]
    assert "sample/boot-helper" in project.parts
    assert project.parts["sample/boot-helper"]["stage-packages"] == ["busybox"]
