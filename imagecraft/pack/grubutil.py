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
from craft_parts.filesystem_mounts import FilesystemMount
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models.volume import StructureList
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
        emit.progress(
            "Skipping GRUB installation because grub-install is not available",
            permanent=True,
        )
        return

    try:
        for cmd in [
            grub_install_command,
            divert_os_prober_command,
            update_grub_command,
            undivert_os_prober_command,
        ]:
            res = run(*cmd, stderr=subprocess.STDOUT)
            if res.stdout:
                emit.debug(res.stdout)
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError("Fail to install grub") from err
    except FileNotFoundError as err:
        raise errors.GRUBInstallError("Missing tool to install grub") from err


def setup_grub(
    image: Image, workdir: Path, arch: str, filesystem_mount: FilesystemMount
) -> None:
    """Setups GRUB in the image.

    :param image: Image object handling the actual disk file
    :param workdir: working directory
    :param arch: architecture the image is built for
    :param filesystem_mount: order in which partitions should be mounted

    """
    emit.progress("Setting up GRUB in the image")

    if not image.has_boot_partition:
        emit.progress(
            "Skipping GRUB installation because no boot partition was found",
            permanent=True,
        )
        return
    if not image.has_data_partition:
        emit.progress(
            "Skipping GRUB installation because no data partition was found",
            permanent=True,
        )
        return

    if arch not in _ARCH_TO_GRUB_EFI_TARGET:
        emit.progress("Cannot install GRUB on this architecture", permanent=True)
        return

    mount_dir = workdir / "mount"
    mount_dir.mkdir(exist_ok=True)

    with image.attach_loopdev() as loop_dev:
        mounts: list[Mount] = [
            *_image_mounts(loop_dev, image.volume.structure, filesystem_mount),
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
            Mount(
                fstype=None, src="/run", relative_mountpoint="/run", options=["--bind"]
            ),
        ]
        chroot = Chroot(path=mount_dir, mounts=mounts)

        try:
            chroot.execute(
                target=_grub_install,
                grub_target=_ARCH_TO_GRUB_EFI_TARGET[arch],
                loop_dev=loop_dev,
            )
        except errors.ChrootMountError as err:
            # Ignore mounting errors indicating the rootfs does not have
            # the needed structure to install grub.
            emit.progress(f"Cannot install GRUB on this rootfs: {err}", permanent=True)


def _image_mounts(
    loop_dev: str, structure: StructureList, filesystem_mount: FilesystemMount
) -> list[Mount]:
    """Generate a list of mounts for the structure, based on the given filesystem_mount.

    :param loop_dev: loop device the disk is associated to
    :param structure: StructureList describing the partition layout of the image
    :param filesystem_mount: order in which partitions should be mounted
    """
    image_mounts: list[Mount] = []

    for entry in filesystem_mount:
        partition_name = _partition_name_from_device(entry.device)
        partnum = _part_num(partition_name, structure)
        if partnum is None:
            raise errors.ImageError(
                message=f"Cannot find a partition named {partition_name}"
            )
        image_mounts.append(
            Mount(
                fstype=None,
                src=f"{loop_dev}p{partnum}",
                relative_mountpoint=entry.mount,
            )
        )
    return image_mounts


def _part_num(name: str, structure: StructureList) -> int | None:
    """Get the partition number for a given name based on its position."""
    for i, structure_item in enumerate(structure):
        if structure_item.name == name:
            if structure_item.partition_number is None:
                # Partition numbers start at 1, so offset the index
                return i + 1
            return structure_item.partition_number
    return None


def _partition_name_from_device(device: str) -> str:
    """Extract the partition name from the device name.

    Works under the assumption that the full device name references
    the correct volume and the device name follows the
    (volume/<volume_name>/<structure_name>) syntax.

    """
    return device.strip("()").split("/")[-1]
