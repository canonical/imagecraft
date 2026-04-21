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
from imagecraft.plugins.uc_prepare_plugin import (
    UcPreparePlugin,
    UcPreparePluginProperties,
)
from pydantic import ValidationError


@pytest.fixture
def part_info(new_dir):
    project_info = ProjectInfo(application_name="test_uc_prepare", cache_dir=new_dir)
    return PartInfo(project_info=project_info, part=Part("my-part", {}))


def test_missing_model_assertion():
    with pytest.raises(ValidationError, match="uc-prepare-model-assert"):
        UcPreparePluginProperties.unmarshal({})


def test_preseed_sign_key_without_preseed():
    with pytest.raises(ValueError, match="cannot be used without uc-prepare-preseed"):
        UcPreparePluginProperties.unmarshal(
            {
                "uc-prepare-model-assert": "model.assert",
                "uc-prepare-preseed-sign-key": "sign-key",
            }
        )


def test_sysfs_overlay_without_preseed():
    with pytest.raises(ValueError, match="cannot be used without uc-prepare-preseed"):
        UcPreparePluginProperties.unmarshal(
            {
                "uc-prepare-model-assert": "model.assert",
                "uc-prepare-sysfs-overlay": "./sysfs",
            }
        )


def test_get_build_packages_without_preseed(part_info):
    properties = UcPreparePluginProperties.unmarshal(
        {"uc-prepare-model-assert": "model.assert"}
    )
    plugin = UcPreparePlugin(properties=properties, part_info=part_info)

    assert plugin.get_build_packages() == set()


def test_get_build_packages_with_preseed_same_arch(part_info, mocker):
    mocker.patch.object(part_info, "host_arch", "amd64")
    mocker.patch.object(part_info, "target_arch", "amd64")
    properties = UcPreparePluginProperties.unmarshal(
        {"uc-prepare-model-assert": "model.assert", "uc-prepare-preseed": True}
    )
    plugin = UcPreparePlugin(properties=properties, part_info=part_info)

    assert plugin.get_build_packages() == set()


def test_get_build_packages_with_preseed_different_arch(part_info, mocker):
    mocker.patch.object(part_info, "host_arch", "amd64")
    mocker.patch.object(part_info, "target_arch", "arm64")
    properties = UcPreparePluginProperties.unmarshal(
        {"uc-prepare-model-assert": "model.assert", "uc-prepare-preseed": True}
    )
    plugin = UcPreparePlugin(properties=properties, part_info=part_info)

    assert plugin.get_build_packages() == {"qemu-user-static"}


def test_get_build_commands(part_info):
    properties = UcPreparePluginProperties.unmarshal(
        {"uc-prepare-model-assert": "model.assert"}
    )

    plugin = UcPreparePlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"snap prepare-image --validation=ignore model.assert {part_info.part_install_dir}"
    )


def test_get_build_commands_with_preseed(part_info):
    properties = UcPreparePluginProperties.unmarshal(
        {
            "uc-prepare-model-assert": "model.assert",
            "uc-prepare-preseed": True,
        }
    )
    plugin = UcPreparePlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"snap prepare-image --preseed --validation=ignore model.assert {part_info.part_install_dir}"
    )


def test_get_build_commands_with_preseed_sign_key(part_info):
    properties = UcPreparePluginProperties.unmarshal(
        {
            "uc-prepare-model-assert": "model.assert",
            "uc-prepare-preseed": True,
            "uc-prepare-preseed-sign-key": "sign-key",
        }
    )
    plugin = UcPreparePlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"snap prepare-image --preseed --preseed-sign-key=sign-key --validation=ignore model.assert {part_info.part_install_dir}"
    )


def test_get_build_commands_with_apparmor_dir(part_info):
    apparmor_features_dir = "/sys/kernel/security/somewhere"
    properties = UcPreparePluginProperties.unmarshal(
        {
            "uc-prepare-model-assert": "model.assert",
            "uc-prepare-preseed": True,
            "uc-prepare-apparmor-features-dir": apparmor_features_dir,
        }
    )
    plugin = UcPreparePlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"snap prepare-image --preseed --apparmor-features-dir={apparmor_features_dir} --validation=ignore model.assert {part_info.part_install_dir}"
    )


def test_get_build_commands_with_sysfs_overlay(part_info):
    sysfs_overlay = "./sysfs-overlay"
    properties = UcPreparePluginProperties.unmarshal(
        {
            "uc-prepare-model-assert": "model.assert",
            "uc-prepare-preseed": True,
            "uc-prepare-sysfs-overlay": sysfs_overlay,
        }
    )
    plugin = UcPreparePlugin(properties=properties, part_info=part_info)

    assert (
        plugin.get_build_commands()[0]
        == f"snap prepare-image --preseed --sysfs-overlay={sysfs_overlay} --validation=ignore model.assert {part_info.part_install_dir}"
    )
