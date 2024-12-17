# Copyright 2023 Canonical Ltd.
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

import os
import types
from pathlib import Path

import pytest
from imagecraft import plugins


@pytest.fixture
def project_main_module() -> types.ModuleType:
    """Fixture that returns the project's principal package (imported).

    This fixture should be rewritten by "downstream" projects to return the correct
    module. Then, every test that uses this fixture will correctly test against the
    downstream project.
    """
    try:
        # This should be the project's main package; downstream projects must update this.
        import imagecraft

        main_module = imagecraft
    except ImportError:
        pytest.fail(
            "Failed to import the project's main module: check if it needs updating",
        )
    return main_module


@pytest.fixture(autouse=True, scope="session")
def _setup_parts():
    plugins.setup_plugins()


@pytest.fixture
def new_dir(tmpdir):
    """Change to a new temporary directory."""

    cwd = Path.cwd()
    os.chdir(tmpdir)

    yield tmpdir

    os.chdir(cwd)


@pytest.fixture
def extra_project_params():
    """Configuration fixture for the Project used by the default services."""
    return {}


@pytest.fixture
def default_project(extra_project_params):
    from imagecraft.models.project import Platform, Project

    parts = extra_project_params.pop("parts", {})

    return Project(
        name="default",
        version="1",
        summary="default project",
        description="default project",
        base="ubuntu@22.04",
        platforms={"amd64": Platform(build_for=["amd64"], build_on=["amd64"])},
        parts=parts,
        **extra_project_params,
    )


@pytest.fixture
def default_build_plan(default_project):
    from imagecraft.models.project import BuildPlanner

    return BuildPlanner.unmarshal(default_project.marshal()).get_build_plan()


@pytest.fixture
def default_factory(default_project, default_build_plan):
    from imagecraft.application import APP_METADATA
    from imagecraft.services import ImagecraftServiceFactory

    factory = ImagecraftServiceFactory(
        app=APP_METADATA,
        project=default_project,
    )

    factory.update_kwargs("lifecycle", build_plan=default_build_plan)
    factory.update_kwargs("package", build_plan=default_build_plan)
    return factory


@pytest.fixture
def default_application(default_factory):
    from imagecraft.application import APP_METADATA, Imagecraft

    return Imagecraft(APP_METADATA, default_factory)


@pytest.fixture
def lifecycle_service(default_project, default_factory, default_build_plan):
    from imagecraft.application import APP_METADATA
    from imagecraft.services import ImagecraftLifecycleService

    return ImagecraftLifecycleService(
        app=APP_METADATA,
        build_for="amd64",
        platform="amd64",
        project=default_project,
        services=default_factory,
        work_dir=Path("work/"),
        cache_dir=Path("cache/"),
        build_plan=default_build_plan,
    )


@pytest.fixture
def pack_service(default_project, default_factory, default_build_plan):
    from imagecraft.application import APP_METADATA
    from imagecraft.services import ImagecraftPackService

    return ImagecraftPackService(
        app=APP_METADATA,
        project=default_project,
        services=default_factory,
        build_plan=default_build_plan,
    )
