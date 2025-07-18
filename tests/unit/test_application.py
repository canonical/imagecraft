# This file is part of imagecraft.
#
# Copyright 2023-2025 Canonical Ltd.
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
from typing import cast

import pytest
from craft_application import ServiceFactory
from imagecraft.application import Imagecraft
from imagecraft.models import Project

IMAGECRAFT_YAML = """
name: ubuntu-server-amd64
version: "1"
base: bare
build-base: ubuntu@22.04
platforms:
  amd64:
    build-for: amd64
    build-on: amd64

filesystems:
  default:
  - mount: /
    device: (volume/pc/rootfs)
  - mount: /boot/efi
    device: (volume/pc/efi)

volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500 M
      - name: rootfs
        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
        filesystem: ext4
        filesystem-label: writable
        role: system-data
        size: 6G
"""


@pytest.fixture
def custom_project_file(default_project_file: Path):
    default_project_file.write_text(IMAGECRAFT_YAML)

    return default_project_file


def test_application(
    new_dir: Path,
    custom_project_file: Path,
    default_application: Imagecraft,
    enable_features,
):
    project = cast(Project, default_application.services.get("project").get())

    assert project.base == "bare"
    assert project.build_base == "ubuntu@22.04"
    assert project.volumes["pc"].volume_schema == "gpt"


GRAMMAR_IMAGECRAFT_YAML = """
name: ubuntu-server-amd64
version: "1"
base: bare
build-base: ubuntu@22.04
platforms:
  arm64:
    build-on: [amd64]
    build-for: [arm64]
  riscv64:
    build-on: [amd64]
    build-for: [riscv64]
filesystems:
  default:
  - mount: /
    device: (volume/pc/rootfs)
volumes:
  pc:
    schema: gpt
    structure:
      - to arm64:
        - name: efi
          role: system-boot
          type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
          filesystem: vfat
          size: 500 M
      - to riscv64:
        - name: uboot
          role: system-boot
          type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
          filesystem: vfat
          size: 200 M
      - name: rootfs
        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
        filesystem: ext4
        filesystem-label: writable
        role: system-data
        size: 6G
"""


@pytest.fixture
def grammar_project_file(default_project_file: Path):
    default_project_file.write_text(GRAMMAR_IMAGECRAFT_YAML)
    return default_project_file


@pytest.fixture
def default_factory(default_project_file, app_metadata, request):
    factory = ServiceFactory(
        app=app_metadata,
    )

    platform = (
        request.getfixturevalue("fake_platform")
        if "fake_platform" in request.fixturenames
        else None
    )
    build_for = (
        str(request.getfixturevalue("build_for"))
        if "build_for" in request.fixturenames
        else None
    )

    factory.update_kwargs("project", project_dir=default_project_file.parent)
    project = factory.get("project")
    project.configure(platform=platform, build_for=build_for)

    return factory


@pytest.mark.parametrize(
    ("fake_platform", "build_for", "expected"),
    [
        ("arm64", "arm64", ["efi", "rootfs"]),
        ("riscv64", "riscv64", ["uboot", "rootfs"]),
    ],
)
def test_application_grammar(
    fake_platform,
    build_for,
    expected,
    grammar_project_file,
    default_factory,
    default_application: Imagecraft,
    enable_features,
):
    project = cast(Project, default_application.services.get("project").get())

    assert len(project.volumes["pc"].structure) == len(expected)
    for i, e in enumerate(expected):
        assert project.volumes["pc"].structure[i].name == e
