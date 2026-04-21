# This file is part of imagecraft.
#
# Copyright 2025-2026 Canonical Ltd.
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

import re

import pytest
from imagecraft.models import Role, Volume
from imagecraft.models.volume import (
    GPTVolume,
    HybridVolume,
    MBRVolume,
    StructureList,
)
from pydantic import TypeAdapter, ValidationError


def test_volume_valid():
    volume_adapter = TypeAdapter(Volume)

    volume = volume_adapter.validate_python(
        {
            "schema": "gpt",
            "structure": [
                {
                    "name": "efi",
                    "role": "system-boot",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "vfat",
                    "size": "3G",
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
        }
    )
    assert volume.volume_schema == "gpt"
    assert len(volume.structure) == 3
    assert volume.structure[0].size == 3 * 1024**3
    assert volume.structure[0].role == Role.SYSTEM_BOOT
    assert volume.structure[0].filesystem_label == "efi"
    assert volume.structure[1].size == 6 * 1024**3
    assert volume.structure[1].filesystem_label == "boot"
    assert volume.structure[2].role == Role.SYSTEM_DATA
    assert volume.structure[2].size == 0
    assert volume.structure[2].filesystem_label == "writable"


@pytest.mark.parametrize(
    ("error_value", "error_class", "volume"),
    [
        (
            "1 validation error for Volume\n  Unable to extract tag",
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
        pytest.param(
            "1 validation error for Volume\n  Input tag",
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
            id="missing-schema",
        ),
        pytest.param(
            "1 validation error for Volume\ngpt.structure.0.name\n  String should match pattern",
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
            id="empty-name",
        ),
        (
            "1 validation error for Volume\ngpt.structure.0.name\n  String should match pattern",
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
            "1 validation error for Volume\ngpt.structure\n  List should have at least 1 item after validation, not 0",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [],
            },
        ),
        (
            "1 validation error for Volume\ngpt.structure.0.role\n  Input should be '",
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
        pytest.param(
            "1 validation error for Volume\ngpt.structure\n  Value error, Duplicate filesystem labels: ['test']",
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
            id="duplicate-values",
        ),
        (
            "1 validation error for Volume\ngpt.structure.0.type",
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
            "1 validation error for Volume\ngpt.structure.0.filesystem",
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
            "1 validation error for Volume\ngpt.structure.0.id\n  Input should be a valid UUID",
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
            "1 validation error for Volume\ngpt.structure.0.name\n  String should have at most 36 characters",
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
            "1 validation error for Volume\ngpt.structure.0.size\n  Field required",
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
            "1 validation error for Volume\ngpt.structure.0.size\n  Value error, size must be expressed in bytes, optionally with M or G unit.",
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
            "1 validation error for Volume\ngpt.structure.0.size\n  Value error, size must be expressed in bytes, optionally with M or G unit.",
            ValidationError,
            {
                "schema": "gpt",
                "structure": [
                    {
                        "name": "test",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "6GiB",
                    }
                ],
            },
        ),
        (
            "1 validation error for Volume\ngpt.structure\n  Value error, Duplicate filesystem labels: ['label1']",
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
            "1 validation error for Volume\ngpt.structure\n  Value error, Duplicate filesystem labels: ['test2']",
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
    volume_adapter = TypeAdapter(Volume, config={"title": "Volume"})
    with pytest.raises(error_class) as exc_info:
        volume_adapter.validate_python(volume)

    assert error_value in str(exc_info.value)


@pytest.mark.parametrize(
    "structures",
    [
        pytest.param(
            [
                {
                    "name": "one",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "0",
                },
                {
                    "name": "two",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "0",
                },
            ],
            id="no-partition-numbers",
        ),
        pytest.param(
            [
                {
                    "name": "one",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "0",
                    "partition-number": 1,
                },
                {
                    "name": "two",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "0",
                    "partition-number": 2,
                },
            ],
            id="all-partition-numbers",
        ),
    ],
)
def test_structure_list_success(structures: list[dict]):
    TypeAdapter(StructureList).validate_python(structures)


@pytest.mark.parametrize(
    ("structures", "error_message"),
    [
        pytest.param(
            [
                {
                    "name": "mary-kate",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "0",
                    "partition-number": 64,
                },
                {
                    "name": "ashley",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "0",
                    "partition-number": 64,
                },
            ],
            re.escape(
                "Value error, duplicate partition numbers (partition-number 64 shared by 'mary-kate' and 'ashley')"
            ),
            id="duplicate-partition-numbers",
        ),
        pytest.param(
            [
                {
                    "name": "william",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "0",
                    "partition-number": 1,
                },
                {
                    "name": "thomas",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "0",
                },
            ],
            re.escape(
                "Value error, all partition numbers must be explicitly declared to use non-sequential partition numbers in a volume. (Not numbered: 'thomas')"
            ),
            id="partially-declared-partition-numbers",
        ),
    ],
)
def test_structure_list_errors(structures: list[dict], error_message):
    with pytest.raises(ValidationError, match=error_message):
        TypeAdapter(StructureList).validate_python(structures)


# ---------------------------------------------------------------------------
# MBRVolume
# ---------------------------------------------------------------------------

_MBR_SEED = {
    "name": "ubuntu-seed",
    "role": "system-seed",
    "type": "0C",
    "filesystem": "vfat",
    "size": "1200M",
}
_MBR_DATA = {
    "name": "ubuntu-data",
    "role": "system-data",
    "type": "83",
    "filesystem": "ext4",
    "size": "1500M",
}


@pytest.mark.parametrize(
    ("structure_type", "structure"),
    [
        ("0C", _MBR_SEED),
        ("83", _MBR_DATA),
    ],
    ids=["fat32", "linux"],
)
def test_mbr_volume_valid(structure_type, structure):
    volume_adapter = TypeAdapter(Volume)
    volume = volume_adapter.validate_python({"schema": "mbr", "structure": [structure]})
    assert isinstance(volume, MBRVolume)
    assert volume.volume_schema == "mbr"
    assert volume.structure[0].structure_type == structure_type


def test_mbr_volume_invalid_type():
    volume_adapter = TypeAdapter(Volume)
    with pytest.raises(ValidationError, match=r"mbr\.structure\.0\.type"):
        volume_adapter.validate_python(
            {
                "schema": "mbr",
                "structure": [
                    {
                        "name": "rootfs",
                        "role": "system-data",
                        "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                        "filesystem": "ext4",
                        "size": "6G",
                    }
                ],
            }
        )


def test_mbr_volume_duplicate_filesystem_labels():
    volume_adapter = TypeAdapter(Volume)
    with pytest.raises(
        ValidationError,
        match=re.escape("Value error, Duplicate filesystem labels: ['ubuntu-data']"),
    ):
        volume_adapter.validate_python(
            {
                "schema": "mbr",
                "structure": [
                    {**_MBR_SEED, "filesystem-label": "ubuntu-data"},
                    _MBR_DATA,
                ],
            }
        )


# ---------------------------------------------------------------------------
# GPTVolume vs MBRVolume discriminated union
# ---------------------------------------------------------------------------


def test_volume_gpt_schema_produces_gpt_volume():
    volume = TypeAdapter(Volume).validate_python(
        {
            "schema": "gpt",
            "structure": [
                {
                    "name": "rootfs",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "6G",
                }
            ],
        }
    )
    assert isinstance(volume, GPTVolume)


def test_volume_mbr_schema_produces_mbr_volume():
    volume = TypeAdapter(Volume).validate_python(
        {"schema": "mbr", "structure": [_MBR_DATA]}
    )
    assert isinstance(volume, MBRVolume)


# ---------------------------------------------------------------------------
# content and min-size fields
# ---------------------------------------------------------------------------

_VALID_GPT_STRUCTURE = {
    "name": "rootfs",
    "role": "system-data",
    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
    "filesystem": "ext4",
    "size": "6G",
}
_VALID_MBR_STRUCTURE = _MBR_DATA


@pytest.mark.parametrize(
    ("schema", "base_structure"),
    [
        ("gpt", _VALID_GPT_STRUCTURE),
        ("mbr", _VALID_MBR_STRUCTURE),
    ],
)
def test_content_null_is_accepted(schema, base_structure):
    TypeAdapter(Volume).validate_python(
        {"schema": schema, "structure": [{**base_structure, "content": None}]}
    )


@pytest.mark.parametrize(
    ("schema", "base_structure"),
    [
        ("gpt", _VALID_GPT_STRUCTURE),
        ("mbr", _VALID_MBR_STRUCTURE),
    ],
)
def test_content_non_null_is_rejected(schema, base_structure):
    with pytest.raises(
        ValidationError,
        match="Imagecraft does not support the 'content' key in volume structures.",
    ):
        TypeAdapter(Volume).validate_python(
            {
                "schema": schema,
                "structure": [
                    {**base_structure, "content": [{"source": "boot/", "target": "/"}]}
                ],
            }
        )


@pytest.mark.parametrize(
    ("schema", "base_structure"),
    [
        ("gpt", _VALID_GPT_STRUCTURE),
        ("mbr", _VALID_MBR_STRUCTURE),
    ],
)
def test_min_size_null_is_accepted(schema, base_structure):
    TypeAdapter(Volume).validate_python(
        {"schema": schema, "structure": [{**base_structure, "min-size": None}]}
    )


@pytest.mark.parametrize(
    ("schema", "base_structure"),
    [
        ("gpt", _VALID_GPT_STRUCTURE),
        ("mbr", _VALID_MBR_STRUCTURE),
    ],
)
def test_min_size_non_null_is_rejected(schema, base_structure):
    with pytest.raises(
        ValidationError,
        match="Imagecraft does not support the 'min-size' key in volume structures.",
    ):
        TypeAdapter(Volume).validate_python(
            {"schema": schema, "structure": [{**base_structure, "min-size": "16M"}]}
        )


# ---------------------------------------------------------------------------
# HybridVolume
# ---------------------------------------------------------------------------

_HYBRID_SEED = {
    "name": "ubuntu-seed",
    "role": "system-seed",
    "type": "0C,C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
    "filesystem": "vfat",
    "size": "1200M",
}
_HYBRID_DATA = {
    "name": "ubuntu-data",
    "role": "system-data",
    "type": "83,0FC63DAF-8483-4772-8E79-3D69D8477DE4",
    "filesystem": "ext4",
    "size": "1500M",
}


@pytest.mark.parametrize(
    ("structure_type", "structure"),
    [
        ("0C,C12A7328-F81F-11D2-BA4B-00A0C93EC93B", _HYBRID_SEED),
        ("83,0FC63DAF-8483-4772-8E79-3D69D8477DE4", _HYBRID_DATA),
    ],
    ids=["fat32-efi", "linux-linux-data"],
)
def test_hybrid_volume_valid(structure_type, structure):
    volume = TypeAdapter(Volume).validate_python(
        {"schema": "mbr,gpt", "structure": [structure]}
    )
    assert isinstance(volume, HybridVolume)
    assert volume.volume_schema == "mbr,gpt"
    assert volume.structure[0].structure_type == structure_type


def test_hybrid_volume_schema_produces_hybrid_volume():
    volume = TypeAdapter(Volume).validate_python(
        {"schema": "mbr,gpt", "structure": [_HYBRID_DATA]}
    )
    assert isinstance(volume, HybridVolume)


@pytest.mark.parametrize(
    "bad_type",
    [
        pytest.param("0C", id="mbr-only"),
        pytest.param("0FC63DAF-8483-4772-8E79-3D69D8477DE4", id="gpt-only"),
        pytest.param(
            "FF,0FC63DAF-8483-4772-8E79-3D69D8477DE4", id="invalid-mbr-component"
        ),
        pytest.param("0C,NOTAGUUID", id="invalid-gpt-component"),
    ],
)
def test_hybrid_volume_invalid_type(bad_type):
    with pytest.raises(ValidationError, match="String should match pattern"):
        TypeAdapter(Volume).validate_python(
            {
                "schema": "mbr,gpt",
                "structure": [{**_HYBRID_DATA, "type": bad_type}],
            }
        )


def test_hybrid_volume_duplicate_filesystem_labels():
    with pytest.raises(
        ValidationError,
        match=re.escape("Value error, Duplicate filesystem labels: ['ubuntu-data']"),
    ):
        TypeAdapter(Volume).validate_python(
            {
                "schema": "mbr,gpt",
                "structure": [
                    {**_HYBRID_SEED, "filesystem-label": "ubuntu-data"},
                    _HYBRID_DATA,
                ],
            }
        )
