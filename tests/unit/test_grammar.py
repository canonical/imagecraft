# This file is part of imagecraft.
#
# Copyright 2025 Canonical Ltd.
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

import textwrap

import pytest
import yaml
from craft_application.errors import CraftValidationError
from imagecraft.grammar import process_filesystems, process_volumes


@pytest.mark.parametrize(
    ("volumes_yaml", "arch", "target_arch", "platform", "expected"),
    [
        pytest.param(
            textwrap.dedent(
                """
                pc:
                  schema: gpt
                  structure:
                    - name: rootfs
                      type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                      filesystem: ext4
                      filesystem-label: writable
                      role: system-data
                      size: 6G
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            {
                "pc": {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "rootfs",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "filesystem-label": "writable",
                            "role": "system-data",
                            "size": "6G",
                        }
                    ],
                },
            },
            id="no grammar",
        ),
        pytest.param(
            textwrap.dedent(
                """
                pc:
                  schema: gpt
                  structure:
                    - to arm64:
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
            ),
            "amd64",
            "arm64",
            "amd64-generic",
            {
                "pc": {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                            "filesystem": "vfat",
                            "role": "system-boot",
                            "size": "500 M",
                        },
                        {
                            "name": "rootfs",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "filesystem-label": "writable",
                            "role": "system-data",
                            "size": "6G",
                        },
                    ],
                },
            },
            id="to grammar",
        ),
        pytest.param(
            textwrap.dedent(
                """
                pc:
                  schema: gpt
                  structure:
                    - for amd64-generic:
                      - name: efi
                        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
                        filesystem: vfat
                        role: system-boot
                        size: 256M
                    - for raspi-arm64:
                      - name: boot
                        role: system-boot
                        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                        filesystem: vfat
                        size: 512M
                    - name: rootfs
                      type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                      filesystem: ext4
                      filesystem-label: writable
                      role: system-data
                      size: 6G
                """
            ),
            "amd64",
            "arm64",
            "amd64-generic",
            {
                "pc": {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                            "filesystem": "vfat",
                            "role": "system-boot",
                            "size": "256M",
                        },
                        {
                            "name": "rootfs",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "filesystem-label": "writable",
                            "role": "system-data",
                            "size": "6G",
                        },
                    ],
                },
            },
            id="for grammar",
        ),
    ],
)
def test_process_volumes(volumes_yaml, arch, target_arch, platform, expected):
    yaml_loaded = yaml.safe_load(volumes_yaml)
    assert (
        process_volumes(
            volumes_yaml_data=yaml_loaded,
            arch=arch,
            target_arch=target_arch,
            platform_ids={platform},
        )
        == expected
    )


@pytest.mark.parametrize(
    ("volumes_yaml", "arch", "target_arch", "platform"),
    [
        pytest.param(
            textwrap.dedent(
                """
                pc:
                  schema: gpt
                  structure:
                    - to arm64:
                        - name: rootfs
                          type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                          filesystem: ext4
                          filesystem-label: writable
                          role: system-data
                          size: 6G
                    - else:
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            id="incomplete else statement",
        ),
        pytest.param(
            textwrap.dedent(
                """
                pc:
                  schema: gpt
                  structure:
                    - for amd64-generic:
                      - name: efi
                        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
                        filesystem: vfat
                        role: system-boot
                        size: 256M
                    - to amd64:
                      - name: boot
                        role: system-boot
                        type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                        filesystem: vfat
                        size: 512M
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            id="for and to variants",
        ),
    ],
)
def test_process_volumes_fail(volumes_yaml, arch, target_arch, platform):
    yaml_loaded = yaml.safe_load(volumes_yaml)
    with pytest.raises(CraftValidationError):
        process_volumes(
            volumes_yaml_data=yaml_loaded,
            arch=arch,
            target_arch=target_arch,
            platform_ids={platform},
        )


@pytest.mark.parametrize(
    ("filesystems_yaml", "arch", "target_arch", "platform", "expected"),
    [
        pytest.param(
            textwrap.dedent(
                """
                filesystems:
                  default:
                  - mount: /
                    device: (volume/pc/rootfs)
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            {"default": [{"mount": "/", "device": "(volume/pc/rootfs)"}]},
            id="no grammar",
        ),
        pytest.param(
            textwrap.dedent(
                """
                filesystems:
                  default:
                  - to arm64:
                    - mount: /
                      device: (foo)
                  - to amd64:
                    - mount: /
                      device: (bar)
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            {"default": [{"mount": "/", "device": "(bar)"}]},
            id="to grammar",
        ),
        pytest.param(
            textwrap.dedent(
                """
                filesystems:
                  default:
                  - mount: /
                    device: foo
                  - to amd64:
                    - mount: /bar
                      device: baz
                  - mount: /qux
                    device: bla
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            {
                "default": [
                    {"mount": "/", "device": "foo"},
                    {"mount": "/bar", "device": "baz"},
                    {"mount": "/qux", "device": "bla"},
                ]
            },
            id="to grammar in the middle of a list",
        ),
        pytest.param(
            textwrap.dedent(
                """
                filesystems:
                  default:
                  - for raspi-arm64:
                    - mount: /
                      device: (foo)
                  - for amd64-generic:
                    - mount: /
                      device: (bar)
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            {"default": [{"mount": "/", "device": "(bar)"}]},
            id="for grammar",
        ),
        pytest.param(
            textwrap.dedent(
                """
                filesystems:
                  default:
                  - mount: /
                    device: foo
                  - for amd64-generic:
                    - mount: /bar
                      device: baz
                  - mount: /qux
                    device: bla
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            {
                "default": [
                    {"mount": "/", "device": "foo"},
                    {"mount": "/bar", "device": "baz"},
                    {"mount": "/qux", "device": "bla"},
                ]
            },
            id="for grammar in the middle of a list",
        ),
        pytest.param(
            textwrap.dedent(
                """
                filesystems:
                  default: False
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            {"default": False},
            id="ignore invalid filesystem",
        ),
    ],
)
def test_process_filesystems(filesystems_yaml, arch, target_arch, platform, expected):
    yaml_loaded = yaml.safe_load(filesystems_yaml)
    assert (
        process_filesystems(
            filesystems_yaml_data=yaml_loaded["filesystems"],
            arch=arch,
            target_arch=target_arch,
            platform_ids={platform},
        )
        == expected
    )


@pytest.mark.parametrize(
    ("filesystems_yaml", "arch", "target_arch", "platform"),
    [
        pytest.param(
            textwrap.dedent(
                """
                filesystems:
                  default:
                  - to arm64:
                    - mount: /
                      device: (foo)
                  - else:
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            id="incomplete else statement",
        ),
        pytest.param(
            textwrap.dedent(
                """
                filesystems:
                  default:
                  - for raspi-arm64:
                    - mount: /
                      device: (foo)
                  - to amd64:
                    - mount: /
                      device: (bar)
                """
            ),
            "amd64",
            "amd64",
            "amd64-generic",
            id="for and to variants",
        ),
    ],
)
def test_process_filesystems_fail(filesystems_yaml, arch, target_arch, platform):
    yaml_loaded = yaml.safe_load(filesystems_yaml)
    with pytest.raises(CraftValidationError):
        process_filesystems(
            filesystems_yaml_data=yaml_loaded["filesystems"],
            arch=arch,
            target_arch=target_arch,
            platform_ids={platform},
        )
