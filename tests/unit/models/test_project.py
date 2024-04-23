# This file is part of imagecraft.
#
# Copyright (C) 2022 Canonical Ltd
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

import pytest
import yaml
from craft_application.errors import CraftValidationError
from imagecraft.models import PackageRepository, Platform, Project
from pydantic import ValidationError

IMAGECRAFT_YAML_GENERIC = """
name: ubuntu-server-amd64
version: "22.04"
series: jammy
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]

package-repositories:
  - type: apt
    components: [main,restricted]
    suites: [jammy]
    url: http://archive.ubuntu.com/ubuntu/
    flavor: ubuntu
    pocket: proposed
    used-for: build
  - type: apt
    components: [main,restricted]
    suites: [jammy]
  - type: apt
    components: [main,restricted]
    suites: [jammy]
    url: http://archive.ubuntu.com/ubuntu/
    used-for: run
  - type: apt
    ppa: canonical-foundations/ubuntu-image
    used-for: run
  - type: apt
    ppa: canonical-foundations/ubuntu-image-private-test
    auth: "sil2100:vVg74j6SM8WVltwpxDRJ"
    used-for: run

parts:
  gadget:
    plugin: gadget
    source: https://github.com/snapcore/pc-gadget.git
    source-branch: classic
  rootfs:
    plugin: ubuntu-seed
    ubuntu-seed-germinate:
      urls:
        - "git://git.launchpad.net/~ubuntu-core-dev/ubuntu-seeds/+git/"
      branch: jammy
      names:
        - server
        - minimal
        - standard
        - cloud-image
    ubuntu-seed-components:
      - main
      - restricted
    ubuntu-seed-pocket: updates
    ubuntu-seed-extra-snaps: [core20, snapd]
    ubuntu-seed-kernel: linux-generic
    stage:
      - -etc/cloud/cloud.cfg.d/90_dpkg.cfg
"""

IMAGECRAFT_YAML_SIMPLE_PLATFORM = """
name: ubuntu-server-amd64
version: "22.04"
series: jammy
platforms:
  amd64:
    build-for: amd64
    build-on: amd64
parts:
  gadget:
    plugin: gadget
    source: https://github.com/snapcore/pc-gadget.git
    source-branch: classic
"""

IMAGECRAFT_YAML_MINIMAL_PLATFORM = """
name: ubuntu-server-amd64
version: "22.04"
series: jammy
platforms:
  amd64:
parts:
  gadget:
    plugin: gadget
    source: https://github.com/snapcore/pc-gadget.git
    source-branch: classic
"""

IMAGECRAFT_YAML_NO_BUILD_FOR_PLATFORM = """
name: ubuntu-server-amd64
version: "22.04"
series: jammy
platforms:
  amd64:
    build-on: amd64
parts:
  gadget:
    plugin: gadget
    source: https://github.com/snapcore/pc-gadget.git
    source-branch: classic
"""


@pytest.fixture()
def yaml_loaded_data():
    return yaml.safe_load(IMAGECRAFT_YAML_GENERIC)


def load_project_yaml(yaml_loaded_data) -> Project:
    return Project.from_yaml_data(yaml_loaded_data, Path("imagecraft.yaml"))


@pytest.mark.parametrize(
    "yaml_data",
    [
        IMAGECRAFT_YAML_GENERIC,
        IMAGECRAFT_YAML_SIMPLE_PLATFORM,
        IMAGECRAFT_YAML_MINIMAL_PLATFORM,
        IMAGECRAFT_YAML_NO_BUILD_FOR_PLATFORM,
    ],
)
def test_project_unmarshal(yaml_data):
    yaml_loaded = yaml.safe_load(yaml_data)
    project = Project.unmarshal(yaml_loaded)

    for attr, v in yaml_loaded.items():
        if attr == "platforms":
            assert getattr(project, attr).keys() == v.keys()
            continue
        if attr == "package-repositories":
            continue
        assert getattr(project, attr.replace("-", "_")) == v


