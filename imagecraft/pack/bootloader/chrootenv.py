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
from imagecraft.pack.chroot import Chroot, Mount

# Restricted PATH for in-chroot commands, so host-specific PATH entries
# don't leak into the guest environment.
_CHROOT_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"


def require_chroot_binary(root_dir: Path, name: str) -> None:
    """Ensure a tool binary exists in the guest rootfs (on the chroot PATH).

    :raises errors.BootloaderToolsMissingError: If the binary isn't present
        in the staged rootfs.
    """
    for prefix in ("usr/sbin", "usr/bin", "sbin", "bin"):
        if (root_dir / prefix / name).is_file():
            return
    raise errors.BootloaderToolsMissingError(
        f"{name} not found in the staged rootfs",
        resolution="Install the relevant GRUB packages in the image.",
    )


def run_checked(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command, capturing output and wrapping failures.

    :raises errors.BootloaderError: If the command exits non-zero.
    """
    try:
        return subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            env={"PATH": _CHROOT_PATH},
        )
    except subprocess.CalledProcessError as err:
        raise errors.BootloaderError(
            f"Command {' '.join(cmd)!r} failed in chroot: "
            f"{err.stderr.strip() or err.stdout.strip()}"
        ) from err


def build_prime_chroot(
    root_dir: Path,
    *,
    boot_dir: Path | None = None,
    extra_mounts: list[Mount] | None = None,
) -> Chroot:
    """Build a chroot rooted at the root partition's prime directory.

    Only the device files GRUB needs are bind-mounted (rather than
    overmounting ``/dev``, which would hide the bind targets).

    :param root_dir: Prime directory of the root filesystem partition.
    :param boot_dir: Prime directory of a dedicated ``/boot`` partition,
        bound at ``/boot`` in the chroot. Defaults to the root partition's
        own ``/boot`` when not given.
    :param extra_mounts: Additional mounts to set up inside the chroot
        (e.g. tool shims bind-mounted over the guest's binaries).
    """
    for mountpoint in ("proc", "sys", "dev", "tmp"):
        (root_dir / mountpoint).mkdir(parents=True, exist_ok=True)

    mounts = [
        Mount(fstype="proc", src="proc-build", relative_mountpoint="/proc"),
        Mount(fstype="sysfs", src="sysfs-build", relative_mountpoint="/sys"),
    ]
    for device in ("null", "zero", "urandom"):
        (root_dir / "dev" / device).touch(exist_ok=True)
        mounts.append(
            Mount(
                fstype=None,
                src=f"/dev/{device}",
                relative_mountpoint=f"/dev/{device}",
                options=["--bind"],
            )
        )
    if boot_dir is not None:
        (root_dir / "boot").mkdir(exist_ok=True)
        mounts.append(
            Mount(
                fstype=None,
                src=str(boot_dir.resolve()),
                relative_mountpoint="/boot",
                options=["--bind"],
            )
        )
    mounts.extend(extra_mounts or [])
    return Chroot(path=root_dir, mounts=mounts)
