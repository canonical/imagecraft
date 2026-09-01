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

"""Tests for imagecraft.pack.grubutil.

This module covers the pure-logic parts of ``setup_grub``: skip/dispatch
conditions and small helpers like ``_part_num`` and ``_dump_signed_efi_binaries``
against plain directory trees.

The full end-to-end flow (real disk images, FUSE mounts, chroot) is covered
by ``tests/integration/pack/test_grubutil.py``.
"""

import shutil
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from craft_platforms import DebianArchitecture
from imagecraft import errors
from imagecraft.models.volume import (
    GPTStructureItem,
    GPTStructureList,
    GPTVolume,
    HybridStructureItem,
    MBRStructureItem,
    MBRStructureList,
    MBRVolume,
)
from imagecraft.pack import grubutil
from imagecraft.pack.image import Image

# Real tools this module's implementation shells out to. If any of these is
# missing, the tests below fail (rather than silently skip) with a message
# pointing at `make setup`, since these are declared dependencies of the
# project (see snap/snapcraft.yaml and Makefile's APT_PACKAGES).
_REQUIRED_TOOLS = (
    "sfdisk",
    "mke2fs",
    "mkfs.vfat",
    "dd",
)


@pytest.fixture(autouse=True, scope="session")
def _require_grub_tools():
    """Fail loudly if a real tool used by grubutil/imgfs is missing.

    These aren't optional test-only dependencies: they're the actual tools
    imagecraft's GRUB installation code shells out to, so a developer
    machine missing them needs `make setup` regardless of these tests.
    """
    missing = [tool for tool in _REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        pytest.fail(
            "Missing required tool(s) for grubutil tests: "
            f"{', '.join(missing)}. Run `make setup` to install them.",
            pytrace=False,
        )


# ── setup_grub: skip conditions and dispatch (mocked, no real tools) ──────


@pytest.mark.parametrize(
    ("volume", "arch", "message"),
    [
        (
            GPTVolume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "512M",
                            "filesystem-label": "writable",
                        },
                    ],
                }
            ),
            DebianArchitecture.AMD64,
            "Skipping GRUB installation because no boot partition was found",
        ),
        (
            GPTVolume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "64M",
                            "filesystem-label": "",
                        },
                    ],
                }
            ),
            DebianArchitecture.AMD64,
            "Skipping GRUB installation because no data partition was found",
        ),
        (
            MBRVolume.unmarshal(
                {
                    "schema": "mbr",
                    "structure": [
                        {
                            "name": "boot",
                            "role": "system-boot",
                            "type": "83",
                            "filesystem": "ext4",
                            "size": "512M",
                        },
                    ],
                }
            ),
            DebianArchitecture.AMD64,
            "Skipping GRUB installation because no data partition was found",
        ),
    ],
)
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_skip_conditions(mocker, new_dir, volume, arch, emitter, message):
    """setup_grub emits a permanent progress message and returns without acting."""
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(volume=volume, disk_path=disk_path)
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    setup_efi = mocker.patch("imagecraft.pack.grubutil._setup_grub_efi")
    setup_bios = mocker.patch("imagecraft.pack.grubutil._setup_grub_bios_chroot")

    grubutil.setup_grub(image=image, workdir=workdir, arch=arch)

    setup_efi.assert_not_called()
    setup_bios.assert_not_called()
    emitter.assert_progress(message)


@pytest.mark.usefixtures("new_dir")
def test_setup_grub_dispatches_to_efi(mocker, new_dir):
    volume = GPTVolume.unmarshal(
        {
            "schema": "gpt",
            "structure": [
                {
                    "name": "efi",
                    "role": "system-boot",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "vfat",
                    "size": "64M",
                    "filesystem-label": "",
                },
                {
                    "name": "rootfs",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "512M",
                    "filesystem-label": "writable",
                },
            ],
        }
    )
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(volume=volume, disk_path=disk_path)
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    setup_efi = mocker.patch("imagecraft.pack.grubutil._setup_grub_efi")

    grubutil.setup_grub(
        image=image,
        workdir=workdir,
        arch=DebianArchitecture.AMD64,
    )

    setup_efi.assert_called_once_with(image, "x86_64-efi")


