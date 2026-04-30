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
from imagecraft.plugins.snap_preseed_plugin import (
    SnapPreseedPlugin,
    SnapPreseedPluginProperties,
)
from pydantic import ValidationError


@pytest.fixture
def part_info(new_dir):
    project_info = ProjectInfo(application_name="test_snap_preseed", cache_dir=new_dir)
    return PartInfo(project_info=project_info, part=Part("my-part", {}))


def test_missing_snaps_or_model_assert_key():
    with pytest.raises(
        ValidationError, match="At least one of snap-preseed-snaps or snap-preseed-model-assert"
    ):
        SnapPreseedPluginProperties.unmarshal({})


@pytest.fixture
def cmd_prefix(part_info):
    return f"snap prepare-image --classic --arch={part_info.target_arch} --validation=enforce"


def test_snap_preseed_snaps_validation():
    with pytest.raises(ValidationError, match="Invalid snap reference"):
        SnapPreseedPluginProperties.unmarshal(
            {
                "snap-preseed-snaps": ["invalid--snap"],
            }
        )


def test_get_build_commands(part_info, cmd_prefix):
    properties = SnapPreseedPluginProperties.unmarshal(
        {"snap-preseed-snaps": ["core24", "hello-world/latest/stable"]}
    )

    plugin = SnapPreseedPlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"{cmd_prefix} --snap=core24 --snap=hello-world=latest/stable '' {part_info.part_install_dir}"
    )


def test_get_build_commands_with_model_assertion(part_info, cmd_prefix):
    properties = SnapPreseedPluginProperties.unmarshal(
        {
            "snap-preseed-model-assert": "model.assert",
        }
    )

    plugin = SnapPreseedPlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"{cmd_prefix} model.assert {part_info.part_install_dir}"
    )


def test_get_build_commands_with_assertions(part_info, cmd_prefix):
    properties = SnapPreseedPluginProperties.unmarshal(
        {
            "snap-preseed-snaps": ["core24"],
            "snap-preseed-assertions": ["system-user.assert", "account.assert"],
        }
    )

    plugin = SnapPreseedPlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"{cmd_prefix} --assert=system-user.assert --assert=account.assert --snap=core24 '' {part_info.part_install_dir}"
    )


def test_get_build_commands_with_revisions(part_info, cmd_prefix):
    properties = SnapPreseedPluginProperties.unmarshal(
        {
            "snap-preseed-snaps": ["core24"],
            "snap-preseed-revisions": "./revisions.txt",
        }
    )

    plugin = SnapPreseedPlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"{cmd_prefix} --revisions=./revisions.txt --snap=core24 '' {part_info.part_install_dir}"
    )


def test_get_build_commands_with_write_revisions(part_info, cmd_prefix):
    properties = SnapPreseedPluginProperties.unmarshal(
        {
            "snap-preseed-snaps": ["core24"],
            "snap-preseed-write-revisions": True,
        }
    )

    plugin = SnapPreseedPlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"{cmd_prefix} --write-revisions={part_info.part_install_dir}/seed.manifest --snap=core24 '' {part_info.part_install_dir}"
    )


def test_get_build_commands_with_write_revisions_path(part_info, cmd_prefix):
    properties = SnapPreseedPluginProperties.unmarshal(
        {
            "snap-preseed-snaps": ["core24"],
            "snap-preseed-write-revisions": "./revisions.txt",
        }
    )

    plugin = SnapPreseedPlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"{cmd_prefix} --write-revisions={part_info.part_install_dir}/revisions.txt --snap=core24 '' {part_info.part_install_dir}"
    )


def test_get_build_commands_with_channel(part_info, cmd_prefix):
    properties = SnapPreseedPluginProperties.unmarshal(
        {
            "snap-preseed-snaps": ["core24"],
            "snap-preseed-channel": "latest/stable",
        }
    )

    plugin = SnapPreseedPlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"{cmd_prefix} --channel=latest/stable --snap=core24 '' {part_info.part_install_dir}"
    )


def test_get_build_commands_with_validation_enforce(part_info):
    properties = SnapPreseedPluginProperties.unmarshal(
        {
            "snap-preseed-snaps": ["core24"],
            "snap-preseed-validation": "enforce",
        }
    )

    plugin = SnapPreseedPlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"snap prepare-image --classic --arch={part_info.target_arch} --validation=enforce --snap=core24 '' {part_info.part_install_dir}"
    )
