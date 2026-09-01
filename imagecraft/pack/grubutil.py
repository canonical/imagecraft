# Copyright 2025-2026 Canonical Ltd.
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

"""GRUB utilities.

Coordinates GRUB installation for disk images:
- EFI (GPT/hybrid) images are handled directly via :mod:`imagecraft.pack.efi`.
- Legacy BIOS/MBR images are installed through a loop device and chroot.
"""

import pathlib
import subprocess
from collections.abc import Callable

from craft_cli import emit
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models import volume
from imagecraft.pack import chroot
from imagecraft.pack.efi import (
    _ARCH_TO_GRUB_EFI_TARGET,
    _EFI_CORE_MODULES,
    _SIGNED_SHIM_SUFFIXES,
    _discover_grub_target,
    _dump_signed_efi_binaries,
    _efi_filenames,
    _find_structure_item,
    _is_efi_partition,
    _part_num,
    _partition_offset_size,
    _read_ext_uuid,
    _resolve_core_modules,
    _run_update_grub,
    _setup_grub_efi,
    _unsigned_shim_name,
)
from imagecraft.pack.image import Image
from imagecraft.subprocesses import run

__all__ = [
    "_ARCH_TO_GRUB_EFI_TARGET",
    "_EFI_CORE_MODULES",
    "_SIGNED_SHIM_SUFFIXES",
    "_discover_grub_target",
    "_dump_signed_efi_binaries",
    "_efi_filenames",
    "_find_structure_item",
    "_is_efi_partition",
    "_part_num",
    "_partition_offset_size",
    "_read_ext_uuid",
    "_resolve_core_modules",
    "_run_update_grub",
    "_setup_grub_bios_chroot",
    "_setup_grub_efi",
    "_unsigned_shim_name",
    "setup_grub",
]

_GRUB_BIOS_TARGET = "i386-pc"
_GRUB_BIOS_ARCHS = {DebianArchitecture.AMD64, DebianArchitecture.I386}

_ROLE_MOUNT_PAIRS: list[tuple[Callable[[volume.StructureItem], bool], str]] = [
    (lambda s: s.role == volume.Role.SYSTEM_DATA, "/"),
    (lambda s: s.role == volume.Role.SYSTEM_BOOT and not _is_efi_partition(s), "/boot"),
]


def setup_grub(
    image: Image,
    workdir: pathlib.Path,
    arch: str,
) -> None:
    """Set up GRUB directly on the disk image.

    :param image: Image object handling the actual disk file
    :param workdir: working directory
    :param arch: architecture the image is built for
    """
    emit.progress("Setting up GRUB in the image")

    if not image.has_data_partition:
        emit.progress(
            "Skipping GRUB installation because no data partition was found",
        )
        return

    if image.volume.volume_schema == volume.PartitionSchema.MBR:
        if arch not in _GRUB_BIOS_ARCHS:
            emit.progress("Cannot install GRUB on this architecture", permanent=True)
            return
        # Legacy BIOS/MBR images are still installed through a loop device
        # and a chroot. They move over to direct image manipulation in a
        # follow-up change, once the EFI path has settled.
        _setup_grub_bios_chroot(image, workdir, _GRUB_BIOS_TARGET)
        return

    # GPT or hybrid — EFI boot
    if not image.has_boot_partition:
        emit.progress(
            "Skipping GRUB installation because no boot partition was found",
        )
        return
    if arch not in _ARCH_TO_GRUB_EFI_TARGET:
        emit.progress("Cannot install GRUB on this architecture", permanent=True)
        return
    grub_target = _ARCH_TO_GRUB_EFI_TARGET[arch]

    try:
        _setup_grub_efi(image, grub_target)
    except errors.ImageError as err:
        emit.progress(f"Cannot install GRUB on this rootfs: {err}", permanent=True)


def _setup_grub_bios_chroot(
    image: Image,
    workdir: pathlib.Path,
    grub_target: str,
) -> None:
    """Install GRUB for a legacy BIOS/MBR image via a loop device and chroot.

    This is the original, privileged installation path. It is retained only
    for BIOS/MBR images until they are converted to direct disk image
    manipulation, at which point this and its helpers are removed.
    """
    structure = image.volume.structure
    mount_dir = workdir / "mount"
    mount_dir.mkdir(exist_ok=True)

    with image.attach_loopdev() as loop_dev:
        image_mounts = []
        for predicate, mountpoint in _ROLE_MOUNT_PAIRS:
            try:
                item = _find_structure_item(structure, predicate)
            except errors.ImageError:
                continue
            partnum = _part_num(item.name, structure)
            if partnum is None:
                raise errors.ImageError(
                    message=f"Cannot find a partition named {item.name}"
                )
            image_mounts.append(
                chroot.Mount(
                    fstype=None,
                    src=f"{loop_dev}p{partnum}",
                    relative_mountpoint=mountpoint,
                )
            )
        # EFI system partition (GPT only) is mounted at /boot/efi.
        if any(_is_efi_partition(s) for s in structure):
            item = _find_structure_item(structure, _is_efi_partition)
            partnum = _part_num(item.name, structure)
            image_mounts.append(
                chroot.Mount(
                    fstype=None,
                    src=f"{loop_dev}p{partnum}",
                    relative_mountpoint="/boot/efi",
                )
            )
        mounts: list[chroot.Mount] = [
            *image_mounts,
            chroot.Mount(
                fstype="devtmpfs",
                src="devtmpfs-build",
                relative_mountpoint="/dev",
            ),
            chroot.Mount(
                fstype="devpts",
                src="devpts-build",
                relative_mountpoint="/dev/pts",
                options=["-o", "nodev,nosuid"],
            ),
            chroot.Mount(fstype="proc", src="proc-build", relative_mountpoint="proc"),
            chroot.Mount(fstype="sysfs", src="sysfs-build", relative_mountpoint="/sys"),
            chroot.Mount(
                fstype=None, src="/run", relative_mountpoint="/run", options=["--bind"]
            ),
        ]
        chroot_obj = chroot.Chroot(path=mount_dir, mounts=mounts)

        try:
            chroot_obj.execute(
                target=_grub_install,
                grub_target=grub_target,
                loop_dev=loop_dev,
            )
        except errors.ChrootMountError as err:
            # Ignore mounting errors indicating the rootfs does not have
            # the needed structure to install grub.
            emit.progress(f"Cannot install GRUB on this rootfs: {err}", permanent=True)


def _grub_install(grub_target: str, loop_dev: str) -> None:
    """Install grub in the image.

    :param grub_target: target platform to install grub for.
    :param loop_dev: loop device to install grub on
    """
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
        ]

    # Divert os-prober to avoid writing wrong output in grub.cfg
    os_prober = "/etc/grub.d/30_os-prober"
    divert_args = [
        "--local",
        "--divert",
        f"{os_prober}.dpkg-divert",
        "--rename",
        os_prober,
    ]
    commands = [
        grub_install_command,
        ["dpkg-divert", *divert_args],
        ["update-grub"],
        ["dpkg-divert", "--remove", *divert_args],
    ]

    # Check if grub-install is available, otherwise skip the installation without error
    try:
        run("grub-install", "-V")
    except FileNotFoundError:
        emit.progress(
            "Skipping GRUB installation because grub-install is not available",
            permanent=True,
        )
        return

    try:
        for cmd in commands:
            res = run(*cmd, stderr=subprocess.STDOUT)
            if res.stdout:
                emit.debug(res.stdout)
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError("Fail to install grub") from err
    except FileNotFoundError as err:
        raise errors.GRUBInstallError("Missing tool to install grub") from err
