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

import shutil
import subprocess
from pathlib import Path

from craft_cli import emit
from craft_parts.filesystem_mounts import FilesystemMount
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models.volume import (
    MBRStructureItem,
    PartitionSchema,
    StructureList,
)
from imagecraft.pack import mbrutil
from imagecraft.pack.chroot import Chroot, Mount
from imagecraft.pack.image import Image
from imagecraft.subprocesses import run

_ARCH_TO_GRUB_EFI_TARGET: dict[str, str] = {
    DebianArchitecture.AMD64: "x86_64-efi",
    DebianArchitecture.ARM64: "arm64-efi",
    DebianArchitecture.ARMHF: "arm-efi",
}

_GRUB_BIOS_TARGET = "i386-pc"
_GRUB_BIOS_ARCHS = {DebianArchitecture.AMD64, DebianArchitecture.I386}

# Maps grub EFI target → (grub binary name under /EFI/<id>/, fallback sibling name)
_EFI_TARGET_TO_FILENAMES: dict[str, tuple[str, str]] = {
    "x86_64-efi": ("grubx64.efi", "grubx64.efi"),
    "arm64-efi": ("grubaa64.efi", "grubaa64.efi"),
    "arm-efi": ("grubarm.efi", "grubarm.efi"),
}


def _grub_install(grub_target: str, loop_dev: str) -> None:
    """Install grub in the image.

    :param grub_target: target platform to install grub for.
    :param loop_dev: loop device to install grub on
    """
    check_grub_install = ["grub-install", "-V"]
    if grub_target == _GRUB_BIOS_TARGET:
        grub_install_command = [
            "grub-install",
            "--boot-directory=/boot",
            f"--target={grub_target}",
            loop_dev,
        ]
    else:
        grub_install_command = [
            "grub-install",
            loop_dev,
            "--boot-directory=/boot",
            "--efi-directory=/boot/efi",
            f"--target={grub_target}",
            "--uefi-secure-boot",
            "--no-nvram",
            # Ubuntu's signed grub binary has /EFI/ubuntu compiled in as its
            # $prefix, so the config and modules must live there.
            "--bootloader-id=ubuntu",
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

    _populate_uefi_fallback(grub_target)


def _extract_root_uuid(grub_cfg_src: Path) -> str:
    """Extract rootfs UUID from a search.fs_uuid line in a GRUB config file."""
    for line in grub_cfg_src.read_text(encoding="utf-8").splitlines():
        if line.startswith("search.fs_uuid "):
            parts = line.split()
            if len(parts) > 1:
                return parts[1]
    return ""


def _populate_uefi_fallback(grub_target: str) -> None:
    """Populate UEFI fallback path with grub + config next to BOOT*.EFI.

    We intentionally keep BOOT*.EFI as shim and provide grubx64.efi/grub.cfg
    in the same directory, which is the location shim looks at first.
    """
    if grub_target not in _EFI_TARGET_TO_FILENAMES:
        return

    grub_fname, fallback_grub_fname = _EFI_TARGET_TO_FILENAMES[grub_target]
    efi_dir = Path("/boot/efi/EFI")
    grub_src = efi_dir / "ubuntu" / grub_fname
    grub_cfg_src = efi_dir / "ubuntu" / "grub.cfg"
    boot_grub = efi_dir / "BOOT" / fallback_grub_fname
    boot_cfg = efi_dir / "BOOT" / "grub.cfg"

    if not (grub_src.exists() and grub_cfg_src.exists()):
        return

    boot_grub.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(grub_src, boot_grub)
    root_uuid = _extract_root_uuid(grub_cfg_src)
    if root_uuid:
        # In this path grub may start in command mode; `normal` enters
        # menu mode and evaluates /boot/grub/grub.cfg from the rootfs.
        stub = "\n".join(
            [
                f"search.fs_uuid {root_uuid} root",
                "set prefix=($root)'/boot/grub'",
                "normal",
            ]
        )
        boot_cfg.write_text(stub + "\n", encoding="utf-8")
        grub_cfg_src.write_text(stub + "\n", encoding="utf-8")
    else:
        shutil.copy2(grub_cfg_src, boot_cfg)


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

    if not image.has_data_partition:
        emit.progress(
            "Skipping GRUB installation because no data partition was found",
            permanent=True,
        )
        return

    schema = image.volume.volume_schema
    if schema == PartitionSchema.MBR:
        if arch not in _GRUB_BIOS_ARCHS:
            emit.progress("Cannot install GRUB on this architecture", permanent=True)
            return
        grub_target = _GRUB_BIOS_TARGET
    else:  # GPT or hybrid — EFI boot
        if not image.has_boot_partition:
            emit.progress(
                "Skipping GRUB installation because no boot partition was found",
                permanent=True,
            )
            return
        if arch not in _ARCH_TO_GRUB_EFI_TARGET:
            emit.progress("Cannot install GRUB on this architecture", permanent=True)
            return
        grub_target = _ARCH_TO_GRUB_EFI_TARGET[arch]

    mount_dir = workdir / "mount"
    mount_dir.mkdir(exist_ok=True)

    with image.attach_loopdev() as loop_dev:
        mounts: list[Mount] = [
            *_image_mounts(loop_dev, image.volume.structure, filesystem_mount),
            # Use a recursive bind of the host's /dev so that loop devices
            # created by losetup (e.g. /dev/loop5) are visible inside the
            # chroot.  A fresh devtmpfs would not contain them, causing
            # grub-install to fail silently when it cannot access the disk.
            Mount(
                fstype=None,
                src="/dev",
                relative_mountpoint="/dev",
                options=["--rbind"],
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
                grub_target=grub_target,
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
    """Get the partition number for a given name based on its position.

    For MBR volumes with extended partitions (>4 entries), logical partitions
    start at 5 because slot 4 is reserved for the synthesised extended container.
    """
    needs_extended = len(structure) > mbrutil.MAX_PRIMARY_SLOTS and isinstance(
        structure[0], MBRStructureItem
    )
    for i, structure_item in enumerate(structure):
        if structure_item.name == name:
            explicit = getattr(structure_item, "partition_number", None)
            if explicit is not None:
                return explicit
            pos = i + 1  # 1-based
            if needs_extended and pos > mbrutil.PRIMARY_SLOTS_WITH_EXTENDED:
                return pos + 1  # skip slot 4 (extended container)
            return pos
    return None


def _partition_name_from_device(device: str) -> str:
    """Extract the partition name from the device name.

    Works under the assumption that the full device name references
    the correct volume and the device name follows the
    (volume/<volume_name>/<structure_name>) syntax.

    """
    return device.strip("()").split("/")[-1]
