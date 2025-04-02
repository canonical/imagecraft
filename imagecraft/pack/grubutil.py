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
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.pack.chroot import Chroot, Mount
from imagecraft.pack.image import Image
from imagecraft.subprocesses import run

_ARCH_TO_GRUB_EFI_TARGET: dict[str, str] = {
    DebianArchitecture.AMD64: "x86_64-efi",
    DebianArchitecture.ARM64: "arm64-efi",
    DebianArchitecture.ARMHF: "arm-efi",
}


def _grub_install(grub_target: str, loop_dev: str) -> None:
    """Install grub in the image.

    :param grub_target: target platform to install grub for.
    :param loop_dev: loop device to install grub on
    """
    check_grub_install = ["grub-install", "-V"]
    grub_install_command = [
        "grub-install",
        loop_dev,
        "--boot-directory=/boot",
        "--efi-directory=/boot/efi",
        f"--target={grub_target}",
        "--uefi-secure-boot",
        "--no-nvram",
    ]

    update_grub_command = [
        "update-grub",
    ]

    # Divert os-probe to avoid writing wrong output in grub.cfg
    os_prober = "/etc/grub.d/30_os-prober"
    divert_base_command = "dpkg-divert"

    divert_common_args = [
        "--local",
        "--divert",
        os_prober + ".dpkg-divert",
        "--rename",
        os_prober,
    ]

    divert_os_prober_command = [divert_base_command, *list(divert_common_args)]

    undivert_os_prober_command = [
        divert_base_command,
        "--remove",
        *divert_common_args,
    ]

    # Check if grub-install is available, otherwise skip the installation without error
    try:
        run(*check_grub_install)
    except FileNotFoundError:
        emit.message("Skipping GRUB installation because grub-install is not available")
        return

    try:
        run(*grub_install_command)
        run(*divert_os_prober_command)
        run(*update_grub_command)
        run(*undivert_os_prober_command)
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError("Fail to install grub") from err
    except FileNotFoundError as err:
        raise errors.GRUBInstallError("Missing tool to install grub") from err


def setup_grub(image: Image, workdir: Path, arch: str) -> None:
    """Setups GRUB in the image.

    :param image: Image object handling the actual disk file
    :param workdir: working directory
    :param arch: architecture the image is built for

    """
    rootfs_partition_num = image.data_partition_number
    boot_partition_num = image.boot_partition_number

    if boot_partition_num is None:
        emit.message("Skipping GRUB installation because no boot partition was found")
        return
    if rootfs_partition_num is None:
        emit.message("Skipping GRUB installation because data partition was found")
        return

    if arch not in _ARCH_TO_GRUB_EFI_TARGET:
        emit.message("Cannot install GRUB on this architecture")
        return

    mount_dir = workdir / "mount"
    mount_dir.mkdir(exist_ok=True)

    loop_dev = image.attach_loopdev()

    mounts: list[Mount] = [
        Mount(
            fstype=None,
            src=f"{loop_dev}p{rootfs_partition_num}",
            relative_mountpoint="/",
        ),
        Mount(
            fstype=None,
            src=f"{loop_dev}p{boot_partition_num}",
            relative_mountpoint="/boot/efi",
        ),
        Mount(
            fstype="devtmpfs",
            src="devtmpfs-build",
            relative_mountpoint="/dev",
        ),
        Mount(
            fstype="devpts",
            src="devpts-build",
            relative_mountpoint="/dev/pts",
            options=["-o", "nodev,nosuid"],
        ),
        Mount(fstype="proc", src="proc-build", relative_mountpoint="proc"),
        Mount(fstype="sysfs", src="sysfs-build", relative_mountpoint="/sys"),
        Mount(fstype=None, src="/run", relative_mountpoint="/run", options=["--bind"]),
    ]
    chroot = Chroot(path=mount_dir, mounts=mounts)

    try:
        chroot.execute(
            target=_grub_install,
            grub_target=_ARCH_TO_GRUB_EFI_TARGET[arch],
            loop_dev=loop_dev,
        )
    finally:
        image.detach_loopdevs()
