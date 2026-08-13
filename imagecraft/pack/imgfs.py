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
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

from imagecraft import errors
from imagecraft.subprocesses import run

SECTOR_SIZE = 512
# A `debugfs ls -l` row: inode, mode, (filetype), uid, gid, size, date, time,
# then the name, which may itself contain spaces and so runs to end of line.
_DEBUGFS_LS_LINE_RE = re.compile(
    r"^\s*\d+\s+\d+\s+\(\d+\)\s+\d+\s+\d+\s+\d+\s+\S+\s+\S+\s(?P<name>.+)$"
)
# debugfs exits 0 even when it couldn't open the filesystem at all, so that
# failure has to be spotted in its output instead of via the return code.
# These markers only appear when the image itself is unusable; an ordinary
# missing path reports "File not found by ext2_lookup" and is not fatal.
_DEBUGFS_OPEN_FAILURE_MARKERS = ("Filesystem not open", "while trying to open")
# debugfs also exits 0 when an individual request fails, and a failed "write"
# leaves behind an inode of the right size holding truncated data, so the
# result can't be validated by inspecting the image afterwards either.
_DEBUGFS_REQUEST_FAILURE_MARKERS = (
    "Could not allocate",
    "No space left",
    "while allocating",
    "while expanding",
    "while writing",
    "Usage: ",
)
_DEBUGFS_NOT_FOUND_MARKERS = ("File not found", "Inode is not in use")
# `ls` on a regular file reports this and still exits 0, which would
# otherwise be indistinguishable from an empty directory.
_DEBUGFS_NOT_A_DIRECTORY_MARKER = "Ext2 inode is not a directory"
# debugfs prefixes every request it echoes back with its own prompt.
_DEBUGFS_ECHO_PREFIX = "debugfs: "
# `stat` reports the inode type on the same line as the inode number, which
# is where it has to be read from: debugfs echoes the requested path too, so
# scanning the whole output would let a crafted path fake a type.
_DEBUGFS_STAT_TYPE_RE = re.compile(r"^Inode:.*\bType:\s+(\w+)", re.MULTILINE)
# A symlink short enough to live in the inode itself has its target reported
# by `stat`; longer ones are stored in a block and aren't reported at all.
_DEBUGFS_FAST_LINK_RE = re.compile(r'^Fast link dest: "(.*)"', re.MULTILINE)
# debugfs escapes bytes it can't print in `ls` output, one `\xNN` per byte.
_DEBUGFS_ESCAPE_RE = re.compile(r"\\x([0-9a-fA-F]{2})")
# Characters that can't be expressed in a debugfs script argument: the quote
# character it delimits arguments with, and control characters (a newline in
# particular terminates the request and starts another one).
_DEBUGFS_UNSAFE_PATH_RE = re.compile(r'["\x00-\x1f\x7f]')
# debugfs reports failures only in prose, which e2fsprogs translates, so its
# messages have to be forced back to English to stay machine-readable.
_C_LOCALE_ENV = {**os.environ, "LC_ALL": "C", "LANGUAGE": "C"}


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


def _dd_copy_exact(
    *, src: Path, dst: Path, bs: int, skip: int = 0, seek: int = 0, count: int
) -> None:
    """Copy exactly ``count`` blocks, failing if fewer are available.

    ``dd`` stops at end-of-input and still exits 0, so a truncated image or
    an out-of-range partition would otherwise yield a short filesystem that
    subsequent tools happily corrupt.
    """
    available = src.stat().st_size - skip * bs
    if available < count * bs:
        raise errors.GRUBInstallError(
            f"{src} is too small: needs {count * bs} bytes at offset {skip * bs}"
        )
    _dd_copy(src=src, dst=dst, bs=bs, skip=skip, seek=seek, count=count)


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
        _dd_copy_exact(
            src=imagepath,
            dst=tmp_path,
            bs=SECTOR_SIZE,
            skip=offset_sectors,
            count=size_sectors,
        )
        yield tmp_path
        _dd_copy_exact(
            src=tmp_path,
            dst=imagepath,
            bs=SECTOR_SIZE,
            seek=offset_sectors,
            count=size_sectors,
        )


def _debugfs_quote(path: str) -> str:
    """Quote a path for debugfs's script parser.

    debugfs reads its script line by line and splits on whitespace, so an
    unquoted path containing a space silently turns into the wrong request,
    and a path containing a newline injects an entirely new request.
    """
    if _DEBUGFS_UNSAFE_PATH_RE.search(path):
        raise errors.GRUBInstallError(
            f"Refusing to pass unsafe path to debugfs: {path!r}"
        )
    return f'"{path}"'


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
            env=_C_LOCALE_ENV,
            # The forced C locale applies to debugfs, not to this process's
            # pipes, which would otherwise be encoded using the ambient
            # locale and fail on a non-ASCII path.
            encoding="utf-8",
        )
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError(f"debugfs failed running: {commands!r}") from err
    if any(
        marker in line
        for line in _debugfs_diagnostic_lines(res.stdout)
        for marker in _DEBUGFS_OPEN_FAILURE_MARKERS + _DEBUGFS_REQUEST_FAILURE_MARKERS
    ):
        raise errors.GRUBInstallError(
            f"debugfs failed running: {commands!r}", details=res.stdout
        )
    return res.stdout


