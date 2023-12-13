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
from imagecraft.models import Project

IMAGECRAFT_YAML_GENERIC = """
name: ubuntu-server-amd64
version: "22.04"
series: jammy
platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]

parts:
  gadget:
    plugin: gadget
    source: https://github.com/snapcore/pc-gadget.git
    source-branch: classic
  rootfs:
    plugin: ubuntu-seed
    ubuntu-seed-sources:
      - "git://git.launchpad.net/~ubuntu-core-dev/ubuntu-seeds/+git/"
    ubuntu-seed-source-branch: jammy
    ubuntu-seed-seeds:
      - server
      - minimal
      - standard
      - cloud-image
    ubuntu-seed-components:
      - main
      - restricted
    ubuntu-seed-pocket: updates
    ubuntu-seed-extra-snaps: [core20, snapd]
    ubuntu-seed-active-kernel: linux-generic
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


@pytest.fixture()
def yaml_loaded_data():
    return yaml.safe_load(IMAGECRAFT_YAML_GENERIC)


def load_project_yaml(yaml_loaded_data) -> Project:
    return Project.from_yaml_data(yaml_loaded_data, Path("rockcraft.yaml"))


@pytest.mark.parametrize(
    "yaml_data",
    [
        IMAGECRAFT_YAML_GENERIC,
        IMAGECRAFT_YAML_SIMPLE_PLATFORM,
    ],
)
def test_project_unmarshal(yaml_data):
    yaml_loaded = yaml.safe_load(yaml_data)
    project = Project.unmarshal(yaml_loaded)

    for attr, v in yaml_loaded.items():
        if attr == "platforms":
            assert getattr(project, attr).keys() == v.keys()
            continue

        assert getattr(project, attr.replace("-", "_")) == v
