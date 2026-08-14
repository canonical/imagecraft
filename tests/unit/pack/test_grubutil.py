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

This module is tested at two levels:

- Pure-logic unit tests (mocked subprocesses) for ``setup_grub``'s
  skip/dispatch conditions and small helpers like ``_part_num``.
- Real, no-privilege end-to-end integration tests that build actual disk
  images with ``sfdisk``/``mke2fs``/``mkfs.vfat`` and drive the real
  ``grubutil`` code (``mtools``, ``debugfs``, ``grub-mkimage``) against them,
  then inspect the resulting image with ``mdir``/``debugfs`` to confirm the
  right files landed in the right places. No loop device, mount, chroot, or
  VM is used anywhere in these tests, matching the module's own design.
"""

import shutil
import subprocess
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
    PartitionSchema,
)
from imagecraft.pack import diskutil, gptutil, grubutil, imgfs, mbrutil
from imagecraft.pack.diskutil import DiskSize
from imagecraft.pack.image import Image

# Real tools this module's implementation shells out to. If any of these is
# missing, the integration tests below fail (rather than silently skip) with
# a message pointing at `make setup`, since these are declared dependencies
# of the project (see snap/snapcraft.yaml and Makefile's APT_PACKAGES).
_REQUIRED_TOOLS = (
    "sfdisk",
    "mke2fs",
    "mkfs.vfat",
    "debugfs",
    "blkid",
    "mcopy",
    "mmd",
    "mdir",
    "dd",
    "grub-mkimage",
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
    setup_bios = mocker.patch("imagecraft.pack.grubutil._setup_grub_bios")

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
    setup_bios = mocker.patch("imagecraft.pack.grubutil._setup_grub_bios")

    grubutil.setup_grub(
        image=image, workdir=workdir, arch=arch, filesystem_mount=filesystem_mount
    )

    setup_bios.assert_called_once_with(image, filesystem_mount)


@pytest.mark.usefixtures("new_dir")
def test_setup_grub_catches_image_error(mocker, new_dir, emitter):
    """A raised ImageError (e.g. missing mount) is turned into a progress message."""
    from imagecraft import errors  # noqa: PLC0415

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
    mocker.patch(
        "imagecraft.pack.grubutil._setup_grub_bios",
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


def test_part_num_mbr_plain():
    structure = cast(
        MBRStructureList,
        [MagicMock(spec=MBRStructureItem, partition_number=None) for _ in range(3)],
    )
    for i, name in enumerate(["boot", "data", "rootfs"]):
        structure[i].name = name

    assert grubutil._part_num("boot", structure) == 1
    assert grubutil._part_num("data", structure) == 2
    assert grubutil._part_num("rootfs", structure) == 3


def test_part_num_mbr_extended():
    structure = cast(
        MBRStructureList,
        [MagicMock(spec=MBRStructureItem, partition_number=None) for _ in range(5)],
    )
    for i, name in enumerate(["boot", "p2", "p3", "logical1", "logical2"]):
        structure[i].name = name

    assert grubutil._part_num("boot", structure) == 1
    assert grubutil._part_num("p2", structure) == 2
    assert grubutil._part_num("p3", structure) == 3
    # slot 4 is the synthesised extended container — logical partitions start at 5
    assert grubutil._part_num("logical1", structure) == 5
    assert grubutil._part_num("logical2", structure) == 6


def test_partition_name_from_device():
    assert grubutil._partition_name_from_device("(volume/pc/rootfs)") == "rootfs"


# ── Small pure-logic helpers ─────────────────────────────────────────────


def test_generate_grub_cfg_no_kernels():
    cfg = grubutil._generate_grub_cfg([], "some-uuid", "some-uuid", "/boot")
    assert "search --no-floppy --fs-uuid --set=root some-uuid" in cfg
    assert "menuentry" not in cfg


def test_generate_grub_cfg_with_kernel_and_boot_prefix():
    cfg = grubutil._generate_grub_cfg(
        [("vmlinuz-1", "initrd.img-1")], "uuid-x", "uuid-x", "/boot"
    )
    assert 'menuentry "vmlinuz-1"' in cfg
    assert "linux /boot/vmlinuz-1 root=UUID=uuid-x ro" in cfg
    assert "initrd /boot/initrd.img-1" in cfg


def test_generate_grub_cfg_with_separate_boot_partition_has_no_prefix():
    """When /boot is its own partition, paths aren't prefixed with /boot."""
    cfg = grubutil._generate_grub_cfg([("vmlinuz-1", "")], "uuid-x", "uuid-boot", "")
    assert "linux /vmlinuz-1 root=UUID=uuid-x ro" in cfg
    assert "initrd" not in cfg