def _debugfs_diagnostic_lines(output: str) -> list[str]:
    """Return the lines of debugfs output that can carry an error message.

    debugfs echoes every request it runs, and ``ls`` prints file names, so
    both can contain arbitrary caller-supplied text; scanning them for error
    markers would let a path such as "/No space left" fake a failure.
    """
    return [
        line
        for line in output.splitlines()
        if not line.startswith(_DEBUGFS_ECHO_PREFIX)
        and not _DEBUGFS_LS_LINE_RE.match(line)
    ]


def debugfs_mkdir_p(image: Path, target_dir: str) -> None:
    """Recursively create a directory inside an ext image, ignoring existing ones.

    :raises errors.GRUBInstallError: If the directory isn't there afterwards.
    """
    parts = [p for p in target_dir.strip("/").split("/") if p]
    current = ""
    commands = []
    for part in parts:
        current += f"/{part}"
        # mkdir errors if the directory already exists; debugfs just prints
        # a warning to stdout in that case rather than failing the script.
        commands.append(f"mkdir {_debugfs_quote(current)}")
    if not commands:
        return
    debugfs_run(image, commands)
    # A regular file anywhere along the path defeats mkdir while debugfs
    # still exits 0, so confirm a directory really landed.
    if _debugfs_stat_type(image, current) != "directory":
        raise errors.GRUBInstallError(
            f"debugfs failed creating directory {target_dir} in {image}"
        )


def debugfs_write_file(image: Path, local_path: Path, target_path: str) -> None:
    """Write a local file into an ext image at target_path.

    :raises errors.GRUBInstallError: If the file isn't present afterwards.
    """
    # debugfs happily allocates an inode from a directory source and exits 0,
    # writing junk rather than failing.
    if not local_path.is_file():
        raise errors.GRUBInstallError(
            f"Cannot write {local_path} into {image}: not a regular file"
        )
    debugfs_mkdir_p(image, str(Path(target_path).parent))
    # debugfs's "write" request creates the destination; remove it first so
    # re-runs (e.g. spread -reuse) don't fail on an existing inode.
    debugfs_run(
        image,
        [
            f"rm {_debugfs_quote(target_path)}",
            f"write {_debugfs_quote(str(local_path))} {_debugfs_quote(target_path)}",
        ],
    )
    # debugfs reports per-request failures (a full filesystem, a bad request)
    # on stdout and still exits 0, so confirm a regular file really landed:
    # a pre-existing directory at target_path defeats both rm and write while
    # still satisfying a plain existence check.
    if _debugfs_stat_type(image, target_path) != "regular":
        raise errors.GRUBInstallError(
            f"debugfs failed writing {local_path} to {target_path} in {image}"
        )


def debugfs_read_file(image: Path, target_path: str, local_path: Path) -> None:
    """Dump a file out of an ext image to a local path.

    Symlinks are resolved first: "dump" reads the inode it is given, so
    dumping a symlink writes an empty file rather than the file linked to.

    :raises errors.GRUBInstallError: If the file couldn't be dumped.
    """
    # A failed "dump" would otherwise leave any pre-existing local file in
    # place, making the caller silently read stale content.
    local_path.unlink(missing_ok=True)
    resolved = _debugfs_resolve_symlinks(image, target_path)
    if resolved is None:
        raise errors.GRUBInstallError(
            f"debugfs failed dumping {target_path} from {image}: not a regular file"
        )
    debugfs_run(
        image,
        [f"dump {_debugfs_quote(resolved)} {_debugfs_quote(str(local_path))}"],
    )
    if not local_path.exists():
        raise errors.GRUBInstallError(
            f"debugfs failed dumping {target_path} from {image}"
        )


def _debugfs_stat(image: Path, target_path: str) -> str:
    return debugfs_run(image, [f"stat {_debugfs_quote(target_path)}"])


def _debugfs_stat_type(image: Path, target_path: str) -> str | None:
    """Return the inode type reported by ``stat``, or None if there is none.

    debugfs echoes each request, including the target path, so the type has
    to be read off the ``Inode:`` line rather than found anywhere in the
    output: a path containing "Type: regular" would otherwise forge it.
    """
    match = _DEBUGFS_STAT_TYPE_RE.search(_debugfs_stat(image, target_path))
    return match.group(1) if match else None


