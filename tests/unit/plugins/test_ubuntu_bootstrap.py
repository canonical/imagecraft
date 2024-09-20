# Copyright 2023 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from unittest.mock import patch

import craft_parts
import pydantic
import pytest
from craft_archives.repo.package_repository import (  # type: ignore[import-untyped]
    PocketEnum,
)
from craft_parts import plugins
from imagecraft.models.package_repository import (
    PackageRepositoryApt,
    UsedForEnum,
)
from imagecraft.plugins import ubuntu_bootstrap

UBUNTU_BOOTSTRAP_BASIC_SPEC = {
    "plugin": "ubuntu-bootstrap",
    "ubuntu-bootstrap-pocket": "updates",
    "ubuntu-bootstrap-extra-snaps": ["core20", "snapd"],
    "ubuntu-bootstrap-extra-packages": ["apt"],
    "ubuntu-bootstrap-kernel": "linux-generic",
    "ubuntu-bootstrap-germinate": {
        "urls": ["git://git.launchpad.net/~ubuntu-core-dev/ubuntu-seeds/+git/"],
        "branch": "jammy",
        "names": ["server", "minimal", "standard", "cloud-image"],
    },
}


UBUNTU_BOOTSTRAP_NO_SOURCE_BRANCH = {
    "plugin": "ubuntu-bootstrap",
    "ubuntu-bootstrap-pocket": "updates",
    "ubuntu-bootstrap-extra-snaps": ["core20", "snapd"],
    "ubuntu-bootstrap-extra-packages": ["apt"],
    "ubuntu-bootstrap-kernel": "linux-generic",
    "ubuntu-bootstrap-germinate": {
        "urls": ["git://git.launchpad.net/~ubuntu-core-dev/ubuntu-seeds/+git/"],
        "names": ["server", "minimal", "standard", "cloud-image"],
    },
}


@pytest.fixture()
def ubuntu_bootstrap_plugin():
    def _ubuntu_bootstrap_plugin(spec, tmp_path):
        project_dirs = craft_parts.ProjectDirs(work_dir=tmp_path)
        plugin_properties = ubuntu_bootstrap.UbuntuBootstrapPluginProperties.unmarshal(
            spec,
        )
        part_spec = plugins.extract_part_properties(
            spec,
            plugin_name="ubuntu-bootstrap",
        )
        part = craft_parts.Part(
            "rootfs",
            part_spec,
            project_dirs=project_dirs,
            plugin_properties=plugin_properties,
        )
        project_vars = {
            "version": "1",
        }
        package_repositories = [
            PackageRepositoryApt.unmarshal(
                {
                    "type": "apt",
                    "used_for": UsedForEnum.BUILD,
                    "pocket": PocketEnum.RELEASE,
                    "components": ["main", "restricted"],
                    "flavor": "ubuntu",
                    "url": "http://archive.ubuntu.com/ubuntu/",
                },
            ),
        ]

        project_info = craft_parts.ProjectInfo(
            application_name="test",
            project_dirs=project_dirs,
            cache_dir=tmp_path,
            project_vars=project_vars,
            series="jammy",
            package_repositories_=package_repositories,
        )
        part_info = craft_parts.PartInfo(project_info=project_info, part=part)

        # pylint: disable=attribute-defined-outside-init
        return plugins.get_plugin(
            part=part,
            part_info=part_info,
            properties=plugin_properties,
        )

    return _ubuntu_bootstrap_plugin


def test_invalid_properties():
    spec = UBUNTU_BOOTSTRAP_BASIC_SPEC.copy()
    spec.update({"ubuntu-bootstrap-something-invalid": True})
    with pytest.raises(pydantic.ValidationError) as raised:
        ubuntu_bootstrap.UbuntuBootstrapPlugin.properties_class.unmarshal(spec)
    err = raised.value.errors()
    assert len(err) == 1
    assert err[0]["loc"] == ("ubuntu-bootstrap-something-invalid",)
    assert err[0]["type"] == "value_error.extra"


def test_missing_properties():
    with pytest.raises(pydantic.ValidationError) as raised:
        ubuntu_bootstrap.UbuntuBootstrapPlugin.properties_class.unmarshal(
            {"gadget-something-invalid": True},
        )
    err = raised.value.errors()
    assert len(err) == 1
    assert err[0]["loc"] == ("ubuntu-bootstrap-germinate",)
    assert err[0]["type"] == "value_error.missing"


def test_get_build_snaps(ubuntu_bootstrap_plugin, tmp_path):
    plugin = ubuntu_bootstrap_plugin(UBUNTU_BOOTSTRAP_BASIC_SPEC, tmp_path)
    assert plugin.get_build_snaps() == set("ubuntu-image")


