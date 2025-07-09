# This file is part of imagecraft.
#
# Copyright 2023-2025 Canonical Ltd.
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

import io
import pathlib
from pathlib import Path

import pytest
import yaml
from craft_application import util
from craft_application.errors import CraftValidationError
from imagecraft.models import Platform, Project
from pydantic import ValidationError

IMAGECRAFT_YAML_GENERIC = """
name: ubuntu-server-amd64
version: "1"
base: bare
build-base: ubuntu@24.04

platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
parts:
  rootfs:
    plugin: nil
filesystems:
  default:
  - mount: /
    device: (volume/pc/rootfs)
  - mount: /boot/efi
    device: (volume/pc/efi)
volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500 M
      - name: rootfs
        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
        filesystem: ext4
        filesystem-label: writable
        role: system-data
        size: 6G
"""

IMAGECRAFT_YAML_SIMPLE_PLATFORM = """
name: ubuntu-server-amd64
version: "1"
base: bare
build-base: ubuntu@24.04

platforms:
  amd64:
    build-for: amd64
    build-on: amd64
parts:
  rootfs:
    plugin: nil
filesystems:
  default:
  - mount: /
    device: (default)
volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500 M
"""

IMAGECRAFT_YAML_MINIMAL_PLATFORM = """
name: ubuntu-server-amd64
version: "1"
base: bare
build-base: ubuntu@24.04

platforms:
  amd64:
parts:
  rootfs:
    plugin: nil
filesystems:
  default:
  - mount: /
    device: (default)
volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500 M
"""

IMAGECRAFT_YAML_INVALID_BASE = """
name: ubuntu-server-amd64
version: "1"
base: ubuntu@24.04
build-base: ubuntu@24.04

platforms:
  amd64:
parts:
  rootfs:
    plugin: nil
filesystems:
  default:
  - mount: /
    device: (default)
volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500 M
"""

IMAGECRAFT_YAML_MISSING_BUILD_BASE = """
name: ubuntu-server-amd64
version: "1"
base: bare

platforms:
  amd64:
parts:
  rootfs:
    plugin: nil
filesystems:
  default:
  - mount: /
    device: (default)
volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500 M
"""

pytestmark = [pytest.mark.usefixtures("enable_features")]


@pytest.fixture
def yaml_loaded_data():
    return util.safe_yaml_load(io.StringIO(IMAGECRAFT_YAML_GENERIC))


def load_project_yaml(yaml_loaded_data) -> Project:
    return Project.from_yaml_data(yaml_loaded_data, Path("imagecraft.yaml"))


@pytest.mark.parametrize(
    "yaml_data",
    [
        IMAGECRAFT_YAML_GENERIC,
        IMAGECRAFT_YAML_SIMPLE_PLATFORM,
        IMAGECRAFT_YAML_MINIMAL_PLATFORM,
    ],
)
def test_project_unmarshal(yaml_data):
    yaml_loaded = yaml.safe_load(yaml_data)
    project_path = pathlib.Path("myproject.yaml")
    project = Project.from_yaml_data(yaml_loaded, project_path)

    for attr, v in yaml_loaded.items():
        if attr == "platforms":
            assert getattr(project, attr).keys() == v.keys()
            continue
        if attr == "volumes":
            assert getattr(project, attr).keys() == v.keys()
            continue
        if attr == "filesystems":
            assert getattr(project, attr).keys() == v.keys()
            continue
        assert getattr(project, attr.replace("-", "_")) == v


