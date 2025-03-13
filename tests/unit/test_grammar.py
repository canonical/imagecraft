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

import pytest
import yaml
from craft_application.errors import CraftValidationError
from imagecraft.grammar import process_volumes


@pytest.mark.parametrize(
    ("volumes_yaml", "arch", "target_arch", "expected"),
    [
        (
            """
pc:
  schema: gpt
  structure:
    - name: rootfs
      type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
      filesystem: ext4
      filesystem-label: writable
      role: system-data
      size: 6GiB
    """,
            "amd64",
            "amd64",
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
                            "size": "6GiB",
                        }
                    ],
                },
            },
        ),
        (
            """
pc:
  schema: gpt
  structure:
    - to arm64:
      - name: efi
        role: system-boot
        type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
        filesystem: vfat
        size: 500 MiB
    - name: rootfs
      type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
      filesystem: ext4
      filesystem-label: writable
      role: system-data
      size: 6GiB
    """,
            "amd64",
            "arm64",
            {
                "pc": {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                            "filesystem": "vfat",
                            "role": "system-boot",
                            "size": "500 MiB",
                        },
                        {
                            "name": "rootfs",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "filesystem-label": "writable",
                            "role": "system-data",
                            "size": "6GiB",
                        },
                    ],
                },
            },
        ),
    ],
)
def test_process_volumes(volumes_yaml, arch, target_arch, expected):
    yaml_loaded = yaml.safe_load(volumes_yaml)
    assert (
        process_volumes(
            volumes_yaml_data=yaml_loaded, arch=arch, target_arch=target_arch
        )
        == expected
    )


@pytest.mark.parametrize(
    ("volumes_yaml", "arch", "target_arch"),
    [
        (
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
          size: 6GiB
    - else:
    """,
            "amd64",
            "amd64",
        ),
    ],
)
def test_process_volumes_fail(volumes_yaml, arch, target_arch):
    yaml_loaded = yaml.safe_load(volumes_yaml)
    with pytest.raises(CraftValidationError):
        process_volumes(
            volumes_yaml_data=yaml_loaded, arch=arch, target_arch=target_arch
        )
