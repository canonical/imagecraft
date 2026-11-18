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

"""Tests for the gadget-volumes extension."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import urllib.error
from typing import TYPE_CHECKING, cast

import pytest
from craft_application import ServiceFactory, errors
from imagecraft import cli
from imagecraft.application import APP_METADATA
from imagecraft.extensions.gadget_volumes import GadgetVolumesExtension
from imagecraft.models import Project
from imagecraft.services.project import ImagecraftProjectService

if TYPE_CHECKING:
    from pathlib import Path

SAMPLE_GADGET_YAML = """
volumes:
  pc:
    schema: gpt
    bootloader: grub
    structure:
      - name: mbr
        type: mbr
        size: 440
      - name: BIOS Boot
        size: 1M
        type: 21686148-6449-6E6F-744E-656564454649
      - name: ubuntu-seed
        role: system-seed
        filesystem: vfat
        size: 1200M
        type: EF,C12A7328-F81F-11D2-BA4B-00A0C93EC93B
      - name: ubuntu-boot
        role: system-boot
        filesystem: ext4
        size: 750M
        type: 83,0FC63DAF-8483-4772-8E79-3D69D8477DE4
      - name: ubuntu-save
        role: system-save
        filesystem: ext4
        size: 32M
        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
      - name: ubuntu-data
        role: system-data
        filesystem: ext4
        size: 1G
        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
"""

SAMPLE_MODEL_ASSERT = """type: model
authority-id: canonical
series: 16
brand-id: canonical
model: ubuntu-core-24-amd64
architecture: amd64
base: core24
grade: signed
snaps:
  -
    default-channel: 24/stable
    id: UqFziVZDHLSyO3TqSWgNBoAdHbLI4dAH
    name: pc
    type: gadget
  -
    default-channel: 24/stable
    id: pYVQrBcKmBa0mZ4CCN7ExT6jH8rY1hza
    name: pc-kernel
    type: kernel

AcLBXAQAAQoABgUCZiLKhgAKCRDgT5vottzAEmmwD
"""


def _create_mock_snap(output_path: Path, gadget_yaml_content: str) -> None:
    """Pack a minimal mock gadget snap using mksquashfs."""
    mksquashfs = shutil.which("mksquashfs")
    if not mksquashfs:
        pytest.skip("mksquashfs not available")

    source_dir = output_path.parent / "snap_source"
    meta_dir = source_dir / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "gadget.yaml").write_text(gadget_yaml_content, encoding="utf-8")

    subprocess.run(
        [mksquashfs, str(source_dir), str(output_path)],
        check=True,
        capture_output=True,
    )


def test_gadget_volumes_from_root_file(tmp_path: Path):
    (tmp_path / "gadget.yaml").write_text(SAMPLE_GADGET_YAML, encoding="utf-8")

    ext = GadgetVolumesExtension(
        project_root=tmp_path,
        yaml_data={},
        app_name="imagecraft",
    )
    snippet = ext.get_root_snippet()

    assert "volumes" in snippet
    assert "pc" in snippet["volumes"]
    pc = snippet["volumes"]["pc"]
    assert pc["schema"] == "gpt"

    struct = pc["structure"]
    names = [s["name"] for s in struct]
    assert names == ["ubuntu-seed", "ubuntu-boot", "ubuntu-save", "ubuntu-data"]

    seed_part = next(s for s in struct if s["name"] == "ubuntu-seed")
    assert seed_part["role"] == "system-seed"
    assert seed_part["filesystem"] == "vfat"
    assert seed_part["type"] == "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"


def test_gadget_volumes_from_arch_file(tmp_path: Path):
    (tmp_path / "gadget-arm64.yaml").write_text(SAMPLE_GADGET_YAML, encoding="utf-8")

    ext = GadgetVolumesExtension(
        project_root=tmp_path,
        yaml_data={},
        app_name="imagecraft",
        build_for="arm64",
    )
    snippet = ext.get_root_snippet()

    assert "volumes" in snippet
    assert "pc" in snippet["volumes"]


def test_gadget_volumes_from_subdir_file(tmp_path: Path):
    subdir = tmp_path / "gadget"
    subdir.mkdir()
    (subdir / "gadget.yaml").write_text(SAMPLE_GADGET_YAML, encoding="utf-8")

    ext = GadgetVolumesExtension(
        project_root=tmp_path,
        yaml_data={},
        app_name="imagecraft",
    )
    snippet = ext.get_root_snippet()

    assert "volumes" in snippet
    assert "pc" in snippet["volumes"]


def test_gadget_volumes_from_local_snap(tmp_path: Path):
    snap_file = tmp_path / "pc_24_amd64.snap"
    _create_mock_snap(snap_file, SAMPLE_GADGET_YAML)

    ext = GadgetVolumesExtension(
        project_root=tmp_path,
        yaml_data={},
        app_name="imagecraft",
    )
    snippet = ext.get_root_snippet()

    assert "volumes" in snippet
    assert "pc" in snippet["volumes"]


def test_gadget_volumes_from_uc_prepare_store(tmp_path: Path, monkeypatch):
    (tmp_path / "model.assert").write_text(SAMPLE_MODEL_ASSERT, encoding="utf-8")

    mock_snap_path = tmp_path / "store_pc.snap"
    _create_mock_snap(mock_snap_path, SAMPLE_GADGET_YAML)
    snap_bytes = mock_snap_path.read_bytes()

    def mock_urlopen(req, *args, **kwargs):
        del args, kwargs
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "api.snapcraft.io/api/v1/snaps/details" in url:
            payload = {"anon_download_url": "https://api.snapcraft.io/download/pc.snap"}
            return io.BytesIO(json.dumps(payload).encode("utf-8"))
        if "download/pc.snap" in url:
            return io.BytesIO(snap_bytes)
        raise urllib.error.URLError("Unexpected URL")

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    yaml_data = {
        "parts": {
            "seed": {
                "plugin": "uc-prepare",
                "uc-prepare-model-assert": "model.assert",
            }
        }
    }

    ext = GadgetVolumesExtension(
        project_root=tmp_path,
        yaml_data=yaml_data,
        app_name="imagecraft",
        build_for="amd64",
    )
    snippet = ext.get_root_snippet()

    assert "volumes" in snippet
    assert "pc" in snippet["volumes"]


def test_gadget_volumes_not_found_raises(tmp_path: Path):
    ext = GadgetVolumesExtension(
        project_root=tmp_path,
        yaml_data={},
        app_name="imagecraft",
    )
    with pytest.raises(
        errors.ExtensionError, match="Could not find a gadget definition"
    ):
        ext.get_root_snippet()


def test_full_project_service_with_gadget_extension(
    tmp_path: Path, enable_features, monkeypatch
):
    monkeypatch.setenv("IMAGECRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS", "1")
    cli.register_extensions()
    (tmp_path / "gadget.yaml").write_text(SAMPLE_GADGET_YAML, encoding="utf-8")

    project_file = tmp_path / "imagecraft.yaml"
    project_file.write_text(
        """\
