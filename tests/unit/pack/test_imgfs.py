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

"""Tests for low-privilege partition image manipulation.

These exercise the real debugfs/mtools/dd tools rather than mocking them:
imgfs is a thin wrapper whose whole job is getting those command lines and
their quirky output formats right, so mocking the tools would test nothing.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from imagecraft import errors
from imagecraft.pack import imgfs

_EXT_IMAGE_SIZE = "16M"
_FAT_IMAGE_SIZE = "8M"
# Offset the embedded partitions so tests actually exercise the offset
# addressing rather than accidentally passing against a zero offset.
_PARTITION_OFFSET_SECTORS = 2048
_PARTITION_OFFSET_BYTES = _PARTITION_OFFSET_SECTORS * imgfs.SECTOR_SIZE


@pytest.fixture(scope="module")
def ext_template(tmp_path_factory) -> Path:
    """A freshly formatted ext4 filesystem image, made once for the module."""
    image = tmp_path_factory.mktemp("templates") / "ext4.img"
    subprocess.run(["truncate", "-s", _EXT_IMAGE_SIZE, image], check=True)
    subprocess.run(["mkfs.ext4", "-q", "-F", image], check=True)
    return image


@pytest.fixture(scope="module")
def fat_template(tmp_path_factory) -> Path:
    """A freshly formatted FAT filesystem image, made once for the module."""
    image = tmp_path_factory.mktemp("templates") / "fat.img"
    subprocess.run(["truncate", "-s", _FAT_IMAGE_SIZE, image], check=True)
    subprocess.run(["mkfs.vfat", image], check=True, stdout=subprocess.DEVNULL)
    return image


@pytest.fixture
def ext_image(ext_template, tmp_path) -> Path:
    """A writable copy of the ext4 filesystem image."""
    image = tmp_path / "ext4.img"
    shutil.copy2(ext_template, image)
    return image


@pytest.fixture
def fat_disk(fat_template, tmp_path) -> Path:
    """A disk image containing a FAT partition at a non-zero offset."""
    disk = tmp_path / "disk.img"
    subprocess.run(["truncate", "-s", "16M", disk], check=True)
    subprocess.run(
        [
            "dd",
            f"if={fat_template}",
            f"of={disk}",
            f"bs={imgfs.SECTOR_SIZE}",
            f"seek={_PARTITION_OFFSET_SECTORS}",
            "conv=notrunc",
            "status=none",
        ],
        check=True,
    )
    return disk


@pytest.fixture
def ext_disk(ext_template, tmp_path) -> tuple[Path, int]:
    """A disk image containing an ext4 partition at a non-zero offset."""
    disk = tmp_path / "disk.img"
    size_sectors = ext_template.stat().st_size // imgfs.SECTOR_SIZE
    subprocess.run(["truncate", "-s", "32M", disk], check=True)
    subprocess.run(
        [
            "dd",
            f"if={ext_template}",
            f"of={disk}",
            f"bs={imgfs.SECTOR_SIZE}",
            f"seek={_PARTITION_OFFSET_SECTORS}",
            "conv=notrunc",
            "status=none",
        ],
        check=True,
    )
    return disk, size_sectors


def _fat_list(disk: Path, target_dir: str) -> list[str]:
    """List a FAT directory, using mdir's bare output for stable parsing."""
    result = subprocess.run(
        ["mdir", "-b", "-i", f"{disk}@@{_PARTITION_OFFSET_BYTES}", target_dir],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.split()


def _fat_read(disk: Path, target_path: str, local_path: Path) -> bytes:
    """Read a file back out of a FAT partition."""
    subprocess.run(
        [
            "mcopy",
            "-n",
            "-i",
            f"{disk}@@{_PARTITION_OFFSET_BYTES}",
            f"::{target_path}",
            str(local_path),
        ],
        check=True,
        capture_output=True,
    )
    return local_path.read_bytes()


def test_debugfs_write_and_read_file_round_trip(ext_image, tmp_path):
    source = tmp_path / "grub.cfg"
    source.write_text("set timeout=5\n")
    readback = tmp_path / "readback.cfg"

    imgfs.debugfs_write_file(ext_image, source, "/boot/grub/grub.cfg")
    imgfs.debugfs_read_file(ext_image, "/boot/grub/grub.cfg", readback)

    assert readback.read_text() == "set timeout=5\n"


def test_debugfs_write_file_overwrites_existing(ext_image, tmp_path):
    """Re-running an install (e.g. spread -reuse) must not fail on an existing inode."""
    source = tmp_path / "grub.cfg"
    readback = tmp_path / "readback.cfg"

    source.write_text("first\n")
    imgfs.debugfs_write_file(ext_image, source, "/boot/grub.cfg")
    source.write_text("second\n")
    imgfs.debugfs_write_file(ext_image, source, "/boot/grub.cfg")

    imgfs.debugfs_read_file(ext_image, "/boot/grub.cfg", readback)
    assert readback.read_text() == "second\n"


def test_debugfs_mkdir_p_creates_nested_directories(ext_image):
    imgfs.debugfs_mkdir_p(ext_image, "/boot/grub/i386-pc")

    assert imgfs.debugfs_exists(ext_image, "/boot")
    assert imgfs.debugfs_exists(ext_image, "/boot/grub")
    assert imgfs.debugfs_exists(ext_image, "/boot/grub/i386-pc")


def test_debugfs_mkdir_p_is_idempotent(ext_image):
    imgfs.debugfs_mkdir_p(ext_image, "/boot/grub")
    imgfs.debugfs_mkdir_p(ext_image, "/boot/grub")

    assert imgfs.debugfs_exists(ext_image, "/boot/grub")


def test_debugfs_mkdir_p_ignores_empty_path(ext_image):
    """A target of "/" has no components to create and must not invoke debugfs."""
    imgfs.debugfs_mkdir_p(ext_image, "/")


def test_debugfs_mkdir_p_raises_when_a_file_is_in_the_way(ext_image, tmp_path):
    """debugfs prints "already exists" for a blocking file and still exits 0."""
    source = tmp_path / "src"
    source.write_text("data\n")
    imgfs.debugfs_write_file(ext_image, source, "/boot/grub")

    with pytest.raises(errors.GRUBInstallError, match="failed creating directory"):
        imgfs.debugfs_mkdir_p(ext_image, "/boot/grub")


def test_debugfs_mkdir_p_raises_when_a_parent_is_a_file(ext_image, tmp_path):
    """A file part-way down the path stops every directory below it."""
    source = tmp_path / "src"
    source.write_text("data\n")
    imgfs.debugfs_write_file(ext_image, source, "/boot/grub")

    with pytest.raises(errors.GRUBInstallError, match="failed creating directory"):
        imgfs.debugfs_mkdir_p(ext_image, "/boot/grub/x86_64-efi")


def test_debugfs_exists_false_for_missing_path(ext_image):
    assert not imgfs.debugfs_exists(ext_image, "/nonexistent")


def _make_symlink(image, link_path: str, dest: str) -> None:
    imgfs.debugfs_mkdir_p(image, link_path.rsplit("/", 1)[0])
    imgfs.debugfs_run(image, [f'symlink "{link_path}" "{dest}"'])


def test_debugfs_read_file_follows_symlinks(ext_image, tmp_path):
    """Ubuntu ships /usr/lib/shim/shimx64.efi.signed as a symlink."""
    source = tmp_path / "shim"
    source.write_bytes(b"signed shim\n")
    readback = tmp_path / "readback"
    imgfs.debugfs_write_file(ext_image, source, "/usr/lib/shim/shimx64.efi.signed.real")
    _make_symlink(
        ext_image, "/usr/lib/shim/shimx64.efi.signed", "shimx64.efi.signed.real"
    )

    imgfs.debugfs_read_file(ext_image, "/usr/lib/shim/shimx64.efi.signed", readback)

    assert readback.read_bytes() == b"signed shim\n"


def test_debugfs_read_file_follows_absolute_symlink_chain(ext_image, tmp_path):
    source = tmp_path / "shim"
    source.write_bytes(b"signed shim\n")
    readback = tmp_path / "readback"
    imgfs.debugfs_write_file(
        ext_image, source, "/usr/lib/shim/shimx64.efi.signed.latest"
    )
    _make_symlink(
        ext_image,
        "/etc/alternatives/shimx64.efi.signed",
        "/usr/lib/shim/shimx64.efi.signed.latest",
    )
    _make_symlink(
        ext_image,
        "/usr/lib/shim/shimx64.efi.signed",
        "/etc/alternatives/shimx64.efi.signed",
    )

    imgfs.debugfs_read_file(ext_image, "/usr/lib/shim/shimx64.efi.signed", readback)

    assert readback.read_bytes() == b"signed shim\n"


def test_debugfs_read_file_raises_on_dangling_symlink(ext_image, tmp_path):
    """A dangling link would otherwise dump an empty file and be deployed as-is."""
    _make_symlink(ext_image, "/usr/lib/shim/shimx64.efi.signed", "gone.efi")

    with pytest.raises(errors.GRUBInstallError):
        imgfs.debugfs_read_file(
            ext_image, "/usr/lib/shim/shimx64.efi.signed", tmp_path / "out"
        )


def test_debugfs_is_regular_file_rejects_directories_and_dangling_links(ext_image):
    imgfs.debugfs_mkdir_p(ext_image, "/boot/grub")
    _make_symlink(ext_image, "/boot/dangling", "nowhere")

    assert not imgfs.debugfs_is_regular_file(ext_image, "/boot/grub")
    assert not imgfs.debugfs_is_regular_file(ext_image, "/boot/dangling")
    assert not imgfs.debugfs_is_regular_file(ext_image, "/nonexistent")


def test_debugfs_is_regular_file_rejects_symlink_loop(ext_image):
    _make_symlink(ext_image, "/boot/a", "/boot/b")
    _make_symlink(ext_image, "/boot/b", "/boot/a")

    assert not imgfs.debugfs_is_regular_file(ext_image, "/boot/a")


@pytest.mark.parametrize(
    "name", ["No space left", "Could not allocate", "File not found"]
)
def test_debugfs_tolerates_paths_that_look_like_errors(ext_image, tmp_path, name):
    """debugfs echoes each request, so a path must not be read as its output."""
    source = tmp_path / "payload"
    source.write_text("payload\n")

    imgfs.debugfs_write_file(ext_image, source, f"/{name}")

    assert name in imgfs.debugfs_list_dir(ext_image, "/")


def test_debugfs_list_dir_excludes_dot_entries(ext_image, tmp_path):
    source = tmp_path / "vmlinuz"
    source.write_text("kernel\n")
    imgfs.debugfs_write_file(ext_image, source, "/boot/vmlinuz-6.8.0-generic")

    names = imgfs.debugfs_list_dir(ext_image, "/boot")

    assert "vmlinuz-6.8.0-generic" in names
    assert "." not in names
    assert ".." not in names


def test_debugfs_list_dir_on_empty_directory(ext_image):
    imgfs.debugfs_mkdir_p(ext_image, "/empty")

    assert imgfs.debugfs_list_dir(ext_image, "/empty") == []


def test_debugfs_run_raises_when_image_cannot_be_opened(tmp_path):
    """debugfs exits 0 on an unusable image, so failure must be caught in its output."""
    not_an_image = tmp_path / "garbage.img"
    not_an_image.write_text("definitely not a filesystem")

    with pytest.raises(errors.GRUBInstallError, match="debugfs failed running"):
        imgfs.debugfs_run(not_an_image, ["ls -l /"])


def test_debugfs_run_raises_for_missing_image(tmp_path):
    with pytest.raises(errors.GRUBInstallError, match="debugfs failed running"):
        imgfs.debugfs_run(tmp_path / "missing.img", ["ls -l /"])


def test_debugfs_run_does_not_raise_for_missing_path(ext_image):
    """A missing path inside a healthy image is not a fatal error."""
    output = imgfs.debugfs_run(ext_image, ["stat /nonexistent"])

    assert "File not found" in output


@pytest.mark.parametrize("bad_path", ["/a\nmkdir /pwned", "/a\rb", "/a\x01b", '/a"b'])
def test_debugfs_helpers_reject_unsafe_paths(ext_image, tmp_path, bad_path):
    """debugfs scripts are newline-delimited, so a newline injects a request."""
    source = tmp_path / "payload"
    source.write_text("payload\n")

    with pytest.raises(errors.GRUBInstallError, match="unsafe path"):
        imgfs.debugfs_write_file(ext_image, source, bad_path)

    assert not imgfs.debugfs_exists(ext_image, "/pwned")


def test_debugfs_write_and_read_file_with_spaces_in_path(ext_image, tmp_path):
    """Unquoted paths with spaces are silently mis-parsed by debugfs."""
    source = tmp_path / "src with space"
    source.write_text("spaced\n")
    imgfs.debugfs_write_file(ext_image, source, "/dir with space/file name.txt")

    assert imgfs.debugfs_list_dir(ext_image, "/dir with space") == ["file name.txt"]

    dest = tmp_path / "out"
    imgfs.debugfs_read_file(ext_image, "/dir with space/file name.txt", dest)
    assert dest.read_text() == "spaced\n"


def test_debugfs_read_file_raises_for_missing_file(ext_image, tmp_path):
    """A failed dump must not leave the caller reading stale local content."""
    dest = tmp_path / "out"
    dest.write_text("stale\n")

    with pytest.raises(errors.GRUBInstallError, match="failed dumping"):
        imgfs.debugfs_read_file(ext_image, "/nonexistent", dest)

    assert not dest.exists()


def test_debugfs_write_file_rejects_a_missing_source(ext_image, tmp_path):
    """debugfs creates an empty target from a missing source and exits 0."""
    with pytest.raises(errors.GRUBInstallError, match="not a regular file"):
        imgfs.debugfs_write_file(ext_image, tmp_path / "missing", "/target.txt")

    assert not imgfs.debugfs_exists(ext_image, "/target.txt")


def test_debugfs_run_forces_c_locale(ext_image, mocker):
    """debugfs failures are detected by message text, which e2fsprogs translates."""
    spy = mocker.spy(imgfs, "run")

    imgfs.debugfs_run(ext_image, ["ls -l /"])

    assert spy.call_args.kwargs["env"]["LC_ALL"] == "C"


def test_debugfs_write_file_raises_when_filesystem_is_full(tmp_path):
    """A failed write still creates an inode of the right size, holding garbage."""
    small_image = tmp_path / "tiny.img"
    subprocess.run(
        [
            "dd",
            "if=/dev/zero",
            f"of={small_image}",
            "bs=1K",
            "count=512",
            "status=none",
        ],
        check=True,
    )
    subprocess.run(["mkfs.ext2", "-q", "-F", str(small_image)], check=True)
    too_big = tmp_path / "too-big.bin"
    too_big.write_bytes(b"\xab" * 600 * 1024)

    with pytest.raises(errors.GRUBInstallError, match="debugfs failed running"):
        imgfs.debugfs_write_file(small_image, too_big, "/too-big.bin")


def test_debugfs_write_file_raises_when_target_is_a_directory(ext_image, tmp_path):
    """A directory at the target defeats both the rm and the write."""
    source = tmp_path / "grub.cfg"
    source.write_text("cfg\n")
    imgfs.debugfs_mkdir_p(ext_image, "/boot/grub.cfg")

    with pytest.raises(errors.GRUBInstallError, match="failed writing"):
        imgfs.debugfs_write_file(ext_image, source, "/boot/grub.cfg")


def test_debugfs_write_file_rejects_forged_type_in_path(ext_image, tmp_path):
    """debugfs echoes the requested path, which must not fake the stat type."""
    source = tmp_path / "grub.cfg"
    source.write_text("cfg\n")
    forged = "/boot/x Type: regular"
    imgfs.debugfs_mkdir_p(ext_image, forged)

    with pytest.raises(errors.GRUBInstallError, match="failed writing"):
        imgfs.debugfs_write_file(ext_image, source, forged)


def test_debugfs_list_dir_unescapes_names(ext_image, tmp_path):
    """debugfs escapes bytes it can't print, one `\\xNN` escape per byte."""
    source = tmp_path / "src"
    source.write_text("data\n")
    for name in ("café.txt", "back\\slash.txt"):
        imgfs.debugfs_write_file(ext_image, source, f"/escapes/{name}")

    assert sorted(imgfs.debugfs_list_dir(ext_image, "/escapes")) == [
        "back\\slash.txt",
        "café.txt",
    ]


def test_debugfs_list_dir_allows_error_text_as_a_file_name(ext_image, tmp_path):
    """Only lines that aren't directory entries can be reporting an error."""
    source = tmp_path / "src"
    source.write_text("data\n")
    imgfs.debugfs_write_file(ext_image, source, "/tricky/File not found")

    assert imgfs.debugfs_list_dir(ext_image, "/tricky") == ["File not found"]


def test_debugfs_list_dir_raises_for_missing_directory(ext_image):
    """Error text must not be parsed as if it were a directory entry."""
    with pytest.raises(errors.GRUBInstallError, match="No such directory"):
        imgfs.debugfs_list_dir(ext_image, "/nonexistent")


def test_debugfs_list_dir_raises_for_a_regular_file(ext_image, tmp_path):
    """`ls` on a file exits 0, which would otherwise look like an empty directory."""
    source = tmp_path / "src"
    source.write_text("data\n")
    imgfs.debugfs_write_file(ext_image, source, "/boot/grub")

    with pytest.raises(errors.GRUBInstallError, match="is not a directory"):
        imgfs.debugfs_list_dir(ext_image, "/boot/grub")


def test_debugfs_write_file_rejects_a_directory_source(ext_image, tmp_path):
    """debugfs allocates an inode full of junk from a directory and exits 0."""
    source = tmp_path / "srcdir"
    source.mkdir()

    with pytest.raises(errors.GRUBInstallError, match="not a regular file"):
        imgfs.debugfs_write_file(ext_image, source, "/boot/grub.cfg")

    assert not imgfs.debugfs_exists(ext_image, "/boot/grub.cfg")


def test_edit_ext_partition_persists_changes_into_disk(ext_disk, tmp_path):
    disk, size_sectors = ext_disk
    source = tmp_path / "grub.cfg"
    source.write_text("set default=0\n")

    with imgfs.edit_ext_partition(
        disk, _PARTITION_OFFSET_SECTORS, size_sectors
    ) as partition:
        imgfs.debugfs_write_file(partition, source, "/boot/grub/grub.cfg")

    # Re-extract from the disk to prove the edit was written back, rather
    # than only existing in the temporary file.
    readback = tmp_path / "readback.cfg"
    with imgfs.edit_ext_partition(
        disk, _PARTITION_OFFSET_SECTORS, size_sectors
    ) as partition:
        assert imgfs.debugfs_exists(partition, "/boot/grub/grub.cfg")
        imgfs.debugfs_read_file(partition, "/boot/grub/grub.cfg", readback)

    assert readback.read_text() == "set default=0\n"


def test_edit_ext_partition_does_not_disturb_surrounding_disk(ext_disk, tmp_path):
    """Writing the partition back must not clobber bytes outside it."""
    disk, size_sectors = ext_disk
    sentinel = b"\xde\xad\xbe\xef"
    with disk.open("r+b") as handle:
        handle.write(sentinel)

    source = tmp_path / "file"
    source.write_text("data\n")
    with imgfs.edit_ext_partition(
        disk, _PARTITION_OFFSET_SECTORS, size_sectors
    ) as partition:
        imgfs.debugfs_write_file(partition, source, "/file")

    with disk.open("rb") as handle:
        assert handle.read(len(sentinel)) == sentinel


def test_edit_ext_partition_reads_expected_region(ext_disk):
    """The extracted temp file is a valid filesystem, proving the offset is right."""
    disk, size_sectors = ext_disk

    with imgfs.edit_ext_partition(
        disk, _PARTITION_OFFSET_SECTORS, size_sectors
    ) as partition:
        assert partition.stat().st_size == size_sectors * imgfs.SECTOR_SIZE
        assert imgfs.debugfs_exists(partition, "/lost+found")


def test_edit_ext_partition_raises_when_disk_is_too_small(ext_disk):
    """dd stops at end-of-input and exits 0, so short reads must be caught."""
    disk, size_sectors = ext_disk

    with pytest.raises(errors.GRUBInstallError, match="too small"):
        with imgfs.edit_ext_partition(
            disk, _PARTITION_OFFSET_SECTORS, size_sectors * 100
        ):
            pass


def test_edit_ext_partition_raises_when_edited_partition_shrinks(ext_disk):
    """A truncated temp file must not be written back over the disk."""
    disk, size_sectors = ext_disk

    with pytest.raises(errors.GRUBInstallError, match="too small"):  # noqa: PT012
        with imgfs.edit_ext_partition(
            disk, _PARTITION_OFFSET_SECTORS, size_sectors
        ) as partition:
            with partition.open("r+b") as handle:
                handle.truncate(imgfs.SECTOR_SIZE)


def test_mcopy_in_writes_file_at_offset(fat_disk, tmp_path):
    source = tmp_path / "grubx64.efi"
    source.write_bytes(b"EFI binary")

    imgfs.mcopy_in(fat_disk, _PARTITION_OFFSET_BYTES, source, "/EFI/BOOT/BOOTX64.EFI")

    assert _fat_list(fat_disk, "::/EFI/BOOT") == ["::/EFI/BOOT/BOOTX64.EFI"]
    assert (
        _fat_read(fat_disk, "/EFI/BOOT/BOOTX64.EFI", tmp_path / "out") == b"EFI binary"
    )


def test_mcopy_in_creates_parent_directories(fat_disk, tmp_path):
    source = tmp_path / "grub.cfg"
    source.write_text("configfile\n")

    imgfs.mcopy_in(fat_disk, _PARTITION_OFFSET_BYTES, source, "/EFI/ubuntu/grub.cfg")

    assert "::/EFI/ubuntu/grub.cfg" in _fat_list(fat_disk, "::/EFI/ubuntu")


def test_mcopy_in_overwrites_existing_file(fat_disk, tmp_path):
    source = tmp_path / "file"
    source.write_bytes(b"first")
    imgfs.mcopy_in(fat_disk, _PARTITION_OFFSET_BYTES, source, "/EFI/file")
    source.write_bytes(b"second-and-longer")

    imgfs.mcopy_in(fat_disk, _PARTITION_OFFSET_BYTES, source, "/EFI/file")

    assert _fat_read(fat_disk, "/EFI/file", tmp_path / "out") == b"second-and-longer"


def test_mcopy_in_raises_on_failure(fat_disk, tmp_path):
    with pytest.raises(errors.GRUBInstallError, match="mcopy failed writing"):
        imgfs.mcopy_in(
            fat_disk, _PARTITION_OFFSET_BYTES, tmp_path / "missing", "/nope.efi"
        )


def test_mcopy_in_raises_when_target_is_a_directory(fat_disk, tmp_path):
    """mcopy would otherwise copy the source in *under* the directory."""
    source = tmp_path / "grub.cfg"
    source.write_text("configfile\n")
    imgfs.mmd_p(fat_disk, _PARTITION_OFFSET_BYTES, "/EFI/ubuntu")

    with pytest.raises(errors.GRUBInstallError, match="it is a directory"):
        imgfs.mcopy_in(fat_disk, _PARTITION_OFFSET_BYTES, source, "/EFI/ubuntu")


def test_mmd_p_is_idempotent(fat_disk):
    imgfs.mmd_p(fat_disk, _PARTITION_OFFSET_BYTES, "/EFI/BOOT")
    imgfs.mmd_p(fat_disk, _PARTITION_OFFSET_BYTES, "/EFI/BOOT")

    assert "::/EFI/BOOT/" in _fat_list(fat_disk, "::/EFI")


def test_mmd_p_raises_when_a_file_is_in_the_way(fat_disk, tmp_path):
    """mdir accepts a file path by listing its parent, so it can't be the check."""
    source = tmp_path / "file"
    source.write_bytes(b"not a directory")
    imgfs.mcopy_in(fat_disk, _PARTITION_OFFSET_BYTES, source, "/EFI/BOOT")

    with pytest.raises(errors.GRUBInstallError, match="mmd failed"):
        imgfs.mmd_p(fat_disk, _PARTITION_OFFSET_BYTES, "/EFI/BOOT")


def test_mmd_p_ignores_empty_path(fat_disk):
    """A target of "/" is the FAT root, which always exists."""
    imgfs.mmd_p(fat_disk, _PARTITION_OFFSET_BYTES, "/")


def test_mmd_p_raises_when_directory_cannot_be_created(fat_disk):
    """mtools reports a real failure the same way as an existing directory."""
    with pytest.raises(errors.GRUBInstallError, match="mmd failed"):
        imgfs.mmd_p(fat_disk, _PARTITION_OFFSET_BYTES + 1, "/EFI/BOOT")


def test_write_local_bytes_creates_parents(tmp_path):
    target = tmp_path / "deeply" / "nested" / "core.img"

    imgfs.write_local_bytes(target, b"\x01\x02\x03")

    assert target.read_bytes() == b"\x01\x02\x03"


def test_copy_local_tree_preserves_nested_structure(tmp_path):
    src = tmp_path / "src"
    (src / "i386-pc").mkdir(parents=True)
    (src / "i386-pc" / "boot.img").write_bytes(b"boot")
    (src / "top.mod").write_bytes(b"mod")
    dst = tmp_path / "dst"

    imgfs.copy_local_tree(src, dst)

    assert (dst / "i386-pc" / "boot.img").read_bytes() == b"boot"
    assert (dst / "top.mod").read_bytes() == b"mod"


def test_copy_local_tree_merges_into_existing_destination(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "new.mod").write_bytes(b"new")
    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "existing.mod").write_bytes(b"existing")

    imgfs.copy_local_tree(src, dst)

    assert (dst / "existing.mod").read_bytes() == b"existing"
    assert (dst / "new.mod").read_bytes() == b"new"