@pytest.mark.parametrize(
    ("error_value", "error_class", "platforms"),
    [
        (
            "duplicate values",
            ValidationError,
            {"build-on": ["amd64", "amd64"]},
        ),
        (
            "2 validation errors for Platform\nbuild-for.list[str]\n  List should have at most 1 item after validation, not 2",
            ValidationError,
            {"build-for": ["amd64", "amd64"], "build-on": ["amd64"]},
        ),
        (
            "2 validation errors for Platform\nbuild-for.list[str]\n  List should have at most 1 item after validation, not 2",
            ValidationError,
            {"build-on": ["amd64"], "build-for": ["amd64", "arm64"]},
        ),
        (
            "build-for\n  Field required",
            ValidationError,
            {"build-on": ["amd64"]},
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
        # Both build and target architectures must be supported
        (
            "'noarch' is not a valid Debian architecture",
            {
                "mock": {"build-on": ["noarch"], "build-for": ["amd64"]},
            },
        ),
        (
            "'noarch' is not a valid Debian architecture",
            {
                "mock": {"build-on": ["arm64"], "build-for": ["noarch"]},
            },
        ),
    ],
)
def test_project_all_platforms_invalid(yaml_loaded_data, error_value, platforms):
    def reload_project_platforms(mock_platforms=None):
        yaml_loaded_data["platforms"] = platforms
        project_path = pathlib.Path("myproject.yaml")
        with pytest.raises(CraftValidationError) as err:
            Project.from_yaml_data(yaml_loaded_data, project_path)

        return str(err.value)

    assert error_value in reload_project_platforms(
        platforms,
    )


@pytest.mark.parametrize(
    ("error_value", "yaml_data"),
    [
        (
            "Bad myproject.yaml content:\n- input should be 'bare' (in field 'base')",
            IMAGECRAFT_YAML_INVALID_BASE,
        ),
        (
            "Bad myproject.yaml content:\n- field 'build-base' required in top-level configuration",
            IMAGECRAFT_YAML_MISSING_BUILD_BASE,
        ),
    ],
)
def test_project_invalid_base(error_value, yaml_data):
    yaml_loaded = yaml.safe_load(yaml_data)
    project_path = pathlib.Path("myproject.yaml")
    with pytest.raises(CraftValidationError) as err:
        Project.from_yaml_data(yaml_loaded, project_path)

    assert error_value == str(err.value)


IMAGECRAFT_YAML_MULTIPLE_VOLUMES = """
name: ubuntu-server-amd64
version: "1"
base: bare
build-base: ubuntu@24.04

platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
parts:
  rootfs:
    plugin: nil
filesystems:
  default:
  - mount: /
    device: (default)
volumes:
  pc:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500M
  pc2:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500M
"""

IMAGECRAFT_YAML_INVALID_VOLUME_NAME = """
name: ubuntu-server-amd64
version: "1"
base: bare
build-base: ubuntu@24.04

platforms:
  amd64:
    build-for: [amd64]
    build-on: [amd64]
parts:
  rootfs:
    plugin: nil
filesystems:
  default:
  - mount: /
    device: (default)
volumes:
  invalid_test-:
    schema: gpt
    structure:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500M
"""


@pytest.mark.parametrize(
    ("error_value", "yaml_data"),
    [
        (
            "Bad myproject.yaml content:\n- dictionary should have at most 1 item after validation, not 2 (in field 'volumes')",
            IMAGECRAFT_YAML_MULTIPLE_VOLUMES,
        ),
        (
            "Bad myproject.yaml content:\n- volume names must only contain lowercase letters, numbers, and hyphens, and may not begin or end with a hyphen. (in field 'volumes.invalid_test-.[key]')",
            IMAGECRAFT_YAML_INVALID_VOLUME_NAME,
        ),
    ],
)
def test_project_invalid_volumes(error_value, yaml_data):
    yaml_loaded = yaml.safe_load(yaml_data)
    project_path = pathlib.Path("myproject.yaml")
    with pytest.raises(CraftValidationError) as err:
        Project.from_yaml_data(yaml_loaded, project_path)

    assert error_value == str(err.value)


@pytest.mark.parametrize(
    ("error_lines", "filesystems_val"),
    [
        (
            ["- input should be a valid dictionary (in field 'filesystems')"],
            [],
        ),
        (
            ["- input should be a valid list (in field 'filesystems.test')"],
            {"test": {}},
        ),
        (
            [
                "- the first entry in a filesystem must map the '/' mount. (in field 'filesystems.test')"
            ],
            {
                "test": [
                    {
                        "mount": "/test",
                        "device": "(default)",
                    }
                ]
            },
        ),
        (
            [
                "- field 'mount' required in 'filesystems.test' configuration",
                "- field 'device' required in 'filesystems.test' configuration",
                "- extra inputs are not permitted (in field 'filesystems.test.test')",
            ],
            {
                "test": [
                    {
                        "test": "foo",
                    }
                ]
            },
        ),
        (
            [
                "- list should have at least 1 item after validation, not 0 (in field 'filesystems.test')",
            ],
            {"test": []},
        ),
        (
            [
                "- dictionary should have at most 1 item after validation, not 2 (in field 'filesystems')",
            ],
            {
                "default": [
                    {
                        "mount": "/",
                        "device": "(default)",
                    },
                ],
                "foo": [
                    {
                        "mount": "/",
                        "device": "(default)",
                    }
                ],
            },
        ),
    ],
)
def test_project_invalid_filesystems(error_lines, filesystems_val):
    yaml_loaded = yaml.safe_load(IMAGECRAFT_YAML_GENERIC)
    yaml_loaded["filesystems"] = filesystems_val
    project_path = pathlib.Path("myproject.yaml")
    with pytest.raises(CraftValidationError) as error:
        Project.from_yaml_data(yaml_loaded, project_path)

    assert error.value.args[0] == "\n".join(
        ("Bad myproject.yaml content:", *error_lines)
    )
