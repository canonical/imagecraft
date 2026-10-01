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

"""Shared helpers for staging GRUB assets into boot prime directories."""

import shutil
from pathlib import Path

from imagecraft import errors


def stage_grub_modules(root_dir: Path, boot_dir: Path | None, grub_format: str) -> None:
    """Stage GRUB runtime modules into the ``/boot`` prime directory.

    Must be called *before* the partitions are formatted, since it writes
    into a prime directory that ``diskutil.format_device`` will later embed
    via ``mke2fs -d``.

    :param root_dir: Prime directory of the root filesystem partition (used
        to locate the rootfs's installed GRUB modules).
    :param boot_dir: Prime directory that corresponds to ``/boot``. Defaults
        to ``root_dir / "boot"`` when ``/boot`` isn't a dedicated partition.
    :param grub_format: GRUB target format (e.g. ``i386-pc``, ``x86_64-efi``).
    :raises errors.BootloaderToolsMissingError: If the GRUB modules directory
        isn't present in the staged rootfs.
    """
    mod_dir = root_dir / "usr" / "lib" / "grub" / grub_format
    if not mod_dir.is_dir():
        raise errors.BootloaderToolsMissingError(
            f"GRUB modules directory not found: {mod_dir}"
        )
    target_boot = boot_dir or root_dir / "boot"
    shutil.copytree(
        mod_dir,
        target_boot / "grub" / grub_format,
        dirs_exist_ok=True,
    )
    font_src = root_dir / "usr" / "share" / "grub" / "unicode.pf2"
    if font_src.is_file():
        target_font_dir = target_boot / "grub" / "fonts"
        target_font_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(font_src, target_font_dir / "unicode.pf2")
