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
from imagecraft.models import Platform, Project
from imagecraft.models.errors import ProjectValidationError
from pydantic import ValidationError

IMAGECRAFT_YAML_GENERIC = """
name: ubuntu-server-amd64
version: "1"
series: jammy
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]

package-repositories:
  - type: apt
    components: [main,restricted]
    url: http://archive.ubuntu.com/ubuntu/
    flavor: ubuntu
    series: jammy
    pocket: proposed
    used-for: build
  - type: apt
    components: [main,restricted]
    series: jammy
    pocket: release
    url: http://archive.ubuntu.com/ubuntu/
    used-for: run
  - type: apt
    ppa: canonical-foundations/ubuntu-image
    used-for: always
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
    plugin: ubuntu-bootstrap
    ubuntu-bootstrap-germinate:
      urls:
        - "git://git.launchpad.net/~ubuntu-core-dev/ubuntu-seeds/+git/"
      branch: jammy
      names:
        - server
        - minimal
        - standard
        - cloud-image
    ubuntu-bootstrap-pocket: updates
    ubuntu-bootstrap-extra-snaps: [core20, snapd]
    ubuntu-bootstrap-kernel: linux-generic
    stage:
      - -etc/cloud/cloud.cfg.d/90_dpkg.cfg
"""

IMAGECRAFT_YAML_SIMPLE_PLATFORM = """
name: ubuntu-server-amd64
version: "1"
series: jammy
platforms:
  amd64:
    build-for: amd64
    build-on: amd64
package-repositories:
  - type: apt
    components: [main,restricted]
    url: http://archive.ubuntu.com/ubuntu/
    flavor: ubuntu
    series: jammy
    pocket: proposed
parts:
  gadget:
    plugin: gadget
    source: https://github.com/snapcore/pc-gadget.git
    source-branch: classic
"""

IMAGECRAFT_YAML_MINIMAL_PLATFORM = """
name: ubuntu-server-amd64
version: "1"
series: jammy
platforms:
  amd64:
package-repositories:
  - type: apt
    components: [main,restricted]
    url: http://archive.ubuntu.com/ubuntu/
    flavor: ubuntu
    series: jammy
    pocket: proposed
parts:
  gadget:
    plugin: gadget
    source: https://github.com/snapcore/pc-gadget.git
    source-branch: classic
"""

IMAGECRAFT_YAML_NO_BUILD_FOR_PLATFORM = """
name: ubuntu-server-amd64
version: "1"
series: jammy
platforms:
  amd64:
    build-on: amd64
package-repositories:
  - type: apt
    components: [main,restricted]
    url: http://archive.ubuntu.com/ubuntu/
    flavor: ubuntu
    series: jammy
    pocket: proposed
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


@pytest.mark.parametrize(
    ("error_value", "error_class", "platforms"),
    [
        (
            "duplicated",
            ValidationError,
            {"build-on": ["amd64", "amd64"]},
        ),
        (
            "duplicated",
            ValidationError,
            {"build-for": ["amd64", "amd64"], "build-on": ["amd64"]},
        ),
        (
            "multiple target architectures",
            CraftValidationError,
            {"build-on": ["amd64"], "build-for": ["amd64", "arm64"]},
        ),
        (
            "multiple architectures",
            CraftValidationError,
            {"build-on": ["amd64", "arm64"], "build-for": ["arm64"]},
        ),
    ],
)
def test_project_platform_invalid(
    error_value,
    error_class,
    platforms,
):
    def load_platform(platform, raises):
        with pytest.raises(raises) as err:
            Platform(**platform)

        return str(err.value)

    assert error_value in load_platform(platforms, error_class)


@pytest.mark.parametrize(
    ("error_value", "platforms"),
    [
        # If the label maps to a valid architecture and
        # `build-for` is present, then both need to have the same value    mock_platforms = {"mock": {"build-on": "amd64"}}
        (
            "arm64 != amd64",
            {"arm64": {"build-on": ["arm64"], "build-for": ["amd64"]}},
        ),
        # Both build and target architectures must be supported
        (
            "Invalid architecture: 'noarch' must be a valid debian architecture.",
            {
                "mock": {"build-on": ["noarch"], "build-for": ["amd64"]},
            },
        ),
        (
            "Invalid architecture: 'noarch' must be a valid debian architecture.",
            {
                "mock": {"build-on": ["arm64"], "build-for": ["noarch"]},
            },
        ),
        (
            "trying to build image in one of ['powerpc']",
            {
                "powerpc": None,
            },
        ),
    ],
)
def test_project_all_platforms_invalid(yaml_loaded_data, error_value, platforms):
    def reload_project_platforms(mock_platforms=None):
        yaml_loaded_data["platforms"] = platforms
        with pytest.raises(CraftValidationError) as err:
            Project.unmarshal(yaml_loaded_data)

        return str(err.value)

    assert error_value in reload_project_platforms(
        platforms,
    )


def test_project_package_repositories_invalid(yaml_loaded_data):
    def reload_project_package_repositories(mock_package_repositories, raises):
        yaml_loaded_data["package-repositories"] = mock_package_repositories
        with pytest.raises(raises) as err:
            Project.unmarshal(yaml_loaded_data)

        return str(err.value)

    mock_package_repositories = [{"test"}]
    assert "value is not a valid dict" in reload_project_package_repositories(
        mock_package_repositories,
        ProjectValidationError,
    )