def test_get_build_packages(ubuntu_bootstrap_plugin, tmp_path):
    plugin = ubuntu_bootstrap_plugin(UBUNTU_BOOTSTRAP_BASIC_SPEC, tmp_path)
    assert plugin.get_build_packages() == set()


def test_get_build_environment(ubuntu_bootstrap_plugin, tmp_path):
    plugin = ubuntu_bootstrap_plugin(UBUNTU_BOOTSTRAP_BASIC_SPEC, tmp_path)
    assert plugin.get_build_environment() == {}


def test_get_build_commands(ubuntu_bootstrap_plugin, mocker, tmp_path):
    plugin = ubuntu_bootstrap_plugin(UBUNTU_BOOTSTRAP_BASIC_SPEC, tmp_path)

    with patch(
        "imagecraft.plugins.ubuntu_bootstrap.ubuntu_image_cmds_build_rootfs",
        return_value=["build_rootfs_cmd1", "build_rootfs_cmd2"],
    ) as build_rootfs_patcher:
        assert plugin.get_build_commands() == [
            "build_rootfs_cmd1",
            "build_rootfs_cmd2",
        ]

        build_rootfs_patcher.assert_called_with(
            "jammy",
            "amd64",
            "release",
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-germinate"].get("urls"),
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-germinate"].get("branch"),
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-germinate"].get("names"),
            ["main", "restricted"],
            "ubuntu",
            "http://archive.ubuntu.com/ubuntu/",
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-pocket"],
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-kernel"],
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-extra-snaps"],
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-extra-packages"],
            None,
            None,
            debug=False,
        )

    with patch(
        "imagecraft.plugins.ubuntu_bootstrap.ubuntu_image_cmds_build_rootfs",
        return_value=["build_rootfs_cmd1", "build_rootfs_cmd2"],
    ) as build_rootfs_patcher:
        # test without source_branch
        plugin = ubuntu_bootstrap_plugin(UBUNTU_BOOTSTRAP_NO_SOURCE_BRANCH, tmp_path)

        assert plugin.get_build_commands() == [
            "build_rootfs_cmd1",
            "build_rootfs_cmd2",
        ]

        build_rootfs_patcher.assert_called_with(
            "jammy",
            "amd64",
            "release",
            UBUNTU_BOOTSTRAP_NO_SOURCE_BRANCH["ubuntu-bootstrap-germinate"].get("urls"),
            "jammy",
            UBUNTU_BOOTSTRAP_NO_SOURCE_BRANCH["ubuntu-bootstrap-germinate"].get(
                "names",
            ),
            ["main", "restricted"],
            "ubuntu",
            "http://archive.ubuntu.com/ubuntu/",
            UBUNTU_BOOTSTRAP_NO_SOURCE_BRANCH["ubuntu-bootstrap-pocket"],
            UBUNTU_BOOTSTRAP_NO_SOURCE_BRANCH["ubuntu-bootstrap-kernel"],
            UBUNTU_BOOTSTRAP_NO_SOURCE_BRANCH["ubuntu-bootstrap-extra-snaps"],
            UBUNTU_BOOTSTRAP_NO_SOURCE_BRANCH["ubuntu-bootstrap-extra-packages"],
            None,
            None,
            debug=False,
        )

    # Test with a customization package repository
    with patch(
        "imagecraft.plugins.ubuntu_bootstrap.ubuntu_image_cmds_build_rootfs",
        return_value=["build_rootfs_cmd1", "build_rootfs_cmd2"],
    ) as build_rootfs_patcher:
        plugin._part_info.project_info.package_repositories_ = [
            PackageRepositoryApt.unmarshal(
                {
                    "type": "apt",
                    "used_for": UsedForEnum.BUILD,
                    "pocket": PocketEnum.RELEASE,
                    "components": ["main", "restricted"],
                    "flavor": "ubuntu",
                    "url": "http://archive.ubuntu.com/ubuntu/",
                },
            ),
            PackageRepositoryApt.unmarshal(
                {
                    "type": "apt",
                    "used_for": UsedForEnum.RUN,
                    "pocket": PocketEnum.PROPOSED,
                    "components": ["universe", "restricted"],
                },
            ),
        ]

        assert plugin.get_build_commands() == [
            "build_rootfs_cmd1",
            "build_rootfs_cmd2",
        ]

        build_rootfs_patcher.assert_called_with(
            "jammy",
            "amd64",
            "release",
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-germinate"].get("urls"),
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-germinate"].get("branch"),
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-germinate"].get("names"),
            ["main", "restricted"],
            "ubuntu",
            "http://archive.ubuntu.com/ubuntu/",
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-pocket"],
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-kernel"],
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-extra-snaps"],
            UBUNTU_BOOTSTRAP_BASIC_SPEC["ubuntu-bootstrap-extra-packages"],
            ["universe", "restricted"],
            "proposed",
            debug=False,
        )
