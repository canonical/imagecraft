# This file is part of imagecraft.
#
# Copyright 2025 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License version 3, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

from pathlib import Path

import craft_application
import imagecraft
import pytest
from craft_application import ServiceFactory
from imagecraft.cli import register_services


@pytest.fixture
def project_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    return project_dir


@pytest.fixture
def service_factory(
    app_metadata: craft_application.AppMetadata,
    default_project_file,
) -> craft_application.ServiceFactory:
    return ServiceFactory(
        app=app_metadata,
    )  # type: ignore[assignment]


@pytest.fixture
def imagecraft_app(
    app_metadata: craft_application.AppMetadata,
    service_factory,
    mocker,
) -> imagecraft.Imagecraft:
    mocker.patch("craft_parts.lifecycle_manager._ensure_overlay_supported")
    register_services()
    return imagecraft.Imagecraft(app_metadata, service_factory)
