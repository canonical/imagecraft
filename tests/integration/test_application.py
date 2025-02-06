#  This file is part of imagecraft.
#
#  Copyright 2025 Canonical Ltd.
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
"""Integration tests for the application as a whole."""

from pathlib import Path

import pytest
from craft_parts import Features
from imagecraft import application

IMAGECRAFT_YAML = """
name: ubuntu-server-amd64
version: "24.04.20241217"
base: bare
build-base: ubuntu@24.04
platforms:
  generic-amd64:
    build-on: amd64
    build-for: amd64
  arm64:
  armhf:
  i386:
  ppc64el:
  riscv64:
  s390x:
parts:
  rootfs:
    plugin: nil
    override-build: |
      echo "build a rootfs" > $CRAFT_PART_INSTALL/a.txt
      echo "build a rootfs" > $CRAFT_PART_INSTALL/b.txt
    organize:
      a.txt: (volume/pc/rootfs)/a.txt
      b.txt: (volume/pc/efi)/b.txt
volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        filesystem-label: system-boot
        size: 512MiB
        role: system-boot
      - name: rootfs
        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
        filesystem: ext4
        filesystem-label: writable
        role: system-data
        size: 6GiB

"""

IMAGECRAFT_OVERLAY_YAML = """
name: ubuntu-server-amd64
version: "24.04.20241217"
base: bare
build-base: ubuntu@24.04
platforms:
  generic-amd64:
    build-on: amd64
    build-for: amd64
parts:
  part1:
    plugin: nil
    overlay-script: |
      echo "a1" > $CRAFT_OVERLAY/a
      echo b > $CRAFT_OVERLAY/b
  part2:
    after: [part1]
    plugin: nil
    overlay-script: |
      echo "a2" > $CRAFT_OVERLAY/a
      echo "c2" > $CRAFT_OVERLAY/c
  part3:
    after: [part1]
    plugin: nil
    overlay-script: |
      rm $CRAFT_OVERLAY/a # will create $CRAFT_OVERLAY/.wh.a
      echo "c3" > $CRAFT_OVERLAY/c
  part4:
    after: [part3]
    plugin: nil
    overlay-script: |
      echo "a4" > $CRAFT_OVERLAY/a
      echo "d4" > $CRAFT_OVERLAY/d
  part5:
    after: [part4]
    plugin: nil
    overlay-script: |
      rm $CRAFT_OVERLAY/a # will also create $CRAFT_OVERLAY/.wh.a

volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        filesystem-label: system-boot
        size: 512MiB
        role: system-boot
      - name: rootfs
        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
        filesystem: ext4
        filesystem-label: writable
        role: system-data
        size: 6GiB

"""


def test_imagecraft_build(
    empty_project_dir: Path,
    imagecraft_app: application.Imagecraft,
    monkeypatch: pytest.MonkeyPatch,
    check,
):
    """Test imagecraft."""
    monkeypatch.setenv("CRAFT_DEBUG", "1")

    project_file = empty_project_dir / "imagecraft.yaml"
    project_file.write_text(IMAGECRAFT_YAML)

    monkeypatch.setattr(
        "sys.argv",
        ["imagecraft", "build", "--destructive-mode", "--verbosity", "debug"],
    )
    result = imagecraft_app.run()

    assert result == 0

    assert imagecraft_app._partitions == [
        "default",
        "volume/pc/efi",
        "volume/pc/rootfs",
    ]
    check.is_true((empty_project_dir / "prime").exists())
    check.is_true((empty_project_dir / "parts").exists())
    check.is_true((empty_project_dir / "stage").exists())
    check.is_true(
        (
            empty_project_dir / "partitions/volume/pc/rootfs/parts/rootfs/install/a.txt"
        ).exists()
    )
    check.is_true(
        (
            empty_project_dir / "partitions/volume/pc/efi/parts/rootfs/install/b.txt"
        ).exists()
    )


def test_imagecraft_clean_overlay(
    empty_project_dir: Path,
    imagecraft_app: application.Imagecraft,
    monkeypatch: pytest.MonkeyPatch,
    check,
):
    """Test imagecraft."""
    monkeypatch.setenv("CRAFT_DEBUG", "1")

    project_file = empty_project_dir / "imagecraft.yaml"
    project_file.write_text(IMAGECRAFT_OVERLAY_YAML)

    monkeypatch.setattr(
        "sys.argv",
        ["imagecraft", "build", "--destructive-mode", "--verbosity", "debug"],
    )
    result = imagecraft_app.run()

    assert result == 0

    Features.reset()

    monkeypatch.setattr(
        "sys.argv",
        ["imagecraft", "clean", "--destructive-mode", "--verbosity", "debug"],
    )
    result = imagecraft_app.run()