def test_generate_grub_cfg_searches_boot_partition_not_root():
    """The kernel lives on /boot, so GRUB has to select that partition."""
    cfg = grubutil._generate_grub_cfg([("vmlinuz-1", "")], "uuid-root", "uuid-boot", "")
    assert "search --no-floppy --fs-uuid --set=root uuid-boot" in cfg
    assert "root=UUID=uuid-root" in cfg


def test_generate_grub_cfg_appends_configured_cmdline():
    """Kernel arguments from /etc/default/grub end up on the linux line."""
    cfg = grubutil._generate_grub_cfg(
        [("vmlinuz-1", "")],
        "uuid-x",
        "uuid-x",
        "/boot",
        grubutil.GrubDefaults(cmdline="console=ttyS0 quiet"),
    )
    assert "linux /boot/vmlinuz-1 root=UUID=uuid-x ro console=ttyS0 quiet" in cfg


def _fake_default_grub(mocker, content: str) -> None:
    """Make /etc/default/grub read back as `content`."""
    mocker.patch.object(grubutil.imgfs, "debugfs_exists", return_value=True)

    def fake_read(_image, _target, local_path):
        Path(local_path).write_text(content)

    mocker.patch.object(grubutil.imgfs, "debugfs_read_file", side_effect=fake_read)


def test_read_grub_defaults_missing_file(mocker):
    mocker.patch.object(grubutil.imgfs, "debugfs_exists", return_value=False)
    assert grubutil._read_grub_defaults(Path("/nonexistent.img")) == (
        grubutil.GrubDefaults()
    )


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
def test_read_grub_defaults_cmdline(mocker, tmp_path, content, expected):
    _fake_default_grub(mocker, content)
    assert grubutil._read_grub_defaults(tmp_path / "root.img").cmdline == expected


def _ext_image_with(tmp_path, files: dict[str, bytes], links: dict[str, str]) -> Path:
    image = tmp_path / "root.img"
    subprocess.run(["truncate", "-s", "32M", image], check=True)
    subprocess.run(["mkfs.ext4", "-q", "-F", image], check=True)
    for path, data in files.items():
        local = tmp_path / Path(path).name
        local.write_bytes(data)
        imgfs.debugfs_write_file(image, local, path)
    for link, dest in links.items():
        imgfs.debugfs_mkdir_p(image, str(Path(link).parent))
        imgfs.debugfs_run(image, [f'symlink "{link}" "{dest}"'])
    return image


def test_dump_signed_efi_binaries_follows_symlinked_shim(tmp_path):
    """Ubuntu ships /usr/lib/shim/shimx64.efi.signed as a symlink."""
    image = _ext_image_with(
        tmp_path,
        {
            "/usr/lib/shim/shimx64.efi.signed.real": b"shim binary",
            "/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed": b"grub binary",
        },
        {"/usr/lib/shim/shimx64.efi.signed": "shimx64.efi.signed.real"},
    )

    result = grubutil._dump_signed_efi_binaries(image, "x86_64-efi", tmp_path / "out")

    assert result is not None
    assert result["shim"].read_bytes() == b"shim binary"
    assert result["grub"].read_bytes() == b"grub binary"


