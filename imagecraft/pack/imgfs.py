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

"""Low-privilege partition image manipulation.

These helpers let callers read and write files inside FAT and ext2/3/4
partitions *embedded in a raw disk image* without mounting anything,
attaching loop devices, chrooting, or spinning up a VM. This lets imagecraft
run in unprivileged containers that can't do any of those things.

FAT partitions are manipulated in place with ``mtools`` using its
``image@@offset`` addressing (no extraction needed). Ext partitions are
manipulated with ``debugfs``, which only understands whole filesystem
images, so the partition is first extracted to a temporary file with
``dd``, edited, then written back with ``dd``.
"""

import contextlib
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

from imagecraft import errors
from imagecraft.subprocesses import run

SECTOR_SIZE = 512
# Minimum number of whitespace-separated fields in a `debugfs ls -l` line
# (inode, mode/type, uid, gid, size, timestamp, name) before the name column.
_DEBUGFS_LS_MIN_FIELDS = 6


def _dd_copy(
    *, src: Path, dst: Path, bs: int, skip: int = 0, seek: int = 0, count: int | None
) -> None:
    args = [
        "dd",
        f"if={src}",
        f"of={dst}",
        f"bs={bs}",
        f"skip={skip}",
        f"seek={seek}",
        "conv=notrunc",
        "status=none",
    ]
    if count is not None:
        args.append(f"count={count}")
    run(*args)


@contextlib.contextmanager
def edit_ext_partition(
    imagepath: Path, offset_sectors: int, size_sectors: int
) -> Iterator[Path]:
    """Extract an ext2/3/4 partition to a temp file for editing with debugfs.

    On successful exit, the (possibly modified) temp file is written back
    into ``imagepath`` at the same location. No mount, loop device, or
    elevated privilege is needed: extraction/injection is done with plain
    ``dd`` reads/writes, and the temp file is edited with ``debugfs -w``.

    :param imagepath: Path to the whole-disk image.
    :param offset_sectors: Partition start, in sectors.
    :param size_sectors: Partition size, in sectors.
    """
    with tempfile.NamedTemporaryFile(
        prefix="imagecraft-ext-", suffix=".img"
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)
        _dd_copy(
            src=imagepath,
            dst=tmp_path,
            bs=SECTOR_SIZE,
            skip=offset_sectors,
            count=size_sectors,
        )
        yield tmp_path
        _dd_copy(
            src=tmp_path,
            dst=imagepath,
            bs=SECTOR_SIZE,
            seek=offset_sectors,
            count=size_sectors,
        )


def debugfs_run(image: Path, commands: list[str]) -> str:
    """Run one or more debugfs requests against an ext2/3/4 image file.

    :param image: Path to the ext2/3/4 filesystem image (a plain file).
    :param commands: debugfs requests to run, e.g. ``["mkdir /foo"]``.
    :raises errors.GRUBInstallError: If debugfs fails.
    """
    script = "\n".join(commands)
    try:
        res = run(
            "debugfs",
            "-w",
            "-f",
            "-",
            str(image),
            input=script,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError(f"debugfs failed running: {commands!r}") from err
    return res.stdout


def debugfs_mkdir_p(image: Path, target_dir: str) -> None:
    """Recursively create a directory inside an ext image, ignoring existing ones."""
    parts = [p for p in target_dir.strip("/").split("/") if p]
    current = ""
    commands = []
    for part in parts:
        current += f"/{part}"
        # mkdir errors if the directory already exists; debugfs just prints
        # a warning to stdout in that case rather than failing the script.
        commands.append(f"mkdir {current}")
    if commands:
        debugfs_run(image, commands)


def debugfs_write_file(image: Path, local_path: Path, target_path: str) -> None:
    """Write a local file into an ext image at target_path."""
    debugfs_mkdir_p(image, str(Path(target_path).parent))
    # debugfs's "write" request creates the destination; remove it first so
    # re-runs (e.g. spread -reuse) don't fail on an existing inode.
    debugfs_run(image, [f"rm {target_path}", f"write {local_path} {target_path}"])


def debugfs_read_file(image: Path, target_path: str, local_path: Path) -> None:
    """Dump a file out of an ext image to a local path."""
    debugfs_run(image, [f"dump {target_path} {local_path}"])


def debugfs_exists(image: Path, target_path: str) -> bool:
    """Check whether a path exists inside an ext image."""
    output = debugfs_run(image, [f"stat {target_path}"])
    return "File not found" not in output and "Inode is not in use" not in output


def debugfs_list_dir(image: Path, target_dir: str) -> list[str]:
    """List file names directly under target_dir inside an ext image."""
    output = debugfs_run(image, [f"ls -l {target_dir}"])
    names: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < _DEBUGFS_LS_MIN_FIELDS:
            continue
        name = fields[-1]
        if name in (".", ".."):
            continue
        names.append(name)
    return names


def _mtools_spec(imagepath: Path, offset_bytes: int) -> str:
    return f"{imagepath}@@{offset_bytes}"


def mcopy_in(
    imagepath: Path, offset_bytes: int, local_path: Path, target_path: str
) -> None:
    """Copy a local file into a FAT partition embedded in imagepath.

    No mount or loop device is used: mtools reads/writes the FAT filesystem
    directly at the given byte offset within the disk image.
    """
    mmd_p(imagepath, offset_bytes, str(Path(target_path).parent))
    spec = _mtools_spec(imagepath, offset_bytes)
    try:
        run("mcopy", "-n", "-o", "-i", spec, str(local_path), f"::{target_path}")
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError(f"mcopy failed writing {target_path}") from err


def mmd_p(imagepath: Path, offset_bytes: int, target_dir: str) -> None:
    """Recursively create a directory inside a FAT partition, ignoring existing ones."""
    target_dir = target_dir.strip("/")
    if not target_dir:
        return
    spec = _mtools_spec(imagepath, offset_bytes)
    parts = target_dir.split("/")
    current = ""
    for part in parts:
        current += f"/{part}"
        # mmd fails if the directory already exists; that's fine here.
        subprocess.run(
            ["mmd", "-i", spec, f"::{current}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def write_local_bytes(local_path: Path, data: bytes) -> None:
    """Write bytes to a local (host, not image) path, creating parent dirs."""
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(data)


def copy_local_tree(src: Path, dst: Path) -> None:
    """Copy a local (host, not image) directory tree, merging into dst."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def read_ext_uuid(image: Path) -> str:
    """Return the filesystem UUID of an ext2/3/4 image file."""
    try:
        res = run("blkid", "-o", "value", "-s", "UUID", str(image))
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError(f"Failed to read UUID of {image}") from err
    return res.stdout.strip()