def test_project_platform_invalid():
    def load_platform(platform, raises):
        with pytest.raises(raises) as err:
            Platform(**platform)

        return str(err.value)

    # lists must be unique
    mock_platform = {"build-on": ["amd64", "amd64"]}
    assert "duplicated" in load_platform(mock_platform, ValidationError)

    mock_platform = {"build-for": ["amd64", "amd64"], "build-on": ["amd64"]}
    assert "duplicated" in load_platform(mock_platform, ValidationError)

    # build-for must be only 1 element
    mock_platform = {"build-on": ["amd64"], "build-for": ["amd64", "arm64"]}
    assert "multiple target architectures" in load_platform(
        mock_platform,
        CraftValidationError,
    )

    # build-on must be only 1 element
    mock_platform = {"build-on": ["amd64", "arm64"]}
    assert "multiple architectures" in load_platform(
        mock_platform,
        CraftValidationError,
    )

    # If build_for is provided, then build_on must also be
    mock_platform = {"build-for": ["arm64"]}
    assert "'build_for' expects 'build_on' to also be provided." in load_platform(
        mock_platform,
        CraftValidationError,
    )


def test_project_all_platforms_invalid(yaml_loaded_data):
    def reload_project_platforms(new_platforms=None):
        yaml_loaded_data["platforms"] = mock_platforms
        with pytest.raises(CraftValidationError) as err:
            Project.unmarshal(yaml_loaded_data)

        return str(err.value)

    # A platform validation error must have an explicit prefix indicating
    # the platform entry for which the validation has failed
    mock_platforms = {"foo": {"build-for": ["amd64"]}}
    assert "'build_for' expects 'build_on'" in reload_project_platforms(
        mock_platforms,
    )

    # If the label maps to a valid architecture and
    # `build-for` is present, then both need to have the same value    mock_platforms = {"mock": {"build-on": "amd64"}}
    mock_platforms = {"arm64": {"build-on": ["arm64"], "build-for": ["amd64"]}}
    assert "arm64 != amd64" in reload_project_platforms(mock_platforms)

    # Both build and target architectures must be supported
    mock_platforms = {
        "mock": {"build-on": ["noarch"], "build-for": ["amd64"]},
    }
    assert "none of these build architectures is supported" in reload_project_platforms(
        mock_platforms,
    )

    mock_platforms = {
        "mock": {"build-on": ["arm64"], "build-for": ["noarch"]},
    }
    assert "build image for target architecture noarch" in reload_project_platforms(
        mock_platforms,
    )

    mock_platforms = {
        "unsupported": None,
    }
    assert "Invalid platform unsupported" in reload_project_platforms(
        mock_platforms,
    )

    mock_platforms = None
    assert "No platforms were specified." in reload_project_platforms(
        mock_platforms,
    )


def test_project_package_repositories_invalid():
    def load_package_repositories(data, raises):
        with pytest.raises(raises) as err:
            PackageRepository.unmarshal(data)

        return str(err.value)

    mock_package_repositories = {
        "type": "apt",
        "pocket": "invalid",
    }
    assert "is not a valid enumeration member" in load_package_repositories(
        mock_package_repositories,
        ValidationError,
    )

    mock_package_repositories = {
        "type": "apt",
        "used-for": "test",
    }
    assert "is not a valid enumeration member" in load_package_repositories(
        mock_package_repositories,
        ValidationError,
    )

    ## Test PPA
    mock_package_repositories = {
        "type": "apt",
        "ppa": "test",
        "used-for": "test",
    }
    assert "is not a valid enumeration member" in load_package_repositories(
        mock_package_repositories,
        ValidationError,
    )

    ## Test invalid key-id
    mock_package_repositories = {
        "type": "apt",
        "ppa": "test",
        "key-id": "tooshort",
    }
    assert "ensure this value has at least 40 characters" in load_package_repositories(
        mock_package_repositories,
        ValidationError,
    )

    ## Test invalid auth
    mock_package_repositories = {
        "type": "apt",
        "ppa": "test",
        "auth": "invalid",
    }
    assert "string does not match regex" in load_package_repositories(
        mock_package_repositories,
        ValidationError,
    )