name: core-test
version: "0.1"
summary: Test image
description: Testing gadget-volumes extension
base: bare
build-base: devel
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
extensions:
  - gadget-volumes
filesystems:
  default:
    - mount: /
      device: (volume/pc/ubuntu-seed)
"""
    )

    services = ServiceFactory(app=APP_METADATA)
    project_service = ImagecraftProjectService(
        app=APP_METADATA,
        services=services,
        project_dir=tmp_path,
    )
    project_service.configure(platform="amd64", build_for="amd64")

    project = cast(Project, project_service.get())
    assert project.extensions == ["gadget-volumes"]
    assert "pc" in project.volumes
    vol = project.volumes["pc"]
    partition_names = [p.name for p in vol.structure]
    assert "ubuntu-seed" in partition_names
    assert "ubuntu-boot" in partition_names
    assert "ubuntu-save" in partition_names
    assert "ubuntu-data" in partition_names


def test_gadget_volumes_experimental_blocked(
    tmp_path: Path, enable_features, monkeypatch
):
    monkeypatch.delenv("IMAGECRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS", raising=False)
    monkeypatch.delenv("CRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS", raising=False)
    cli.register_extensions()
    (tmp_path / "gadget.yaml").write_text(SAMPLE_GADGET_YAML, encoding="utf-8")

    project_file = tmp_path / "imagecraft.yaml"
    project_file.write_text(
        """\
name: core-test
version: "0.1"
summary: Test image
description: Testing gadget-volumes extension
base: bare
build-base: ubuntu@24.04
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
extensions:
  - gadget-volumes
filesystems:
  default:
    - mount: /
      device: (volume/pc/ubuntu-seed)
"""
    )

    services = ServiceFactory(app=APP_METADATA)
    project_service = ImagecraftProjectService(
        app=APP_METADATA,
        services=services,
        project_dir=tmp_path,
    )
    project_service.configure(platform="amd64", build_for="amd64")

    with pytest.raises(
        errors.ExtensionError,
        match="Extension 'gadget-volumes' is experimental on base 'ubuntu@24.04'",
    ):
        project_service.get()


@pytest.mark.parametrize("build_base", ["ubuntu@24.04", "ubuntu@26.04", "devel"])
def test_gadget_volumes_supported_build_bases(
    tmp_path: Path, build_base: str, enable_features, monkeypatch
):
    monkeypatch.setenv("IMAGECRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS", "1")
    cli.register_extensions()
    (tmp_path / "gadget.yaml").write_text(SAMPLE_GADGET_YAML, encoding="utf-8")

    project_file = tmp_path / "imagecraft.yaml"
    project_file.write_text(
        f"""\
name: core-test
version: "0.1"
summary: Test image
description: Testing gadget-volumes extension
base: bare
build-base: {build_base}
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
extensions:
  - gadget-volumes
filesystems:
  default:
    - mount: /
      device: (volume/pc/ubuntu-seed)
"""
    )

    services = ServiceFactory(app=APP_METADATA)
    project_service = ImagecraftProjectService(
        app=APP_METADATA,
        services=services,
        project_dir=tmp_path,
    )
    project_service.configure(platform="amd64", build_for="amd64")

    project = cast(Project, project_service.get())
    assert "pc" in project.volumes


def test_gadget_volumes_unsupported_build_base(
    tmp_path: Path, enable_features, monkeypatch
):
    monkeypatch.setenv("IMAGECRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS", "1")
    cli.register_extensions()
    (tmp_path / "gadget.yaml").write_text(SAMPLE_GADGET_YAML, encoding="utf-8")

    project_file = tmp_path / "imagecraft.yaml"
    project_file.write_text(
        """\
name: core-test
version: "0.1"
summary: Test image
description: Testing gadget-volumes extension
base: bare
build-base: ubuntu@20.04
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
extensions:
  - gadget-volumes
filesystems:
  default:
    - mount: /
      device: (volume/pc/ubuntu-seed)
"""
    )

    services = ServiceFactory(app=APP_METADATA)
    project_service = ImagecraftProjectService(
        app=APP_METADATA,
        services=services,
        project_dir=tmp_path,
    )
    project_service.configure(platform="amd64", build_for="amd64")

    with pytest.raises(
        errors.ExtensionError,
        match="Extension 'gadget-volumes' does not support base 'ubuntu@20.04'",
    ):
        project_service.get()
