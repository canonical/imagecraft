# Copyright 2026 Canonical Ltd.
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

"""Filesystem utilities for resilient copying and boot file discovery."""

import contextlib
import shutil
from pathlib import Path


def resilient_copy(src: Path, dst: Path, *, follow_symlinks: bool = True) -> Path:
    """Copy a file, falling back to a plain copy if metadata cannot be preserved.

    Prime directories are sometimes backed by filesystems (e.g. FUSE-mounted
    FAT) that don't support all the metadata operations ``shutil.copy2``
    attempts (permissions, timestamps). This first tries ``shutil.copy2``,
    then falls back to ``shutil.copyfile`` on ``OSError``.

    :param src: Source file path.
    :param dst: Destination file or directory path.
    :param follow_symlinks: Whether to follow symlinks.
    :return: The destination file path.
    """
    target = dst / src.name if dst.is_dir() else dst
    try:
        shutil.copy2(src, target, follow_symlinks=follow_symlinks)
    except OSError:
        shutil.copyfile(src, target, follow_symlinks=follow_symlinks)
    return target


def safe_copytree(
    src: Path,
    dst: Path,
    *,
    dirs_exist_ok: bool = True,
    symlinks: bool = False,
) -> Path:
    """Recursively copy a directory tree using :func:`resilient_copy` for each file.

    Tolerates directory metadata (``copystat``) failures, which can happen
    when copying into filesystems with limited metadata support.

    :param src: Source directory path.
    :param dst: Destination directory path.
    :param dirs_exist_ok: Whether it's fine for dst to already exist.
    :param symlinks: Whether to preserve symlinks instead of following them.
    :return: The destination directory path.
    """
    if not src.is_dir():
        raise NotADirectoryError(f"Source directory not found: {src}")

    dst.mkdir(parents=True, exist_ok=dirs_exist_ok)

    for entry in src.iterdir():
        target = dst / entry.name
        if entry.is_dir():
            safe_copytree(entry, target, dirs_exist_ok=dirs_exist_ok, symlinks=symlinks)
        else:
            resilient_copy(entry, target, follow_symlinks=not symlinks)

    with contextlib.suppress(OSError):
        shutil.copystat(src, dst)

    return dst
