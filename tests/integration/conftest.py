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


@pytest.fixture
def empty_project_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    return project_dir


@pytest.fixture
def app_metadata():
    return imagecraft.application.APP_METADATA


@pytest.fixture
def service_factory(
    app_metadata: craft_application.AppMetadata,
) -> craft_application.ServiceFactory:
    from imagecraft.services import ImagecraftServiceFactory

    return ImagecraftServiceFactory(
        app=app_metadata,
    )


@pytest.fixture
def imagecraft_app(
    app_metadata: craft_application.AppMetadata,
    service_factory: craft_application.ServiceFactory,
) -> imagecraft.Imagecraft:
    return imagecraft.Imagecraft(app_metadata, service_factory)
