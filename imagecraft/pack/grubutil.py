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

"""GRUB utils."""

import subprocess
from pathlib import Path

from craft_cli import emit

from imagecraft import errors
from imagecraft.pack import Image, LinuxChroot
from imagecraft.subprocesses import run

_ARCH_TO_GRUB_EFI_TARGET: dict[str, str] = {
    "amd64": "x86_64-efi",
    "arm64": "arm64-efi",
    "armhf": "arm-efi",
}


def _grub_install(grub_target: str, loop_used: str) -> None:
    grub_command = [
        "grub-install",
        loop_used,
        "--boot-directory=/boot",
        "--efi-directory=/boot/efi",
        f"--target={grub_target}",
        "--uefi-secure-boot",
        "--no-nvram",
    ]

    try:
        run(grub_command)
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError from err


def setup_grub(image: Image, workdir: Path, arch: str) -> None:
    """Setups grub in the image."""
    rootfs_partition_num = image.data_partition_number()
    boot_partition_num = image.boot_partition_number()

    if boot_partition_num is None:
        emit.debug("Cannot install grub without a boot partition")
        return
    if rootfs_partition_num is None:
        emit.debug("Cannot install grub without a data partition")
        return

    if arch not in _ARCH_TO_GRUB_EFI_TARGET:
        emit.debug("Cannot install grub on this architecture")
        return

    mount_dir = workdir / "mount"

    mount_dir.mkdir(exist_ok=True)

    image.attach_loopdev()

    try:
        # mount partitions in mount_dir
        # prepare specific Mount list

        chroot = LinuxChroot(path=mount_dir)
        chroot.chroot(target=_grub_install, grub_target=_ARCH_TO_GRUB_EFI_TARGET[arch])

        # - divert osprober
        # - execute update-grub
        # - umount rootfs/efi
    finally:
        image.detach_loopdevs()
