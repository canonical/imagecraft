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
# For further info, check https://github.com/canonical/kerncraft

import re

import craft_parts
import pydantic
import pytest
from craft_parts import plugins
from imagecraft.plugins import gadget


def gadget_spec(tmp_path):
    return {
        "plugin": "gadget",
        "source": str(tmp_path),
    }


def gadget_spec_with_target(tmp_path):
    return {
        "plugin": "gadget",
        "source": str(tmp_path),
        "gadget-target": "test_target",
    }


@pytest.fixture()
def gadget_plugin(tmp_path):
    return prepare_gadget_plugin(tmp_path, gadget_spec(tmp_path))


@pytest.fixture()
def gadget_plugin_with_target(tmp_path):
    return prepare_gadget_plugin(tmp_path, gadget_spec_with_target(tmp_path))


def prepare_gadget_plugin(tmp_path, spec):
    project_dirs = craft_parts.ProjectDirs(work_dir=tmp_path)
    plugin_properties = gadget.GadgetPluginProperties.unmarshal(spec)
    part_spec = plugins.extract_part_properties(spec, plugin_name="gadget")
    part = craft_parts.Part(
        "gadget",
        part_spec,
        project_dirs=project_dirs,
        plugin_properties=plugin_properties,
    )
    project_info = craft_parts.ProjectInfo(
        application_name="test",
        project_dirs=project_dirs,
        cache_dir=tmp_path,
        series="jammy",
    )
    part_info = craft_parts.PartInfo(project_info=project_info, part=part)

    # pylint: disable=attribute-defined-outside-init
    return plugins.get_plugin(
        part=part,
        part_info=part_info,
        properties=plugin_properties,
    )


def test_get_build_snaps(gadget_plugin):
    assert gadget_plugin.get_build_snaps() == set()


def test_get_build_packages(gadget_plugin):
    assert gadget_plugin.get_build_packages() == {"make"}


def test_get_build_environment(gadget_plugin):
    assert gadget_plugin.get_build_environment() == {"ARCH": "amd64", "SERIES": "jammy"}


def test_invalid_properties():
    with pytest.raises(pydantic.ValidationError) as raised:
        gadget.GadgetPlugin.properties_class.unmarshal(
            {"source": ".", "gadget-something-invalid": True},
        )
    err = raised.value.errors()
    assert len(err) == 1
    assert err[0]["loc"] == ("gadget-something-invalid",)
    assert err[0]["type"] == "value_error.extra"


def test_get_build_commands(gadget_plugin):
    cmds = gadget_plugin.get_build_commands()
    assert len(cmds) == 2
    assert cmds[0] == "make "
    assert re.match(
        "mv .*/parts/gadget/build/install .*/parts/gadget/install/gadget",
        cmds[1],
    )


def test_get_build_commands_with_target(gadget_plugin_with_target):
    cmds = gadget_plugin_with_target.get_build_commands()
    assert len(cmds) == 2
    assert cmds[0] == "make test_target"
    assert re.match(
        "mv .*/parts/gadget/build/install .*/parts/gadget/install/gadget",
        cmds[1],
    )
