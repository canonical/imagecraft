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
from imagecraft.models import Role, Volume
from pydantic import ValidationError


def test_volume_valid():
    volume = Volume(
        schema="gpt",  # pyright: ignore[reportArgumentType]
        structure=[  # pyright: ignore[reportArgumentType]
            {
                "name": "efi",
                "role": "system-boot",
                "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                "filesystem": "vfat",
                "size": "6GiB",
                "filesystem-label": "",
            },
            {
                "name": "boot",
                "role": "system-boot",
                "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                "filesystem": "fat16",
                "size": "6G",
            },
            {
                "name": "rootfs",
                "role": "system-data",
                "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                "filesystem": "ext4",
                "size": "0",
                "filesystem-label": "writable",
            },
        ],
    )
    assert volume.volume_schema == "gpt"
    assert len(volume.structure) == 3
    assert volume.structure[0].size == 6442450944
    assert volume.structure[0].role == Role.SYSTEM_BOOT
    assert volume.structure[0].filesystem_label == "efi"
    assert volume.structure[1].size == 6000000000
    assert volume.structure[1].filesystem_label == "boot"
    assert volume.structure[2].role == Role.SYSTEM_DATA
    assert volume.structure[2].size == 0
    assert volume.structure[2].filesystem_label == "writable"


@pytest.mark.parametrize(
    ("error_value", "error_class", "volume"),
    [
        (
            "1 validation error for Volume\nschema",
            ValidationError,
            {
                "structure": [
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "0",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nschema",
            ValidationError,
            {
                "schema": "",
                "structure": [
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "0",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure.0.name\n  String should match pattern",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "0",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure.0.name\n  String should match pattern",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test-",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "0",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure\n  List should have at least 1 item after validation, not 0",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [],
            },
        ),
        (
            "1 validation error for Volume\nstructure.0.role\n  Input should be 'system-data' or 'system-boot'",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test",
                        "role": "invalid",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "0",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure\n  Value error, duplicate values in list",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "0",
                    },
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "0",
                    },
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure.0.type",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "invalid",
                        "filesystem": "ext4",
                        "size": "0",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure.0.filesystem",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "invalid",
                        "size": "0",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure.0.id\n  Input should be a valid UUID",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test",
                        "id": "invalid",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "0",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure.0.name\n  String should have at most 36 characters",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "toolongtoolongtoolongtoolongtoolongtoolongtoolongtoolongtoolongtoolong",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "0",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure.0.size\n  Field required",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure.0.size\n  could not parse value and unit from byte string",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "invalid",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure\n  Value error, Duplicate filesystem labels: ['label1']",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "filesystem-label": "label1",
                        "size": "0",
                    },
                    {
                        "name": "test2",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "filesystem-label": "label1",
                        "size": "0",
                    },
                ],
            },
        ),
        (
            "1 validation error for Volume\nstructure\n  Value error, Duplicate filesystem labels: ['test2']",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "filesystem-label": "test2",
                        "size": "0",
                    },
                    {
                        "name": "test2",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "0",
                    },
                ],
            },
        ),
    ],
)
def test_volume_invalid(
    error_value,
    error_class,
    volume,
):
    def load_volume(volume, raises):
        with pytest.raises(raises) as err:
            Volume(**volume)

        return str(err.value)

    assert error_value in load_volume(volume, error_class)