@pytest.mark.parametrize("arch", [DebianArchitecture.AMD64, DebianArchitecture.I386])
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_dispatches_to_bios(mocker, new_dir, arch):
    volume = MBRVolume.unmarshal(
        {
            "schema": "mbr",
            "structure": [
                {
                    "name": "rootfs",
                    "role": "system-data",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "512M",
                },
            ],
        }
    )
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(volume=volume, disk_path=disk_path)
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    setup_bios = mocker.patch("imagecraft.pack.grubutil._setup_grub_bios_chroot")

    grubutil.setup_grub(image=image, workdir=workdir, arch=arch)

    # BIOS/MBR still installs GRUB through a chroot until it is converted
    # to direct disk image manipulation.
    setup_bios.assert_called_once_with(image, workdir, "i386-pc")


def test_setup_grub_skips_efi_error(mocker, new_dir, emitter):
    """An EFI setup error emits a permanent skip message."""

    volume = GPTVolume.unmarshal(
        {
            "schema": "gpt",
            "structure": [
                {
                    "name": "efi",
                    "role": "system-boot",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "vfat",
                    "size": "64M",
                    "filesystem-label": "",
                },
                {
                    "name": "rootfs",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "512M",
                    "filesystem-label": "writable",
                },
            ],
        }
    )
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(volume=volume, disk_path=disk_path)
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    mocker.patch(
        "imagecraft.pack.grubutil._setup_grub_efi",
        side_effect=errors.ImageError(message="boom"),
    )

    grubutil.setup_grub(
        image=image,
        workdir=workdir,
        arch=DebianArchitecture.AMD64,
    )

    emitter.assert_progress("Cannot install GRUB on this rootfs: boom", permanent=True)


@pytest.mark.usefixtures("new_dir")
def test_setup_grub_skips_unsupported_bios_architecture(mocker, new_dir, emitter):
    volume = MBRVolume.unmarshal(
        {
            "schema": "mbr",
            "structure": [
                {
                    "name": "rootfs",
                    "role": "system-data",
                    "type": "83",
                    "filesystem": "ext4",
                    "size": "512M",
                },
            ],
        }
    )
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(volume=volume, disk_path=disk_path)
    setup_bios = mocker.patch("imagecraft.pack.grubutil._setup_grub_bios_chroot")

    grubutil.setup_grub(
        image=image,
        workdir=Path(new_dir, "workdir"),
        arch=DebianArchitecture.ARM64,
    )

    setup_bios.assert_not_called()
    emitter.assert_progress("Cannot install GRUB on this architecture", permanent=True)


# ── _part_num ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "structure_spec", "expected"),
    [
        pytest.param(
            "rootfs",
            [
                {"name": "efi", "partition_number": None},
                {"name": "rootfs", "partition_number": None},
            ],
            2,
            id="gpt-position-based",
        ),
        pytest.param(
            "rootfs",
            [
                {"name": "efi", "partition_number": None},
                {"name": "rootfs", "partition_number": 5},
            ],
            5,
            id="gpt-explicit-number",
        ),
        pytest.param(
            "missing",
            [{"name": "efi", "partition_number": None}],
            None,
            id="not-found",
        ),
    ],
)
def test_part_num_gpt(name, structure_spec, expected):
    items = []
    for spec in structure_spec:
        item = MagicMock(spec=GPTStructureItem)
        item.name = spec["name"]
        item.partition_number = spec["partition_number"]
        items.append(item)
    structure = cast(GPTStructureList, items)

    assert grubutil._part_num(name, structure) == expected


@pytest.mark.parametrize(
    ("names", "expected_part_nums"),
    [
        pytest.param(
            ["boot", "data", "rootfs"],
            {"boot": 1, "data": 2, "rootfs": 3},
            id="plain-primary",
        ),
        pytest.param(
            ["boot", "p2", "p3", "logical1", "logical2"],
            {"boot": 1, "p2": 2, "p3": 3, "logical1": 5, "logical2": 6},
            id="extended-container-skips-slot-4",
        ),
    ],
)
def test_part_num_mbr(names, expected_part_nums):
    items = []
    for name in names:
        item = MagicMock(spec=MBRStructureItem, partition_number=None)
        item.name = name
        items.append(item)
    structure = cast(MBRStructureList, items)
    for name, expected in expected_part_nums.items():
        assert grubutil._part_num(name, structure) == expected