def test_read_ext_uuid(ext_image):
    uuid = imgfs.read_ext_uuid(ext_image)

    assert re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", uuid)


def test_read_ext_uuid_raises_on_failure(tmp_path):
    missing = tmp_path / "missing.img"

    with pytest.raises(errors.GRUBInstallError, match="Failed to read UUID"):
        imgfs.read_ext_uuid(missing)


def test_debugfs_handles_non_ascii_paths_under_a_non_utf8_locale(ext_image, tmp_path):
    """The forced C locale must not make *this* process encode its pipes as ASCII."""
    source = tmp_path / "payload"
    source.write_text("payload\n")
    # The child's source stays pure ASCII: under LC_ALL=C python decodes
    # `-c` with the ASCII filesystem encoding.
    script = (
        "from pathlib import Path\n"
        "from craft_cli import EmitterMode, emit\n"
        "emit.init(EmitterMode.QUIET, 'test', 'test')\n"
        "from imagecraft.pack import imgfs\n"
        f"imgfs.debugfs_write_file(Path({str(ext_image)!r}), Path({str(source)!r}),"
        ' "/boot/boot-\\u00e9.cfg")\n'
    )

    subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env={
            **os.environ,
            "LC_ALL": "C",
            "LANG": "C",
            "PYTHONUTF8": "0",
            "PYTHONCOERCECLOCALE": "0",
        },
        capture_output=True,
    )

    assert "boot-\u00e9.cfg" in imgfs.debugfs_list_dir(ext_image, "/boot")
