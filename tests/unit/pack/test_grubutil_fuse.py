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

"""Tests for GRUB util with FUSE mount support."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Any

import pytest

from imagecraft.models.volume import (
    GPTStructureItem,
    HybridStructureItem,
    MBRStructureItem,
    Role,
    PartitionSchema,
    StructureItem,
)
from imagecraft.pack.grubutil import (
    setup_grub,
    _partition_by_name,
    SECTOR_SIZE,
    _partition_role_is_fat,
)
from imagecraft.pack.image import Image
from craft_cli import emit
from craft_platforms import DebianArchitecture
from craft_parts.filesystem_mounts import FilesystemMount


@pytest.fixture
def volume():
    """Create a test GPT volume structure."""
    return {
        "schema": "gpt",
        "structure": [
            {
                "name": "efi",
                "role": "system-boot",
                "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                "filesystem": "vfat",
                "size": "3G",
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


def test_sector_size_constant():
    """Test that SECTOR_SIZE constant is defined correctly."""
    assert SECTOR_SIZE == 512


def test_partition_role_is_fat():
    """Test partition role detection for FAT filesystems."""
    assert _partition_role_is_fat("system-boot") is True
    assert _partition_role_is_fat("system-seed") is True
    assert _partition_role_is_fat("system-data") is False


@pytest.mark.parametrize(
    ("structure_spec", "device_name", "expected"),
    [
        (
            [
                {"name": "efi", "role": "system-boot"},
                {"name": "rootfs", "role": "system-data"},
            ],
            "(volume/pc/efi)",
            "efi",
        ),
        (
            [
                {"name": "rootfs", "role": "system-data"},
            ],
            "(volume/pc/rootfs)",
            "rootfs",
        ),
        (
            [
                {"name": "efi", "role": "system-boot"},
            ],
            "(volume/pc/nonexistent)",
            None,
        ),
    ],
)
def test_partition_by_name(mocker, structure_spec, device_name, expected):
    """Test partition name extraction by device string."""
    structure = []
    for spec in structure_spec:
        item = MagicMock()
        item.name = spec["name"]
        item.role = Role(spec["role"])
        structure.append(item)

    result = _partition_by_name(structure, device_name)
    # Debug output
    if result is None:
        print(f"DEBUG: _partition_by_name returned None for device {device_name}")
    else:
        print(f"DEBUG: Found partition: {result.name}")
    assert result is expected or (result is not None and result.name == expected), (
        f"Expected {expected}, got {result}"
    )


def test_grub_probe_stub_exists():
    """Test that grub-probe stub script exists and is executable."""
    stub_path = Path("/project/imagecraft/pack/grub-probe-stub.sh")
    assert stub_path.exists(), f"grub-probe stub not found at {stub_path}"
    assert stub_path.stat().st_mode & 0o111, "grub-probe stub is not executable"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["--target=fs_uuid"], "1234-5678-90AB-CDEF"),
        (["--target=device"], "/dev/sda2"),
        (["--target=disk"], "/dev/sda"),
        (["--target=drive"], "hd0"),
        (["--target=fs"], "ext2"),
        (["--target=fs_label"], "writable"),
        (["--target=partmap"], "gpt"),
        (["--target=abstraction"], "lvm"),
    ],
)
def test_grub_probe_stub(mocker, args, expected):
    """Test grub-probe stub returns correct values for various targets."""

    def mock_run(*cmd, **kwargs):
        """Mock run function that executes the stub."""
        result = subprocess.CompletedProcess(
            cmd, returncode=0, stdout=expected, stderr=""
        )
        result.stdout = expected.encode() if isinstance(expected, str) else expected
        return result

    with patch("imagecraft.subprocesses.run", side_effect=mock_run):
        result = subprocess.run(
            ["/project/imagecraft/pack/grub-probe-stub.sh"] + args,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == expected


@pytest.mark.parametrize(
    ("args", "expected_error"),
    [
        (["--target=unknown"], 1),
    ],
)
def test_grub_probe_stub_error(mocker, args, expected_error):
    """Test grub-probe stub returns error for unknown targets."""

    def mock_run(*cmd, **kwargs):
        """Mock run function that executes the stub."""
        return subprocess.CompletedProcess(
            cmd,
            returncode=expected_error,
            stdout="",
            stderr="unknown",
        )

    with patch("imagecraft.subprocesses.run", side_effect=mock_run):
        result = subprocess.run(
            ["/project/imagecraft/pack/grub-probe-stub.sh"] + args,
            capture_output=True,
            text=True,
        )
        assert result.returncode == expected_error
        assert result.stderr.strip() == "unknown"


def test_imports():
    """Test that all necessary imports are available."""
    from imagecraft.pack.grubutil import (
        ExtFuseMount,
        FatFuseMount,
        Any,
    )

    assert ExtFuseMount is not None
    assert FatFuseMount is not None
    assert Any is not None
