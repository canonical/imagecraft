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

"""Shared helpers for running GRUB tooling in a prime-directory chroot."""

import shutil
import subprocess
from pathlib import Path

from imagecraft import errors
from imagecraft.subprocesses import run

# Restricted PATH for in-chroot commands, so host-specific PATH entries
# don't leak into the guest environment.
_CHROOT_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"


def require_chroot_binary(root_dir: Path, name: str) -> Path:
    """Ensure a tool binary exists in the guest rootfs (on the chroot PATH).

    :return: The binary's path relative to the rootfs.
    :raises errors.BootloaderToolsMissingError: If the binary isn't present
        in the staged rootfs.
    """
    for prefix in ("usr/sbin", "usr/bin", "sbin", "bin"):
        candidate = Path(prefix) / name
        if (root_dir / candidate).is_file():
            return candidate
    raise errors.BootloaderToolsMissingError(
        f"{name} not found in the staged rootfs",
        resolution="Install the relevant GRUB packages in the image.",
    )


def run_checked(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command with a restricted PATH, capturing output.

    :raises errors.BootloaderError: If the command exits non-zero.
    """
    try:
        return run(cmd[0], *cmd[1:], env={"PATH": _CHROOT_PATH})
    except subprocess.CalledProcessError as err:
        raise errors.BootloaderError(
            f"Command {' '.join(cmd)!r} failed: "
            f"{err.stderr.strip() or err.stdout.strip()}"
        ) from err


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
    effective_boot_dir = boot_dir if boot_dir is not None else root_dir / "boot"
    shutil.copytree(
        mod_dir, effective_boot_dir / "grub" / grub_format, dirs_exist_ok=True
    )