def debugfs_exists(image: Path, target_path: str) -> bool:
    """Check whether a path exists inside an ext image."""
    return _debugfs_stat_type(image, target_path) is not None


def _debugfs_resolve_symlinks(
    image: Path, target_path: str, *, max_hops: int = 8
) -> str | None:
    """Follow symlinks inside an ext image down to a regular file.

    Returns the resolved path, or None if it isn't a regular file, the link
    dangles, the chain is too long, or a target that debugfs stores outside
    the inode (a "slow" symlink, i.e. one over 59 bytes) is encountered.
    """
    current = target_path
    for _ in range(max_hops):
        stat_output = _debugfs_stat(image, current)
        match = _DEBUGFS_STAT_TYPE_RE.search(stat_output)
        if match is None:
            return None
        if match.group(1) == "regular":
            return current
        if match.group(1) != "symlink":
            return None
        dest = _DEBUGFS_FAST_LINK_RE.search(stat_output)
        if dest is None:
            return None
        current = posixpath.normpath(
            posixpath.join(posixpath.dirname(current), dest.group(1))
        )
    return None


def debugfs_is_regular_file(image: Path, target_path: str) -> bool:
    """Check whether a path inside an ext image resolves to a regular file."""
    return _debugfs_resolve_symlinks(image, target_path) is not None


def _debugfs_unescape(name: str) -> str:
    r"""Undo the `\xNN` escaping debugfs applies to names it can't print."""
    unescaped = _DEBUGFS_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), name)
    # Each escape stood for one byte, so the escaped bytes have to be
    # reassembled before they can be decoded as (multi-byte) UTF-8.
    return unescaped.encode("latin-1", "backslashreplace").decode("utf-8", "replace")


def debugfs_list_dir(image: Path, target_dir: str) -> list[str]:
    """List file names directly under target_dir inside an ext image.

    :raises errors.GRUBInstallError: If target_dir doesn't exist.
    """
    output = debugfs_run(image, [f"ls -l {_debugfs_quote(target_dir)}"])
    names: list[str] = []
    for line in output.splitlines():
        # Only accept well-formed rows; error text such as "File not found by
        # ext2_lookup" would otherwise be parsed as a file name.
        match = _DEBUGFS_LS_LINE_RE.match(line)
        if match is None:
            # Conversely, only lines that aren't entries can report an error,
            # so a file whose name contains "File not found" is listed fine.
            # The echoed request carries the caller's path, so skip it too.
            if line.startswith(_DEBUGFS_ECHO_PREFIX):
                continue
            if any(marker in line for marker in _DEBUGFS_NOT_FOUND_MARKERS):
                raise errors.GRUBInstallError(
                    f"No such directory {target_dir} in {image}"
                )
            if _DEBUGFS_NOT_A_DIRECTORY_MARKER in line:
                raise errors.GRUBInstallError(
                    f"{target_dir} in {image} is not a directory"
                )
            continue
        name = _debugfs_unescape(match.group("name").strip())
        if name in (".", ".."):
            continue
        names.append(name)
    return names


def _mtools_spec(imagepath: Path, offset_bytes: int) -> str:
    return f"{imagepath}@@{offset_bytes}"


def _mdir_ok(spec: str, path: str) -> bool:
    return (
        subprocess.run(
            ["mdir", "-i", spec, f"::{path}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode
        == 0
    )


def _is_fat_dir(spec: str, path: str) -> bool:
    # mdir lists the *parent* when given a file, and so succeeds either way;
    # a trailing slash makes it reject anything that isn't a directory.
    return _mdir_ok(spec, f"{path}/")


def mcopy_in(
    imagepath: Path, offset_bytes: int, local_path: Path, target_path: str
) -> None:
    """Copy a local file into a FAT partition embedded in imagepath.

    No mount or loop device is used: mtools reads/writes the FAT filesystem
    directly at the given byte offset within the disk image.
    """
    mmd_p(imagepath, offset_bytes, str(Path(target_path).parent))
    spec = _mtools_spec(imagepath, offset_bytes)
    # mcopy treats an existing directory at target_path as a destination
    # *directory* and silently copies the source in under its own basename.
    if _is_fat_dir(spec, target_path):
        raise errors.GRUBInstallError(
            f"mcopy cannot write {target_path}: it is a directory"
        )
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
        # mmd fails if the directory already exists; that's fine here, and
        # mtools reports it the same way as a genuine failure, so the result
        # is checked below instead.
        subprocess.run(
            ["mmd", "-i", spec, f"::{current}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    if not _is_fat_dir(spec, current):
        raise errors.GRUBInstallError(
            f"mmd failed creating {target_dir} in {imagepath}"
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
