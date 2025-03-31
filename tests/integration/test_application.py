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
    build-on: [amd64]
    build-for: [amd64]
  arm64:
  armhf:
  i386:
  ppc64el:
  riscv64:
  s390x:
parts:
  rootfs:
    plugin: nil
    overlay-script: |
      mkdir $CRAFT_OVERLAY/{etc,bin,boot}
      echo "test" > $CRAFT_OVERLAY/bin/a
      echo "test" > $CRAFT_OVERLAY/etc/b
  bootloader:
    plugin: nil
    after: [rootfs]
    overlay-script: |
      echo "boot files" > $CRAFT_OVERLAY/boot/c

      mv $CRAFT_OVERLAY/boot/* $CRAFT_VOLUME_PC_EFI_OVERLAY/
      mv $CRAFT_OVERLAY/* $CRAFT_VOLUME_PC_ROOTFS_OVERLAY/
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
        size: 512MiB

"""


@pytest.fixture
def custom_project_file(default_project_file: Path):
    default_project_file.write_text(IMAGECRAFT_YAML)
    return default_project_file


def test_imagecraft_build(
    project_path: Path,
    custom_project_file: Path,
    imagecraft_app: application.Imagecraft,
    monkeypatch: pytest.MonkeyPatch,
    check,
):
    """Test imagecraft."""
    Features.reset()
    monkeypatch.setattr(
        "sys.argv",
        ["imagecraft", "build", "--destructive-mode", "--verbosity", "debug"],
    )
    result = imagecraft_app.run()

    assert result == 0

    project = imagecraft_app.services.get("project")

    assert project.partitions == [
        "default",
        "volume/pc/efi",
        "volume/pc/rootfs",
    ]
    check.is_true((project_path / "prime").exists())
    check.is_true((project_path / "parts").exists())
    check.is_true((project_path / "stage").exists())
    check.is_true((project_path / "parts/rootfs/layer/bin/a").exists())
    check.is_true((project_path / "parts/rootfs/layer/etc/b").exists())
    check.is_true(
        (project_path / "partitions/volume/pc/efi/parts/bootloader/layer/c").exists()
    )
    check.is_true(
        (
            project_path / "partitions/volume/pc/rootfs/parts/bootloader/layer/bin/a"
        ).exists()
    )
    check.is_true(
        (
            project_path / "partitions/volume/pc/rootfs/parts/bootloader/layer/etc/b"
        ).exists()
    )


def test_imagecraft_pack(
    project_path: Path,
    imagecraft_app: application.Imagecraft,
    monkeypatch: pytest.MonkeyPatch,
    check,
    mocker,
):
    """Test imagecraft."""
    monkeypatch.setenv("CRAFT_DEBUG", "1")

    mocker.patch("imagecraft.services.pack.Image")
    mocker.patch("imagecraft.services.pack.grubutil.setup_grub")
    project_file = project_path / "imagecraft.yaml"
    project_file.write_text(IMAGECRAFT_YAML)

    monkeypatch.setattr(
        "sys.argv",
        ["imagecraft", "pack", "--destructive-mode", "--verbosity", "debug"],
    )
    result = imagecraft_app.run()

    assert result == 0

    check.is_true((project_path / "pc.img").is_file())