# ── Target & name discovery ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("installed_dirs", "build_for", "expected"),
    [
        pytest.param(["x86_64-efi"], "x86_64-efi", "x86_64-efi", id="single-match"),
        pytest.param(
            ["arm64-efi"],
            "x86_64-efi",
            "arm64-efi",
            id="single-foreign-target-wins",
        ),
        pytest.param(
            ["x86_64-efi", "arm64-efi"],
            "x86_64-efi",
            "x86_64-efi",
            id="multi-build-for-tiebreak",
        ),
    ],
)
def test_discover_grub_target(tmp_path, installed_dirs, build_for, expected):
    rootfs = tmp_path / "rootfs"
    for d in installed_dirs:
        (rootfs / "usr/lib/grub" / d).mkdir(parents=True)

    assert grubutil._discover_grub_target(rootfs, build_for) == expected


@pytest.mark.parametrize(
    ("installed_dirs", "build_for", "match"),
    [
        pytest.param(
            [],
            "x86_64-efi",
            "GRUB modules for x86_64-efi are not installed",
            id="none-installed",
        ),
        pytest.param(
            ["x86_64-efi", "arm64-efi"],
            "riscv64-efi",
            "Multiple GRUB EFI module sets present.*none matches",
            id="multi-no-match",
        ),
    ],
)
def test_discover_grub_target_errors(tmp_path, installed_dirs, build_for, match):
    rootfs = tmp_path / "rootfs"
    for d in installed_dirs:
        (rootfs / "usr/lib/grub" / d).mkdir(parents=True)

    with pytest.raises(errors.ImageError, match=match):
        grubutil._discover_grub_target(rootfs, build_for)


def test_discover_grub_target_ignores_signed_dirs(tmp_path):
    """The ``*-efi-signed`` staging dirs are not module dirs."""
    rootfs = tmp_path / "rootfs"
    (rootfs / "usr/lib/grub/x86_64-efi").mkdir(parents=True)
    (rootfs / "usr/lib/grub/x86_64-efi-signed").mkdir(parents=True)

    assert grubutil._discover_grub_target(rootfs, "x86_64-efi") == "x86_64-efi"


def test_is_efi_partition_recognizes_hybrid_gpt_component():
    item = HybridStructureItem.unmarshal(
        {
            "name": "efi",
            "role": "system-boot",
            "type": "0C,C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
            "filesystem": "vfat",
            "size": "64M",
        }
    )

    assert grubutil._is_efi_partition(item)


@pytest.mark.parametrize(
    ("signed_name", "expected"),
    [
        ("shimx64.efi.signed.latest", "shimx64.efi"),
        ("shimx64.efi.signed", "shimx64.efi"),
        ("shimx64.efi.dualsigned", "shimx64.efi"),
        ("shimaa64.efi.signed.latest", "shimaa64.efi"),
        ("mmx64.efi", "mmx64.efi"),  # already unsigned — returned as-is
    ],
)
def test_unsigned_shim_name(signed_name, expected):
    assert grubutil._unsigned_shim_name(signed_name) == expected


def test_resolve_core_modules_closure(tmp_path):
    """moddep.lst drives the transitive closure and the result is deterministic."""
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir(parents=True)
    (modules_dir / "moddep.lst").write_text(
        "boot: video\n"
        "linux: boot relocator mmap\n"
        "search_fs_uuid:\n"
        "gfxterm: video font\n"
    )

    modules = grubutil._resolve_core_modules(modules_dir)

    assert modules == sorted(modules)
    assert set(modules) == {
        *grubutil._EFI_CORE_MODULES,
        # Resolved from moddep.lst:
        "video",
        "relocator",
        "mmap",
    }


def test_resolve_core_modules_without_moddep(tmp_path):
    """Missing moddep.lst (hand-rolled tree) falls back to the seed modules."""
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir(parents=True)

    assert grubutil._resolve_core_modules(modules_dir) == sorted(
        grubutil._EFI_CORE_MODULES
    )


def test_resolve_core_modules_includes_efi_firmware_setup_when_available(tmp_path):
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir(parents=True)
    (modules_dir / "efifwsetup.mod").touch()

    assert "efifwsetup" in grubutil._resolve_core_modules(modules_dir)
