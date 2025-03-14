# This file is part of imagecraft.
#
# Copyright 2023-2025 Canonical Ltd.
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
from craft_application import ProjectService, ServiceFactory
from imagecraft import cli, plugins
from imagecraft.application import APP_METADATA


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


@pytest.fixture
def app_metadata():
    return APP_METADATA


@pytest.fixture(autouse=True)
def reset_features():
    from craft_parts import Features

    Features.reset()
    yield
    Features.reset()


@pytest.fixture
def enable_partitions_feature(reset_features):
    """Enable the partitions feature."""
    from craft_parts import Features

    Features(enable_partitions=True)


@pytest.fixture
def enable_overlay_feature(reset_features):
    """Enable the overlay feature."""
    from craft_parts import Features

    Features(enable_overlay=True)


@pytest.fixture
def enable_feature(reset_features):
    """Enable the both feature."""
    from craft_parts import Features

    Features(enable_overlay=True, enable_partitions=True)


@pytest.fixture(autouse=True, scope="session")
def setup_plugins():
    plugins.setup_plugins()


@pytest.fixture(autouse=True, scope="session")
def register_services():
    cli.register_services()


@pytest.fixture
def new_dir(tmpdir):
    """Change to a new temporary directory."""

    cwd = Path.cwd()
    os.chdir(tmpdir)

    yield tmpdir

    os.chdir(cwd)


@pytest.fixture
def default_project_yaml():
    return """\
name: default
version: "1.0"
summary: "default project"
description: "default project"
base: bare
build-base: ubuntu@24.04
license: "MIT"

platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
parts:
  my-part:
    plugin: nil
volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500MiB
"""


@pytest.fixture
def default_project_file(in_project_path, default_project_yaml):
    project_file = in_project_path / "imagecraft.yaml"
    project_file.write_text(default_project_yaml)

    return project_file


@pytest.fixture
def default_factory(default_project_file, app_metadata):
    factory = ServiceFactory(
        app=app_metadata,
    )

    factory.update_kwargs("project", project_dir=default_project_file.parent)
    factory.update_kwargs("lifecycle", work_dir=Path("work/"), cache_dir=Path("cache/"))

    project: ProjectService = factory.get("project")
    project.configure(platform=None, build_for=None)

    return factory


@pytest.fixture
def default_application(default_factory, app_metadata):
    from imagecraft.application import Imagecraft

    return Imagecraft(app_metadata, default_factory)


@pytest.fixture
def lifecycle_service(default_factory, app_metadata, enable_partitions_feature):
    return default_factory.get_class("lifecycle")(
        app=app_metadata,
        build_for="amd64",
        platform="amd64",
        services=default_factory,
        work_dir=Path("work/"),
        cache_dir=Path("cache/"),
    )


@pytest.fixture
def pack_service(default_factory):
    return default_factory.get("package")
