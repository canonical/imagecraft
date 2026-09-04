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

import errno
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from craft_cli import emit
from craft_parts.filesystem_mounts import FilesystemMount
from craft_parts.utils import os_utils
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models.volume import (
    MBRStructureItem,
    PartitionSchema,
    StructureList,
)
from imagecraft.pack import gptutil, mbrutil
from imagecraft.pack.chroot import Chroot, Mount
from imagecraft.pack.image import Image
from imagecraft.subprocesses import run


def _copy_executable(src: Path, dst: Path) -> None:
    """Copy an executable without relying on extended filesystem metadata.

    FUSE-backed filesystems such as ``fusefat`` reject ``chmod`` and the
    extended metadata calls used by ``shutil.copy2``. Open the files directly
    and ignore mode changes the destination filesystem does not support.
    """
    dst.write_bytes(src.read_bytes())
    try:
        dst.chmod(src.stat().st_mode & 0o7777)
    except OSError as err:
        if err.errno != errno.ENOSYS:
            raise


if TYPE_CHECKING:
    from imagecraft.utils.mount import BaseMount

_ARCH_TO_GRUB_EFI_TARGET: dict[str, str] = {
    DebianArchitecture.AMD64: "x86_64-efi",
    DebianArchitecture.ARM64: "arm64-efi",
    DebianArchitecture.ARMHF: "arm-efi",
}

_GRUB_BIOS_TARGET = "i386-pc"
_GRUB_BIOS_ARCHS = {DebianArchitecture.AMD64, DebianArchitecture.I386}

# Modules embedded in the removable EFI image.
#
# Mapping from GRUB EFI targets to the corresponding signed shim/GRUB binary
# names and directory layout used by Ubuntu for Secure Boot.
_SIGNED_EFI_FILES: dict[str, dict[str, str]] = {
    "x86_64-efi": {
        "fallback_name": "BOOTX64.EFI",
        "grub_name": "grubx64.efi",
        "grub_signed_name": "grubx64.efi.signed",
        "shim_name": "shimx64.efi.signed",
        "mm_name": "mmx64.efi",
        "fb_name": "fbx64.efi",
        "shim_dir": "/usr/lib/shim",
        "grub_dir": "/usr/lib/grub/x86_64-efi-signed",
    },
    "arm64-efi": {
        "fallback_name": "BOOTAA64.EFI",
        "grub_name": "grubaa64.efi",
        "grub_signed_name": "grubaa64.efi.signed",
        "shim_name": "shimaa64.efi.signed",
        "mm_name": "mmaa64.efi",
        "fb_name": "fbaa64.efi",
        "shim_dir": "/usr/lib/shim",
        "grub_dir": "/usr/lib/grub/arm64-efi-signed",
    },
}


def _grub_install(
    grub_target: str,
    loop_dev: str,
    *,
    root_uuid: str | None = None,
) -> None:
    """Install grub in the image.

    :param grub_target: target platform to install grub for.
    :param loop_dev: loop device to install grub on
    :param root_uuid: UUID of the root filesystem, required for EFI boot.
    """
    if grub_target.endswith("-efi"):
        _install_grub_efi(grub_target, root_uuid=root_uuid)
    else:
        _install_grub_bios(grub_target, loop_dev)

    _update_grub(loop_dev)


