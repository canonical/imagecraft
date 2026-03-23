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


def test_get_build_packages(plugin):
    assert plugin.get_build_packages() == {"mmdebstrap"}


def test_get_build_snaps(plugin):
    assert plugin.get_build_snaps() == set()


@pytest.mark.parametrize(
    ("part_info", "arch", "mirror"),
    [
        ("amd64", "amd64", "http://archive.ubuntu.com/ubuntu"),
        ("arm64", "arm64", "http://ports.ubuntu.com/ubuntu-ports"),
    ],
    indirect=["part_info"],
)
def test_get_build_commands(plugin, arch, mirror):
    assert plugin.get_build_commands() == [
        f'mmdebstrap --arch={arch} --mode=root --variant=apt --format=dir noble "$CRAFT_PART_INSTALL" {mirror}',
        'rm -rf "$CRAFT_PART_INSTALL"/dev/*',
        'rm -rf "$CRAFT_PART_INSTALL"/etc/apt/sources.list.d/*',
        'rm -f "$CRAFT_PART_INSTALL"/etc/apt/sources.list',
    ]


def test_get_build_commands_packages(part_info):
    properties = MmdebstrapPluginProperties.unmarshal(
        {"mmdebstrap-suite": "noble", "mmdebstrap-packages": ["curl"]}
    )
    plugin = MmdebstrapPlugin(properties=properties, part_info=part_info)
    assert "--include=curl" in plugin.get_build_commands()[0]


def test_get_suite(part_info, mocker):
    mocker.patch(
        "imagecraft.plugins.mmdebstrap_plugin.distro.codename", return_value="noble"
    )
    properties = MmdebstrapPluginProperties.unmarshal({})
    plugin = MmdebstrapPlugin(properties=properties, part_info=part_info)

    assert plugin._get_build_base_suite() == "noble"


def test_get_suite_missing(part_info, mocker):
    mocker.patch(
        "imagecraft.plugins.mmdebstrap_plugin.distro.codename", return_value=""
    )
    properties = MmdebstrapPluginProperties.unmarshal({})
    plugin = MmdebstrapPlugin(properties=properties, part_info=part_info)

    with pytest.raises(ValueError, match="Suite could not be determined"):
        plugin._get_build_base_suite()
