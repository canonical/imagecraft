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
"""Integration tests for the project service."""

import pathlib

import pydantic
import pytest
from imagecraft.application import APP_METADATA
from imagecraft.services.project import ImagecraftProjectService

pytestmark = [pytest.mark.usefixtures("enable_features")]


@pytest.mark.parametrize(
    "project_dir",
    [
        pytest.param(path, id=path.name)
        for path in sorted((pathlib.Path(__file__).parent / "valid-projects").iterdir())
    ],
)
def test_load_valid_project(
    in_project_path: pathlib.Path,
    project_dir: pathlib.Path,
):
    project_file = in_project_path / "imagecraft.yaml"
    project_file.write_text(
        (project_dir / "imagecraft.yaml").read_text(),
        encoding="utf-8",
    )

    project_service = ImagecraftProjectService(
        app=APP_METADATA,
        services=None,  # ty: ignore[invalid-argument-type]
        project_dir=in_project_path,
    )
    project_service.configure(platform=None, build_for=None)

    project_service.get()


@pytest.mark.parametrize(
    "project_dir",
    [
        pytest.param(path, id=path.name)
        for path in sorted(
            (pathlib.Path(__file__).parent / "invalid-projects").iterdir()
        )
    ],
)
def test_load_invalid_project(
    in_project_path: pathlib.Path,
    project_dir: pathlib.Path,
):
    project_file = in_project_path / "imagecraft.yaml"
    project_file.write_text(
        (project_dir / "imagecraft.yaml").read_text(),
        encoding="utf-8",
    )
    expected_error = (project_dir / "error.txt").read_text(encoding="utf-8").strip()

    project_service = ImagecraftProjectService(
        app=APP_METADATA,
        services=None,  # ty: ignore[invalid-argument-type]
        project_dir=in_project_path,
    )
    project_service.configure(platform=None, build_for=None)

    with pytest.raises(pydantic.ValidationError) as exc_info:
        project_service.get()

    assert str(exc_info.value) == expected_error
