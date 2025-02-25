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
from textwrap import dedent

import pytest
from craft_application import models, util

IMAGECRAFT_YAML = """
name: ubuntu-server-amd64
version: "1"
base: bare
build-base: ubuntu@22.04
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500 MiB
"""


def test_application(new_dir, default_application):
    project_file = Path(new_dir) / "imagecraft.yaml"
    project_file.write_text(IMAGECRAFT_YAML)

    project = default_application.project

    assert project.base == "bare"
    assert project.build_base == "ubuntu@22.04"
    assert project.volumes["pc"].volume_schema == "gpt"


@pytest.fixture
def grammar_project(tmp_path):
    """A project that builds on amd64 to riscv64 and s390x."""
    contents = dedent(
        """\
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
      volumes:
        pc:
          schema: gpt
          structure:
            - on amd64 to riscv64:
              - name: uboot
                role: system-boot
                type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
                filesystem: vfat
                size: 200 MiB
            - on amd64 to arm64:
              - name: efi
                role: system-boot
                type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
                filesystem: vfat
                size: 500 MiB
            - name: rootfs
              type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
              filesystem: ext4
              filesystem-label: writable
              role: system-data
              size: 6GiB
    """
    )
    project_file = tmp_path / "imagecraft.yaml"
    project_file.write_text(contents)


@pytest.fixture
def grammar_build_plan(mocker):
    """A build plan to build on amd64 to riscv64 and arm64."""
    host_arch = "amd64"
    base = util.get_host_base()
    build_plan = [
        models.BuildInfo(
            f"platform-{build_for}",
            host_arch,
            build_for,
            base,
        )
        for build_for in ("arm64", "riscv64")
    ]

    mocker.patch.object(models.BuildPlanner, "get_build_plan", return_value=build_plan)


@pytest.fixture
def grammar_app(
    tmp_path,
    grammar_project,
    grammar_build_plan,
    default_factory,
):
    from imagecraft.application import APP_METADATA, Imagecraft

    app = Imagecraft(APP_METADATA, default_factory)
    app.project_dir = tmp_path

    return app


def test_application_grammar_arm64(monkeypatch, grammar_app):
    project = grammar_app.get_project(build_for="arm64")

    assert project.volumes["pc"].structure[0].name == "efi"
    assert project.volumes["pc"].structure[1].name == "rootfs"


def test_application_grammar_riscv64(grammar_app):
    project = grammar_app.get_project(build_for="riscv64")

    assert project.volumes["pc"].structure[0].name == "uboot"
    assert project.volumes["pc"].structure[1].name == "rootfs"