def test_dump_signed_efi_binaries_skips_dangling_shim_symlink(tmp_path):
    """A dangling link must not be deployed as an empty (unbootable) binary."""
    image = _ext_image_with(
        tmp_path,
        {"/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed": b"grub binary"},
        {"/usr/lib/shim/shimx64.efi.signed": "gone.efi"},
    )

    assert (
        grubutil._dump_signed_efi_binaries(image, "x86_64-efi", tmp_path / "out")
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
def test_read_grub_defaults_timeout(mocker, tmp_path, content, expected):
    _fake_default_grub(mocker, content)
    assert grubutil._read_grub_defaults(tmp_path / "root.img").timeout == expected


def test_find_kernels_orders_newest_first(mocker):
    """`set default=0` boots the first entry, which has to be the newest kernel."""
    mocker.patch.object(grubutil.imgfs, "debugfs_exists", return_value=True)
    mocker.patch.object(
        grubutil.imgfs,
        "debugfs_list_dir",
        return_value=[
            "vmlinuz-6.8.0-9-generic",
            "initrd.img-6.8.0-9-generic",
            "vmlinuz-6.8.0-100-generic",
            "initrd.img-6.8.0-100-generic",
            "vmlinuz-6.11.0-1-generic",
        ],
    )

    kernels = grubutil._find_kernels(Path("boot.img"), "/boot")

    assert kernels == [
        ("vmlinuz-6.11.0-1-generic", ""),
        ("vmlinuz-6.8.0-100-generic", "initrd.img-6.8.0-100-generic"),
        ("vmlinuz-6.8.0-9-generic", "initrd.img-6.8.0-9-generic"),
    ]


def test_generate_grub_cfg_uses_configured_timeout():
    cfg = grubutil._generate_grub_cfg(
        [], "uuid-x", "uuid-x", "/boot", grubutil.GrubDefaults(timeout=0)
    )
    assert "set timeout=0" in cfg


def test_generate_grub_cfg_without_fw_setup_has_no_uefi_entry():
    cfg = grubutil._generate_grub_cfg([], "some-uuid", "some-uuid", "/boot")
    assert "UEFI Firmware Settings" not in cfg
    assert "fwsetup" not in cfg


def test_generate_grub_cfg_with_fw_setup_adds_uefi_entry():
    cfg = grubutil._generate_grub_cfg(
        [], "some-uuid", "some-uuid", "/boot", include_fw_setup=True
    )
    assert "menuentry 'UEFI Firmware Settings'" in cfg
    assert "fwsetup" in cfg
    assert 'if [ "${grub_platform}" = "efi" ]; then' in cfg


def test_efi_stub_grub_cfg():
    cfg = grubutil._efi_stub_grub_cfg("abcd-uuid", "/boot")
    assert "search.fs_uuid abcd-uuid root" in cfg
    assert "set prefix=($root)'/boot/grub'" in cfg
    assert "configfile $prefix/grub.cfg" in cfg


def test_efi_stub_grub_cfg_separate_boot_partition():
    """A separate /boot partition holds grub at /grub, and has its own UUID."""
    cfg = grubutil._efi_stub_grub_cfg("boot-uuid", "")
    assert "search.fs_uuid boot-uuid root" in cfg
    assert "set prefix=($root)'/grub'" in cfg


# ── Real, no-privilege end-to-end integration tests ────────────────────────
#
# These build small (a few hundred KiB) real disk images using the same
# tools/helpers the production pack pipeline uses (gptutil/mbrutil/diskutil),
# populate them with fake-but-realistic GRUB/shim/kernel content mirroring
# real Ubuntu package layouts, run the real setup_grub(), then inspect the
# resulting image with mdir/debugfs to check the right files ended up in the
# right places. No mount, loop device, chroot, or VM is used.


def _copy_grub_target_files(src_dir: Path, dest_dir: Path) -> None:
    """Copy a whole real /usr/lib/grub/<target> directory, skipping subdirs."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, dest_dir / item.name)


def _build_and_inject_partition(
    *,
    disk_path: Path,
    tmp_path: Path,
    fstype,
    content_dir: Path,
    label: str | None,
    partition_name: str,
    partition_number: int | None = None,
    sector_size: int = 512,
) -> None:
    if partition_number is not None:
        # MBR partitions have no "name" field in sfdisk --json output, so
        # they must be looked up positionally.
        off = gptutil.get_partition_sector_offset_by_number(disk_path, partition_number)
        size = gptutil.get_partition_size_sectors_by_number(disk_path, partition_number)
    else:
        off = gptutil.get_partition_sector_offset(disk_path, partition_name)
        size = gptutil.get_partition_size_sectors(disk_path, partition_name)
    part_file = tmp_path / f"{partition_name}.img"
    subprocess.run(
        ["truncate", "-s", str(size * sector_size), str(part_file)], check=True
    )
    diskutil.format_populate_partition(
        fstype=fstype, content_dir=content_dir, partitionpath=part_file, label=label
    )
    diskutil.inject_partition_into_image(
        partition=part_file,
        imagepath=disk_path,
        sector_offset=off,
        disk_size=DiskSize(bytesize=size * sector_size, sector_size=sector_size),
    )


@pytest.fixture
def fake_kernel_files():
    def _make(boot_dir: Path) -> None:
        boot_dir.mkdir(parents=True, exist_ok=True)
        (boot_dir / "vmlinuz-6.8.0-generic").write_bytes(b"FAKEKERNEL" * 100)
        (boot_dir / "initrd.img-6.8.0-generic").write_bytes(b"FAKEINITRD" * 100)

    return _make


@pytest.mark.slow
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_signed(new_dir, fake_kernel_files):
    """Signed shim+GRUB, when present in the rootfs, are deployed as-is."""
    from imagecraft.models.volume import FileSystem, GptType, Role  # noqa: PLC0415

    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path("/usr/lib/grub/x86_64-efi"), root_content / "usr/lib/grub/x86_64-efi"
    )
    signed_grub = Path("/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed")
    signed_shim = Path("/usr/lib/shim/shimx64.efi.signed.latest")
    if not (signed_grub.is_file() and signed_shim.is_file()):
        pytest.skip("signed shim/grub not installed on this system")
    (root_content / "usr/lib/grub/x86_64-efi-signed").mkdir(parents=True)
    shutil.copy2(
        signed_grub, root_content / "usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed"
    )
    (root_content / "usr/lib/shim").mkdir(parents=True)
    shutil.copy2(signed_shim, root_content / "usr/lib/shim/shimx64.efi.signed.latest")
    fake_kernel_files(root_content / "boot")

    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)

    volume = GPTVolume(
        schema=PartitionSchema.GPT,
        structure=[
            GPTStructureItem(
                name="efi",
                role=Role.SYSTEM_BOOT,
                size="64M",
                filesystem=FileSystem.VFAT,
                type=GptType("C12A7328-F81F-11D2-BA4B-00A0C93EC93B"),
            ),
            GPTStructureItem(
                name="rootfs",
                role=Role.SYSTEM_DATA,
                size="256M",
                filesystem=FileSystem.EXT4,
                type=GptType("0FC63DAF-8483-4772-8E79-3D69D8477DE4"),
            ),
        ],
    )
    disk_path = tmp_path / "disk.img"
    gptutil.create_empty_gpt_image(imagepath=disk_path, sector_size=512, layout=volume)
    for item, content in (
        (volume.structure[0], esp_content),
        (volume.structure[1], root_content),
    ):
        _build_and_inject_partition(
            disk_path=disk_path,
            tmp_path=tmp_path,
            fstype=item.filesystem,
            content_dir=content,
            label=item.filesystem_label,
            partition_name=item.name,
        )
    gptutil.verify_partition_tables(disk_path)

    image = Image(volume=volume, disk_path=disk_path)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
        ]
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    esp_offset_bytes = gptutil.get_partition_sector_offset(disk_path, "efi") * 512
    for dir_path, stem in (
        ("/EFI/ubuntu", "grubx64"),
        ("/EFI/ubuntu", "shimx64"),
        ("/EFI/BOOT", "BOOTX64"),
        # Shim chainloads grub from beside itself, so the removable path
        # needs its own copy for the fallback boot to work.
        ("/EFI/BOOT", "grubx64"),
    ):
        result = subprocess.run(
            ["mdir", "-i", f"{disk_path}@@{esp_offset_bytes}", f"::{dir_path}"],
            capture_output=True,
            text=True,
            check=True,
        )
        # FAT directory listings render 8.3 names in columns (e.g.
        # "GRUBX64  EFI"), so match on the filename stem rather than the
        # dotted form.
        assert stem in result.stdout

    root_offset = gptutil.get_partition_sector_offset(disk_path, "rootfs")
    root_size = gptutil.get_partition_size_sectors(disk_path, "rootfs")
    with imgfs.edit_ext_partition(disk_path, root_offset, root_size) as root_img:
        cfg_path = tmp_path / "grub.cfg.out"
        imgfs.debugfs_read_file(root_img, "/boot/grub/grub.cfg", cfg_path)
        cfg = cfg_path.read_text()
        assert "vmlinuz-6.8.0-generic" in cfg
        assert "initrd.img-6.8.0-generic" in cfg


@pytest.mark.slow
@pytest.mark.usefixtures("new_dir")
def _build_efi_disk(tmp_path: Path, root_content: Path, esp_content: Path):
    """Build a two-partition (ESP + rootfs) GPT disk from the given content dirs."""
    from imagecraft.models.volume import FileSystem, GptType, Role  # noqa: PLC0415

    volume = GPTVolume(
        schema=PartitionSchema.GPT,
        structure=[
            GPTStructureItem(
                name="efi",
                role=Role.SYSTEM_BOOT,
                size="64M",
                filesystem=FileSystem.VFAT,
                type=GptType("C12A7328-F81F-11D2-BA4B-00A0C93EC93B"),
            ),
            GPTStructureItem(
                name="rootfs",
                role=Role.SYSTEM_DATA,
                size="256M",
                filesystem=FileSystem.EXT4,
                type=GptType("0FC63DAF-8483-4772-8E79-3D69D8477DE4"),
            ),
        ],
    )
    disk_path = tmp_path / "disk.img"
    gptutil.create_empty_gpt_image(imagepath=disk_path, sector_size=512, layout=volume)
    for item, content in (
        (volume.structure[0], esp_content),
        (volume.structure[1], root_content),
    ):
        _build_and_inject_partition(
            disk_path=disk_path,
            tmp_path=tmp_path,
            fstype=item.filesystem,
            content_dir=content,
            label=item.filesystem_label,
            partition_name=item.name,
        )
    image = Image(volume=volume, disk_path=disk_path)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
        ]
    )
    return image, filesystem_mount, disk_path


@pytest.mark.slow
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_unsigned_requires_grub_mkimage(
    new_dir, fake_kernel_files, mocker
):
    """Only the unsigned path builds a binary, and it cannot do so without the tool."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path("/usr/lib/grub/x86_64-efi"), root_content / "usr/lib/grub/x86_64-efi"
    )
    fake_kernel_files(root_content / "boot")
    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)
    image, filesystem_mount, _ = _build_efi_disk(tmp_path, root_content, esp_content)
    mocker.patch(
        "imagecraft.pack.grubutil._check_grub_mkimage_available", return_value=False
    )

    with pytest.raises(errors.GRUBInstallError, match="grub-mkimage is not available"):
        grubutil.setup_grub(
            image=image,
            workdir=tmp_path / "work",
            arch=DebianArchitecture.AMD64,
            filesystem_mount=filesystem_mount,
        )