def _install_grub_bios(grub_target: str, _loop_dev: str) -> None:
    """Install BIOS GRUB using grub-install.

    :param grub_target: target platform to install grub for.
    :param _loop_dev: loop device to install grub on
    """
    check_grub_install = ["grub-install", "-V"]
    grub_install_command = [
        "grub-install",
        "--boot-directory=/boot",
        f"--target={grub_target}",
        _loop_dev,
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
        res = run(*grub_install_command, stderr=subprocess.STDOUT)
        if res.stdout:
            emit.debug(res.stdout)
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError("Fail to install grub") from err
    except FileNotFoundError as err:
        raise errors.GRUBInstallError("Missing tool to install grub") from err


def _install_grub_efi(
    grub_target: str,
    *,
    root_uuid: str | None,
    base_path: Path = Path("/"),
) -> None:
    """Install the signed Ubuntu shim and GRUB binaries for UEFI Secure Boot.

    This assumes the chroot contains the distro-signed binaries.  The signed
    GRUB expects its configuration at ``/EFI/ubuntu/grub.cfg`` on the ESP, so a
    small chain-loading config is written there to locate the real
    ``/boot/grub/grub.cfg`` on the root filesystem.

    :param grub_target: target EFI platform (e.g. ``x86_64-efi``).
    :param root_uuid: UUID of the root filesystem, required to locate grub.cfg.
    :param base_path: base directory for the target rootfs (used mainly for
        testing); defaults to the real root.
    """
    if not root_uuid:
        raise errors.GRUBInstallError(
            "Cannot install EFI GRUB without a root filesystem UUID"
        )

    signed_files = _SIGNED_EFI_FILES.get(grub_target)
    if signed_files is None:
        raise errors.GRUBInstallError(
            f"No signed EFI configuration for target {grub_target}"
        )

    efi_boot_dir = base_path / "boot/efi" / "EFI" / "BOOT"
    efi_vendor_dir = base_path / "boot/efi" / "EFI" / "ubuntu"
    efi_boot_dir.mkdir(parents=True, exist_ok=True)
    efi_vendor_dir.mkdir(parents=True, exist_ok=True)

    shim_src = (
        base_path / signed_files["shim_dir"].lstrip("/") / signed_files["shim_name"]
    )
    grub_src = (
        base_path
        / signed_files["grub_dir"].lstrip("/")
        / signed_files["grub_signed_name"]
    )
    if not shim_src.exists() or not grub_src.exists():
        missing: list[str] = []
        if not shim_src.exists():
            missing.append("signed shim")
        if not grub_src.exists():
            missing.append("signed GRUB")
        raise errors.GRUBInstallError(
            f"Missing {', '.join(missing)} for {grub_target}. "
            "Install grub-efi-*-signed and shim-signed (or the platform-equivalent "
            "signed packages) for UEFI Secure Boot support."
        )

    _copy_executable(shim_src, efi_boot_dir / signed_files["fallback_name"])
    _copy_executable(grub_src, efi_vendor_dir / signed_files["grub_name"])
    (efi_vendor_dir / "grub.cfg").write_text(
        f"search.fs_uuid {root_uuid} root\nconfigfile ($root)/boot/grub/grub.cfg\n"
    )

    for helper in ("mm_name", "fb_name"):
        helper_src = (
            base_path / signed_files["shim_dir"].lstrip("/") / signed_files[helper]
        )
        if helper_src.exists():
            _copy_executable(helper_src, efi_vendor_dir / signed_files[helper])


def _restore_grub_probe(
    original_grub_probe: Path,
    grub_probe_path: Path,
    *,
    original_was_created: bool,
) -> None:
    """Restore the original grub-probe after running update-grub."""
    try:
        if original_was_created:
            shutil.copy2(str(original_grub_probe), str(grub_probe_path))
            original_grub_probe.unlink(missing_ok=True)
        else:
            grub_probe_path.unlink(missing_ok=True)
    except OSError as err:
        raise errors.GRUBInstallError("Failed to restore grub-probe") from err


def _run_update_grub_commands(
    grub_probe_stub: Path,
    grub_probe_path: Path,
    update_grub_command: list[str],
    divert_common_args: list[str],
) -> None:
    """Install the grub-probe stub and run update-grub."""
    try:
        shutil.copy2(str(grub_probe_stub), str(grub_probe_path))
    except FileNotFoundError as err:
        raise errors.GRUBInstallError("Missing grub-probe stub") from err
    except OSError as err:
        raise errors.GRUBInstallError("Failed to install grub-probe stub") from err

    for cmd in [
        ["dpkg-divert", *divert_common_args],
        update_grub_command,
        ["dpkg-divert", "--remove", *divert_common_args],
    ]:
        try:
            res = run(*cmd, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            raise errors.GRUBInstallError(
                "Failed to generate GRUB configuration"
            ) from err
        except FileNotFoundError as err:
            raise errors.GRUBInstallError("Missing tool to configure GRUB") from err
        if res.stdout:
            emit.debug(res.stdout)


def _update_grub(_loop_dev: str) -> None:
    """Run update-grub, stubbing grub-probe so it works without a block device.

    The caller must place a ``grub-probe`` stub at ``/tmp/imagecraft-grub-probe-stub``
    inside the chroot before invoking this function.

    :param _loop_dev: fake device name used as the GRUB root device.
    """
    os_prober = "/etc/grub.d/30_os-prober"
    check_update_grub = ["update-grub", "-V"]
    update_grub_command = ["update-grub"]

    # Divert os-probe to avoid writing wrong output in grub.cfg
    divert_common_args = [
        "--local",
        "--divert",
        f"{os_prober}.dpkg-divert",
        "--rename",
        os_prober,
    ]

    try:
        run(*check_update_grub)
    except FileNotFoundError:
        emit.progress(
            "Skipping GRUB configuration because update-grub is not available",
            permanent=True,
        )
        return

    grub_probe_stub = Path("/tmp/imagecraft-grub-probe-stub")  # noqa: S108
    grub_probe_path = Path("/usr/sbin/grub-probe")
    original_grub_probe = Path("/tmp/grub-probe.real")  # noqa: S108

    original_created = False
    try:
        if grub_probe_path.exists():
            shutil.copy2(str(grub_probe_path), str(original_grub_probe))
            original_created = True
        _run_update_grub_commands(
            grub_probe_stub, grub_probe_path, update_grub_command, divert_common_args
        )
    except FileNotFoundError as err:
        raise errors.GRUBInstallError("Missing tool to configure GRUB") from err
    except OSError as err:
        raise errors.GRUBInstallError("Failed to prepare grub-probe") from err
    finally:
        _restore_grub_probe(
            original_grub_probe, grub_probe_path, original_was_created=original_created
        )


def _grub_probe_stub_script(loop_dev: str, *, schema: PartitionSchema) -> str:
    """Return a shell script that answers grub-probe for the fake device.

    The template lives in ``grub_probe_stub.sh.in`` so it can be edited and
    formatted with shell tooling; this function only substitutes the dynamic
    values.

    :param loop_dev: fake device name (e.g. ``/dev/pc.img``).
    :param schema: partition schema of the image.
    :returns: The stub script content.
    """
    partmap = (
        "gpt" if schema in (PartitionSchema.GPT, PartitionSchema.HYBRID) else "msdos"
    )
    drive = "(hd0)"

    template_path = Path(__file__).with_name("grub_probe_stub.sh.in")
    return (
        template_path.read_text()
        .replace("__IMAGECRAFT_LOOP_DEV__", loop_dev)
        .replace("__IMAGECRAFT_DRIVE__", drive)
        .replace("__IMAGECRAFT_PARTMAP__", partmap)
    )


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
    dev_dir = workdir / "dev"
    dev_dir.mkdir(exist_ok=True)

    # Use the host /dev tree as the backing device directory.  In a regular
    # build environment this is a devtmpfs that already contains the standard
    # device nodes grub-install expects; ImageDevDir overlays the fake image
    # devices on top of it.  This is necessary because the test container
    # does not allow mounting a fresh devtmpfs here.
    os_utils.mount("/dev", dev_dir, "--bind")
    try:
        from imagecraft.utils.mount import CompositeMount, ImageDevDir  # noqa: PLC0415

        with ImageDevDir(image_path=image.disk_path, dev_dir=dev_dir) as devices:
            loop_dev_in_chroot = f"/dev/{devices[None].name}"
            root_uuid = _root_uuid(
                image.disk_path, image.volume.structure, filesystem_mount
            )
            part_mounts = _partition_mounts(
                image.disk_path, image.volume.structure, filesystem_mount
            )
            composite_mount = CompositeMount(mounts=part_mounts, mountpoint=mount_dir)
            composite_mount.mount()
            try:
                # Place a grub-probe stub inside the chroot so update-grub can
                # run even though the fake device files are not real block devices.
                grub_probe_stub_mount = mount_dir / "tmp" / "imagecraft-grub-probe-stub"
                grub_probe_stub_mount.parent.mkdir(parents=True, exist_ok=True)
                grub_probe_stub_mount.write_text(
                    _grub_probe_stub_script(loop_dev=loop_dev_in_chroot, schema=schema)
                )
                grub_probe_stub_mount.chmod(0o755)

                chroot_mounts: list[Mount] = [
                    Mount(
                        fstype=None,
                        src=str(dev_dir),
                        relative_mountpoint="/dev",
                        options=["--bind"],
                    ),
                    Mount(
                        fstype="devpts",
                        src="devpts-build",
                        relative_mountpoint="/dev/pts",
                        options=["-o", "nodev,nosuid"],
                    ),
                    Mount(fstype="proc", src="proc-build", relative_mountpoint="proc"),
                    Mount(
                        fstype="sysfs", src="sysfs-build", relative_mountpoint="/sys"
                    ),
                    Mount(
                        fstype=None,
                        src="/run",
                        relative_mountpoint="/run",
                        options=["--bind"],
                    ),
                ]
                chroot = Chroot(path=mount_dir, mounts=chroot_mounts)

                try:
                    chroot.execute(
                        target=_grub_install,
                        grub_target=grub_target,
                        loop_dev=loop_dev_in_chroot,
                        root_uuid=root_uuid,
                    )
                except errors.ChrootMountError as err:
                    # Ignore mounting errors indicating the rootfs does not have
                    # the needed structure to install grub.
                    emit.progress(
                        f"Cannot install GRUB on this rootfs: {err}", permanent=True
                    )
            finally:
                composite_mount.unmount()
    finally:
        os_utils.umount(str(dev_dir), "--recursive")


def _partition_mounts(
    disk_path: Path,
    structure: StructureList,
    filesystem_mount: FilesystemMount,
) -> list[tuple[str, "BaseMount"]]:
    """Generate FUSE mounts for each filesystem_mount entry.

    :param disk_path: path to the disk image file.
    :param structure: StructureList describing the partition layout of the image.
    :param filesystem_mount: order in which partitions should be mounted.
    :returns: List of (relative_mountpoint, BaseMount) pairs for CompositeMount.
    """
    from imagecraft.utils.mount import (  # noqa: PLC0415
        BaseMount,
        mount_partition,
    )

    part_mounts: list[tuple[str, BaseMount]] = []
    is_gpt = not structure or not isinstance(structure[0], MBRStructureItem)

    for entry in filesystem_mount:
        partition_name = _partition_name_from_device(entry.device)
        partnum = _part_num(partition_name, structure)
        if partnum is None:
            raise errors.ImageError(
                message=f"Cannot find a partition named {partition_name}"
            )

        filesystem = structure[partnum - 1].filesystem
        if is_gpt:
            start_sector = gptutil.get_partition_sector_offset(
                disk_path, partition_name
            )
            size_sectors = gptutil.get_partition_size_sectors(disk_path, partition_name)
        else:
            start_sector = gptutil.get_partition_sector_offset_by_number(
                disk_path, partnum
            )
            size_sectors = gptutil.get_partition_size_sectors_by_number(
                disk_path, partnum
            )

        part_mounts.append(
            (
                entry.mount,
                mount_partition(
                    disk_path,
                    filesystem,
                    offset=start_sector * gptutil.SECTOR_SIZE_512,
                    size=size_sectors * gptutil.SECTOR_SIZE_512,
                    allow_other=True,
                ),
            )
        )
    return part_mounts


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


def _root_uuid(
    image_path: Path,
    structure: StructureList,
    filesystem_mount: FilesystemMount,
) -> str | None:
    """Return the UUID of the partition mounted at ``/``.

    This probes the raw disk image at the root partition offset with ``blkid``
    rather than relying on the fake ``/dev`` devices, which are not block
    devices and may not be recognised by all disk tools.

    :param image_path: path to the disk image file.
    :param structure: volume structure describing the partitions.
    :param filesystem_mount: mount configuration for the image.
    :returns: UUID as a string, or ``None`` if it cannot be determined.
    """
    root_entry = next((entry for entry in filesystem_mount if entry.mount == "/"), None)
    if root_entry is None:
        return None
    part_name = _partition_name_from_device(root_entry.device)
    part_num = _part_num(part_name, structure)
    if part_num is None:
        return None

    is_gpt = not structure or not isinstance(structure[0], MBRStructureItem)
    if is_gpt:
        start_sector = gptutil.get_partition_sector_offset(image_path, part_name)
    else:
        start_sector = gptutil.get_partition_sector_offset_by_number(
            image_path, part_num
        )
    offset_bytes = start_sector * gptutil.SECTOR_SIZE_512

    try:
        result = run(
            "blkid",
            "-p",
            "-s",
            "UUID",
            "-o",
            "value",
            "-O",
            str(offset_bytes),
            str(image_path),
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return result.stdout.strip() or None


def _partition_name_from_device(device: str) -> str:
    """Extract the partition name from the device name.

    Works under the assumption that the full device name references
    the correct volume and the device name follows the
    (volume/<volume_name>/<structure_name>) syntax.

    """
    return device.strip("()").split("/")[-1]
