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

import subprocess
from pathlib import Path

from imagecraft import errors
from imagecraft.subprocesses import run

_CHROOT_SEARCH_DIRS = ("usr/sbin", "usr/bin", "sbin", "bin")

# Restricted PATH for in-chroot commands, so host-specific PATH entries
# don't leak into the guest environment.
_CHROOT_PATH = ":".join(f"/{d}" for d in _CHROOT_SEARCH_DIRS)


def require_chroot_binary(root_dir: Path, name: str) -> Path:
    """Ensure a tool binary exists in the guest rootfs (on the chroot PATH).

    :return: The binary's path relative to the rootfs.
    :raises errors.BootloaderToolsMissingError: If the binary isn't present
        in the staged rootfs.
    """
    for prefix in _CHROOT_SEARCH_DIRS:
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