@pytest.mark.slow
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_skips_without_grub_modules(new_dir, fake_kernel_files, emitter):
    """A rootfs with no GRUB package installed gets no bootloader, not an error."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    fake_kernel_files(root_content / "boot")
    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)
    image, filesystem_mount, _ = _build_efi_disk(tmp_path, root_content, esp_content)

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    emitter.assert_progress(
        "Cannot install GRUB on this rootfs: GRUB modules for x86_64-efi "
        "are not installed in the image",
        permanent=True,
    )


def test_setup_grub_efi_unsigned(new_dir, fake_kernel_files):
    """Without signed shim/GRUB, an unsigned standalone image is built."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path("/usr/lib/grub/x86_64-efi"), root_content / "usr/lib/grub/x86_64-efi"
    )
    fake_kernel_files(root_content / "boot")
    (root_content / "etc/default").mkdir(parents=True)
    (root_content / "etc/default/grub").write_text(
        'GRUB_CMDLINE_LINUX_DEFAULT="console=ttyS0,115200n8"\n'
    )

    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)

    image, filesystem_mount, disk_path = _build_efi_disk(
        tmp_path, root_content, esp_content
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    esp_offset_bytes = gptutil.get_partition_sector_offset(disk_path, "efi") * 512
    result = subprocess.run(
        ["mdir", "-i", f"{disk_path}@@{esp_offset_bytes}", "::/EFI/ubuntu"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "grubx64" in result.stdout
    # No signed shim was available, so no shim binary should be deployed.
    assert "shimx64" not in result.stdout

    root_offset = gptutil.get_partition_sector_offset(disk_path, "rootfs")
    root_size = gptutil.get_partition_size_sectors(disk_path, "rootfs")
    with imgfs.edit_ext_partition(disk_path, root_offset, root_size) as root_img:
        cfg_path = tmp_path / "grub.cfg.out"
        imgfs.debugfs_read_file(root_img, "/boot/grub/grub.cfg", cfg_path)
        assert "console=ttyS0,115200n8" in cfg_path.read_text()


@pytest.mark.slow
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_separate_boot_partition(new_dir, fake_kernel_files):
    """With a dedicated /boot partition, its root (not /boot/...) holds GRUB/kernels."""
    from imagecraft.models.volume import FileSystem, GptType, Role  # noqa: PLC0415

    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path("/usr/lib/grub/x86_64-efi"), root_content / "usr/lib/grub/x86_64-efi"
    )
    boot_content = tmp_path / "boot_content"
    fake_kernel_files(boot_content)

    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)

    volume = GPTVolume(
        schema=PartitionSchema.GPT,
        structure=[
            GPTStructureItem(
                name="efi",
                role=Role.SYSTEM_BOOT,
                size="64M",
                filesystem=FileSystem.VFAT,
                type=GptType("C12A7328-F81F-11D2-BA4B-00A0C93EC93B"),
            ),
            GPTStructureItem(
                name="boot",
                role=Role.SYSTEM_BOOT,
                size="128M",
                filesystem=FileSystem.EXT4,
                type=GptType("0FC63DAF-8483-4772-8E79-3D69D8477DE4"),
            ),
            GPTStructureItem(
                name="rootfs",
                role=Role.SYSTEM_DATA,
                size="256M",
                filesystem=FileSystem.EXT4,
                type=GptType("0FC63DAF-8483-4772-8E79-3D69D8477DE4"),
            ),
        ],
    )
    disk_path = tmp_path / "disk.img"
    gptutil.create_empty_gpt_image(imagepath=disk_path, sector_size=512, layout=volume)
    content_map = {"efi": esp_content, "boot": boot_content, "rootfs": root_content}
    for item in volume.structure:
        _build_and_inject_partition(
            disk_path=disk_path,
            tmp_path=tmp_path,
            fstype=item.filesystem,
            content_dir=content_map[item.name],
            label=item.filesystem_label,
            partition_name=item.name,
        )

    image = Image(volume=volume, disk_path=disk_path)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot/", "device": "(volume/pc/boot)"},
            {"mount": "/boot/efi/", "device": "(volume/pc/efi)"},
        ]
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    boot_offset = gptutil.get_partition_sector_offset(disk_path, "boot")
    boot_size = gptutil.get_partition_size_sectors(disk_path, "boot")
    with imgfs.edit_ext_partition(disk_path, boot_offset, boot_size) as boot_img:
        # The boot partition's *root* is /boot, so grub/kernels live directly
        # at its root, not nested under an extra "boot/" directory.
        root_entries = imgfs.debugfs_list_dir(boot_img, "/")
        assert "grub" in root_entries
        assert "vmlinuz-6.8.0-generic" in root_entries
        assert "initrd.img-6.8.0-generic" in root_entries
        assert "boot" not in root_entries

        cfg_path = tmp_path / "grub.cfg.out"
        imgfs.debugfs_read_file(boot_img, "/grub/grub.cfg", cfg_path)
        cfg = cfg_path.read_text()
        # Paths in grub.cfg must not be prefixed with /boot, since the
        # kernel/initrd already live at this partition's root.
        assert "linux /vmlinuz-6.8.0-generic" in cfg
        assert "linux /boot/vmlinuz-6.8.0-generic" not in cfg

        boot_uuid = imgfs.read_ext_uuid(boot_img)

    root_offset = gptutil.get_partition_sector_offset(disk_path, "rootfs")
    root_size = gptutil.get_partition_size_sectors(disk_path, "rootfs")
    with imgfs.edit_ext_partition(disk_path, root_offset, root_size) as root_img:
        root_uuid = imgfs.read_ext_uuid(root_img)

    assert boot_uuid != root_uuid
    # GRUB loads the kernel off the boot partition but boots the root one.
    assert f"search --no-floppy --fs-uuid --set=root {boot_uuid}" in cfg
    assert f"root=UUID={root_uuid}" in cfg

    esp_offset_bytes = (
        gptutil.get_partition_sector_offset(disk_path, "efi") * imgfs.SECTOR_SIZE
    )
    stub = subprocess.run(
        [
            "mtype",
            "-i",
            f"{disk_path}@@{esp_offset_bytes}",
            "::/EFI/ubuntu/grub.cfg",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    # The ESP stub has to chain to the config on the boot partition.
    assert f"search.fs_uuid {boot_uuid} root" in stub
    assert "set prefix=($root)'/grub'" in stub


@pytest.mark.slow
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_bios_mbr(new_dir, fake_kernel_files):
    """Legacy BIOS/MBR: core.img is embedded and the boot sector patched by hand."""
    from imagecraft.models.volume import (  # noqa: PLC0415
        FileSystem,
        MBRPartitionType,
        Role,
    )

    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path("/usr/lib/grub/i386-pc"), root_content / "usr/lib/grub/i386-pc"
    )
    fake_kernel_files(root_content / "boot")

    volume = MBRVolume(
        schema=PartitionSchema.MBR,
        structure=[
            MBRStructureItem(
                name="rootfs",
                role=Role.SYSTEM_DATA,
                size="256M",
                filesystem=FileSystem.EXT4,
                type=MBRPartitionType("83"),
                filesystem_label="writable",
            ),
        ],
    )
    disk_path = tmp_path / "disk.img"
    mbrutil.create_empty_mbr_image(imagepath=disk_path, sector_size=512, layout=volume)
    _build_and_inject_partition(
        disk_path=disk_path,
        tmp_path=tmp_path,
        fstype=volume.structure[0].filesystem,
        content_dir=root_content,
        label=volume.structure[0].filesystem_label,
        partition_name="rootfs",
        partition_number=1,
    )
    mbrutil.verify_partition_tables(disk_path)

    image = Image(volume=volume, disk_path=disk_path)
    filesystem_mount = FilesystemMount.unmarshal(
        [{"mount": "/", "device": "(volume/pc/rootfs)"}]
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    with disk_path.open("rb") as f:
        sector0 = f.read(512)
    # Boot signature must be preserved.
    assert sector0[0x1FE:0x200] == b"\x55\xaa"
    kernel_sector = int.from_bytes(sector0[0x5C:0x64], "little")
    assert kernel_sector == grubutil._BIOS_CORE_IMG_START_SECTOR

    with disk_path.open("rb") as f:
        f.seek(kernel_sector * 512)
        core_start = f.read(512)
    # core.img was embedded in the gap and isn't all zeros/empty.
    assert any(core_start)
    # Regression test: core.img's own embedded blocklist (in diskboot.img,
    # its first sector) must be patched to point past its own first sector,
    # or SeaBIOS boots the MBR/boot.img/diskboot.img chain but hangs
    # indefinitely trying to load the rest of core.img from the wrong
    # place. grub-mkimage only fills in the blocklist's length, so this
    # start-sector patch is grubutil's responsibility (normally done by
    # grub-bios-setup).
    blocklist_start = int.from_bytes(
        core_start[
            grubutil._BIOS_BLOCKLIST_START_OFFSET : grubutil._BIOS_BLOCKLIST_START_OFFSET
            + 8
        ],
        "little",
    )
    assert blocklist_start == kernel_sector + 1

    root_offset = gptutil.get_partition_sector_offset_by_number(disk_path, 1)
    root_size = gptutil.get_partition_size_sectors_by_number(disk_path, 1)
    with imgfs.edit_ext_partition(disk_path, root_offset, root_size) as root_img:
        assert imgfs.debugfs_exists(root_img, "/boot/grub/i386-pc/core.img")
        assert imgfs.debugfs_exists(root_img, "/boot/grub/i386-pc/boot.img")
        cfg_path = tmp_path / "grub.cfg.out"
        imgfs.debugfs_read_file(root_img, "/boot/grub/grub.cfg", cfg_path)
        assert "vmlinuz-6.8.0-generic" in cfg_path.read_text()
