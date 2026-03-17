# This file is part of imagecraft.
#
# Copyright 2026 Canonical Ltd.
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

import pytest
from craft_parts import PartInfo, ProjectInfo
from craft_parts.parts import Part
from imagecraft.plugins.mmdebstrap_plugin import (
    MmdebstrapPlugin,
    MmdebstrapPluginProperties,
)
from pydantic import ValidationError


@pytest.fixture
def part_info(new_dir, request):
    arch = getattr(request, "param", "amd64")
    project_info = ProjectInfo(
        application_name="test_mmdebstrap", cache_dir=new_dir, arch=arch
    )
    return PartInfo(project_info=project_info, part=Part("my-part", {}))


@pytest.fixture
def plugin(part_info):
    properties = MmdebstrapPluginProperties.unmarshal({"mmdebstrap-suite": "noble"})
    return MmdebstrapPlugin(properties=properties, part_info=part_info)


MMDEBSTRAP_CMD = 'mmdebstrap --arch="$CRAFT_ARCH_BUILD_FOR" --mode=auto --variant=minbase --format=dir'
UBUNTU_ARCHIVE_URL = "http://archive.ubuntu.com/ubuntu"
UBUNTU_PORTS_URL = "http://ports.ubuntu.com/ubuntu-ports"


def test_get_build_packages(plugin):
    assert plugin.get_build_packages() == {"mmdebstrap"}


def test_get_build_snaps(plugin):
    assert plugin.get_build_snaps() == set()


def test_get_build_commands(plugin):
    cmd = plugin.get_build_commands()

    assert (
        cmd[0] == f'{MMDEBSTRAP_CMD} noble "$CRAFT_PART_INSTALL" {UBUNTU_ARCHIVE_URL}'
    )
    assert cmd[1] == 'rm -r "$CRAFT_PART_INSTALL"/dev/*'


@pytest.mark.parametrize("part_info", ["arm64"], indirect=True)
def test_get_build_commands_arm64(plugin):
    cmd = plugin.get_build_commands()

    assert cmd[0] == f'{MMDEBSTRAP_CMD} noble "$CRAFT_PART_INSTALL" {UBUNTU_PORTS_URL}'
    assert cmd[1] == 'rm -r "$CRAFT_PART_INSTALL"/dev/*'


def test_get_build_commands_include(part_info):
    properties = MmdebstrapPluginProperties.unmarshal(
        {"mmdebstrap-suite": "noble", "mmdebstrap-include": ["apt"]}
    )
    plugin = MmdebstrapPlugin(properties=properties, part_info=part_info)
    cmd = plugin.get_build_commands()

    assert (
        cmd[0]
        == f'{MMDEBSTRAP_CMD} --include=apt noble "$CRAFT_PART_INSTALL" {UBUNTU_ARCHIVE_URL}'
    )


def test_mmdebstrap_suite_required():
    with pytest.raises(ValidationError, match="mmdebstrap-suite"):
        MmdebstrapPluginProperties.unmarshal({})
