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
conditions and small helpers like ``_part_num``, ``_generate_grub_cfg``,
``_read_grub_defaults``, ``_find_kernels`` and ``_dump_signed_efi_binaries``
against plain directory trees.

The full end-to-end flow (real disk images, FUSE mounts, chroot) is covered
by ``tests/integration/pack/test_grubutil.py``.
"""

import shutil
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import pytest
from craft_parts.filesystem_mounts import FilesystemMount
from craft_platforms import DebianArchitecture
from imagecraft import errors
from imagecraft.models.volume import (
    GPTStructureItem,
    GPTStructureList,
    GPTVolume,
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
            DebianArchitecture.S390X,
            "Cannot install GRUB on this architecture",
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
        (
            MBRVolume.unmarshal(
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
            ),
            DebianArchitecture.ARM64,
            "Cannot install GRUB on this architecture",
        ),
    ],
)
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_skip_conditions(mocker, new_dir, volume, arch, emitter, message):
    """setup_grub emits a permanent progress message and returns without acting."""
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
        ]
    )
    image = Image(volume=volume, disk_path=disk_path)
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    setup_efi = mocker.patch("imagecraft.pack.grubutil._setup_grub_efi")
    setup_bios = mocker.patch("imagecraft.pack.grubutil._setup_grub_bios_chroot")

    grubutil.setup_grub(
        image=image, workdir=workdir, arch=arch, filesystem_mount=filesystem_mount
    )

    setup_efi.assert_not_called()
    setup_bios.assert_not_called()
    emitter.assert_progress(message, permanent=True)


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
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
        ]
    )
    image = Image(volume=volume, disk_path=disk_path)
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    setup_efi = mocker.patch("imagecraft.pack.grubutil._setup_grub_efi")

    grubutil.setup_grub(
        image=image,
        workdir=workdir,
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    setup_efi.assert_called_once_with(image, "x86_64-efi", filesystem_mount)


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
    filesystem_mount = FilesystemMount.unmarshal(
        [{"mount": "/", "device": "(volume/pc/rootfs)"}]
    )
    image = Image(volume=volume, disk_path=disk_path)
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    setup_bios = mocker.patch("imagecraft.pack.grubutil._setup_grub_bios_chroot")

    grubutil.setup_grub(
        image=image, workdir=workdir, arch=arch, filesystem_mount=filesystem_mount
    )

    # BIOS/MBR still installs GRUB through a chroot until it is converted
    # to direct disk image manipulation.
    setup_bios.assert_called_once_with(image, workdir, "i386-pc", filesystem_mount)


@pytest.mark.usefixtures("new_dir")
def test_setup_grub_catches_image_error(mocker, new_dir, emitter):
    """A raised ImageError (e.g. missing mount) is turned into a progress message."""

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
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
        ]
    )
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
        filesystem_mount=filesystem_mount,
    )

    emitter.assert_progress("Cannot install GRUB on this rootfs: boom", permanent=True)


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


def test_partition_name_from_device():
    assert grubutil._partition_name_from_device("(volume/pc/rootfs)") == "rootfs"


# ── Small pure-logic helpers ─────────────────────────────────────────────


@pytest.mark.parametrize(
    (
        "kernels",
        "root_uuid",
        "boot_uuid",
        "boot_prefix",
        "defaults",
        "expected",
        "unexpected",
    ),
    [
        pytest.param(
            [],
            "some-uuid",
            "some-uuid",
            "/boot",
            grubutil.GrubDefaults(),
            ["search --no-floppy --fs-uuid --set=root some-uuid", "set timeout=5"],
            ["menuentry"],
            id="no-kernels",
        ),
        pytest.param(
            [("vmlinuz-1", "initrd.img-1")],
            "uuid-x",
            "uuid-x",
            "/boot",
            grubutil.GrubDefaults(),
            [
                'menuentry "vmlinuz-1"',
                "linux /boot/vmlinuz-1 root=UUID=uuid-x ro",
                "initrd /boot/initrd.img-1",
            ],
            [],
            id="kernel-and-initrd",
        ),
        pytest.param(
            [("vmlinuz-1", "")],
            "uuid-x",
            "uuid-boot",
            "",
            grubutil.GrubDefaults(),
            [
                "search --no-floppy --fs-uuid --set=root uuid-boot",
                "linux /vmlinuz-1 root=UUID=uuid-x ro",
            ],
            ["initrd"],
            id="separate-boot-partition",
        ),
        pytest.param(
            [("vmlinuz-1", "")],
            "uuid-x",
            "uuid-x",
            "/boot",
            grubutil.GrubDefaults(cmdline="console=ttyS0 quiet"),
            ["linux /boot/vmlinuz-1 root=UUID=uuid-x ro console=ttyS0 quiet"],
            [],
            id="cmdline-override",
        ),
        pytest.param(
            [],
            "uuid-x",
            "uuid-x",
            "/boot",
            grubutil.GrubDefaults(timeout=0),
            ["set timeout=0"],
            [],
            id="timeout-override",
        ),
    ],
)
def test_generate_grub_cfg(
    kernels, root_uuid, boot_uuid, boot_prefix, defaults, expected, unexpected
):
    cfg = grubutil._generate_grub_cfg(
        kernels, root_uuid, boot_uuid, boot_prefix, defaults
    )
    for snippet in expected:
        assert snippet in cfg
    for snippet in unexpected:
        assert snippet not in cfg


@pytest.mark.parametrize("include_fw_setup", [True, False])
def test_generate_grub_cfg_fw_setup(include_fw_setup):
    cfg = grubutil._generate_grub_cfg(
        [], "some-uuid", "some-uuid", "/boot", include_fw_setup=include_fw_setup
    )
    snippets = [
        "menuentry 'UEFI Firmware Settings'",
        "fwsetup",
        'if [ "${grub_platform}" = "efi" ]; then',
    ]
    for snippet in snippets:
        if include_fw_setup:
            assert snippet in cfg
        else:
            assert snippet not in cfg


def _root_tree_with(tmp_path, content: str) -> Path:
    """Make a fake rootfs tree whose /etc/default/grub reads back as `content`."""
    rootfs = tmp_path / "rootfs"
    (rootfs / "etc/default").mkdir(parents=True)
    (rootfs / "etc/default/grub").write_text(content)
    return rootfs


def test_read_grub_defaults_missing_file(tmp_path):
    rootfs = tmp_path / "rootfs"
    rootfs.mkdir()
    assert grubutil._read_grub_defaults(rootfs) == grubutil.GrubDefaults()


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ('GRUB_CMDLINE_LINUX_DEFAULT="quiet splash"\n', "quiet splash"),
        ('GRUB_CMDLINE_LINUX="console=ttyS0"\n', "console=ttyS0"),
        (
            (
                'GRUB_CMDLINE_LINUX="console=ttyS0"\n'
                'GRUB_CMDLINE_LINUX_DEFAULT="quiet"\n'
            ),
            "console=ttyS0 quiet",
        ),
        ("GRUB_CMDLINE_LINUX='single'\n", "single"),
        ("GRUB_CMDLINE_LINUX=nomodeset\n", "nomodeset"),
        ('#GRUB_CMDLINE_LINUX="ignored"\n', ""),
        ('GRUB_CMDLINE_LINUX=""\n', ""),
        ("GRUB_TIMEOUT=5\n", ""),
        ('export GRUB_CMDLINE_LINUX="console=ttyS0"\n', "console=ttyS0"),
        ("export GRUB_CMDLINE_LINUX=nomodeset\n", "nomodeset"),
        (
            (
                'GRUB_CMDLINE_LINUX="console=ttyS0"\n'
                'GRUB_CMDLINE_LINUX="$GRUB_CMDLINE_LINUX quiet"\n'
            ),
            "console=ttyS0 quiet",
        ),
        (
            (
                'GRUB_CMDLINE_LINUX="console=ttyS0"\n'
                'GRUB_CMDLINE_LINUX_DEFAULT="${GRUB_CMDLINE_LINUX} splash"\n'
            ),
            "console=ttyS0 console=ttyS0 splash",
        ),
        ("GRUB_CMDLINE_LINUX='$GRUB_TIMEOUT'\n", "$GRUB_TIMEOUT"),
        ('GRUB_CMDLINE_LINUX="$UNSET_ELSEWHERE quiet"\n', "$UNSET_ELSEWHERE quiet"),
        ('GRUB_CMDLINE_LINUX="console=ttyS0 \\\n    quiet"\n', "console=ttyS0 quiet"),
        ("GRUB_CMDLINE_LINUX=nomodeset\\\n\n", "nomodeset"),
        ('GRUB_CMDLINE_LINUX="a"\nGRUB_CMDLINE_LINUX="b"\n', "b"),
    ],
)
def test_read_grub_defaults_cmdline(tmp_path, content, expected):
    rootfs = _root_tree_with(tmp_path, content)
    assert grubutil._read_grub_defaults(rootfs).cmdline == expected


def _root_tree_with_shim(
    tmp_path, files: dict[str, bytes], links: dict[str, str]
) -> Path:
    """Build a fake rootfs tree with regular files and (possibly dangling) links."""
    rootfs = tmp_path / "rootfs"
    for path, data in files.items():
        dest = rootfs / path.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    for link, target in links.items():
        dest = rootfs / link.lstrip("/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.symlink_to(target)
    return rootfs


def test_dump_signed_efi_binaries_follows_symlinked_shim(tmp_path):
    """Ubuntu ships /usr/lib/shim/shimx64.efi.signed as a symlink."""
    rootfs = _root_tree_with_shim(
        tmp_path,
        {
            "/usr/lib/shim/shimx64.efi.signed.real": b"shim binary",
            "/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed": b"grub binary",
        },
        {"/usr/lib/shim/shimx64.efi.signed": "shimx64.efi.signed.real"},
    )

    result = grubutil._dump_signed_efi_binaries(rootfs, "x86_64-efi", tmp_path / "out")

    assert result is not None
    assert result["shim"].read_bytes() == b"shim binary"
    assert result["grub"].read_bytes() == b"grub binary"


def test_dump_signed_efi_binaries_skips_dangling_shim_symlink(tmp_path):
    """A dangling link must not be deployed as an empty (unbootable) binary."""
    rootfs = _root_tree_with_shim(
        tmp_path,
        {"/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed": b"grub binary"},
        {"/usr/lib/shim/shimx64.efi.signed": "gone.efi"},
    )

    assert (
        grubutil._dump_signed_efi_binaries(rootfs, "x86_64-efi", tmp_path / "out")
        is None
    )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("GRUB_TIMEOUT=0\n", 0),
        ('GRUB_TIMEOUT="10"\n', 10),
        ("GRUB_TIMEOUT=-1\n", -1),
        ("GRUB_TIMEOUT=forever\n", 5),
        ("#GRUB_TIMEOUT=0\n", 5),
        ("", 5),
    ],
)
def test_read_grub_defaults_timeout(tmp_path, content, expected):
    rootfs = _root_tree_with(tmp_path, content)
    assert grubutil._read_grub_defaults(rootfs).timeout == expected


def test_find_kernels_orders_newest_first(tmp_path):
    """`set default=0` boots the first entry, which has to be the newest kernel."""
    boot_dir = tmp_path / "boot"
    boot_dir.mkdir()
    for name in (
        "vmlinuz-6.8.0-9-generic",
        "initrd.img-6.8.0-9-generic",
        "vmlinuz-6.8.0-100-generic",
        "initrd.img-6.8.0-100-generic",
        "vmlinuz-6.11.0-1-generic",
    ):
        (boot_dir / name).write_bytes(b"k")

    kernels = grubutil._find_kernels(tmp_path, "/boot")

    assert kernels == [
        ("vmlinuz-6.11.0-1-generic", ""),
        ("vmlinuz-6.8.0-100-generic", "initrd.img-6.8.0-100-generic"),
        ("vmlinuz-6.8.0-9-generic", "initrd.img-6.8.0-9-generic"),
    ]


@pytest.mark.parametrize(
    ("boot_uuid", "boot_prefix", "expected_prefix"),
    [
        ("abcd-uuid", "/boot", "set prefix=($root)'/boot/grub'"),
        ("boot-uuid", "", "set prefix=($root)'/grub'"),
    ],
)
def test_efi_stub_grub_cfg(boot_uuid, boot_prefix, expected_prefix):
    cfg = grubutil._efi_stub_grub_cfg(boot_uuid, boot_prefix)
    assert f"search.fs_uuid {boot_uuid} root" in cfg
    assert expected_prefix in cfg
    assert "configfile $prefix/grub.cfg" in cfg


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


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        ("x86_64-efi", "X64"),
        ("arm64-efi", "AA64"),
        ("arm-efi", "ARM"),
        ("riscv64-efi", "RISCV64"),
    ],
)
def test_uefi_arch_token(target, expected):
    assert grubutil._uefi_arch_token(target) == expected


def test_uefi_arch_token_unknown():
    with pytest.raises(errors.GRUBInstallError, match="ppc64el-efi"):
        grubutil._uefi_arch_token("ppc64el-efi")


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
