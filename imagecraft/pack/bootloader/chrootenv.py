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

CHROOT_IMAGE_DEVICE = "/dev/image"
"""In-chroot path under which the raw disk image is exposed."""

# Restricted PATH for in-chroot commands, so host-specific PATH entries
# don't leak into the guest environment.
_CHROOT_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"


def find_chroot_binary(root_dir: Path, name: str) -> str:
    """Locate a tool binary in the guest rootfs.

    :param root_dir: Prime directory of the root filesystem partition.
    :param name: Binary name (e.g. ``grub-mkimage``).
    :return: The binary's absolute path *inside* the chroot.
    :raises errors.BootloaderToolsMissingError: If the binary isn't present
        in the staged rootfs.
    """
    for prefix in ("/usr/sbin", "/usr/bin", "/sbin", "/bin"):
        candidate = f"{prefix}/{name}"
        if (root_dir / candidate.lstrip("/")).is_file():
            return candidate
    raise errors.BootloaderToolsMissingError(
        f"{name} not found in the staged rootfs",
        resolution="Install the relevant GRUB packages in the image.",
    )


def run_checked(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a command inside the chroot, wrapping failures.

    :return: The completed process (output captured).
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
    image_path: Path | None = None,
    boot_dir: Path | None = None,
    host_dev: bool = False,
    extra_mounts: list[Mount] | None = None,
) -> Chroot:
    """Build a chroot rooted at the root partition's prime directory.

    :param root_dir: Prime directory of the root filesystem partition.
    :param image_path: If given, the raw disk image is bind-mounted at
        :data:`CHROOT_IMAGE_DEVICE` in the chroot.
    :param boot_dir: Prime directory of a dedicated ``/boot`` partition,
        bound at ``/boot`` in the chroot. Defaults to the root partition's
        own ``/boot`` when not given.
    :param host_dev: Bind-mount the host's ``/dev`` instead of only the few
        device files GRUB needs. Incompatible with ``image_path`` since the
        overmount would hide the bind target. (A real devtmpfs mount is
        preferable but is blocked in unprivileged containers.)
    :param extra_mounts: Additional mounts to set up inside the chroot
        (e.g. tool shims bind-mounted over the guest's binaries).
    """
    if host_dev and image_path is not None:
        raise ValueError("host /dev overmounts /dev, hiding the /dev/image bind target")

    for mountpoint in ("proc", "sys", "dev", "tmp"):
        (root_dir / mountpoint).mkdir(parents=True, exist_ok=True)

    mounts = [
        Mount(fstype="proc", src="proc-build", relative_mountpoint="/proc"),
        Mount(fstype="sysfs", src="sysfs-build", relative_mountpoint="/sys"),
    ]
    if host_dev:
        mounts.append(
            Mount(
                fstype=None, src="/dev", relative_mountpoint="/dev", options=["--bind"]
            )
        )
    else:
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
        if image_path is not None:
            (root_dir / "dev" / "image").touch(exist_ok=True)
            mounts.append(
                Mount(
                    fstype=None,
                    src=str(image_path.resolve()),
                    relative_mountpoint=CHROOT_IMAGE_DEVICE,
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
