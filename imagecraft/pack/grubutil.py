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

"""GRUB utils.

Installs and configures GRUB directly against a raw disk image, without
mounting anything, attaching loop devices, chrooting, or spinning up a VM.
This lets imagecraft build images in unprivileged containers that can't do
any of those things.

Instead, this module:

- Builds GRUB boot images with ``grub-mkimage`` (or deploys Ubuntu's
  pre-signed Secure Boot shim/GRUB, when available) and writes them straight
  into the EFI System Partition with ``mtools``.
- Writes GRUB runtime assets and ``grub.cfg`` into the ext4 boot partition
  with ``debugfs``, after extracting/re-injecting it with ``dd`` (``debugfs``
  only understands whole filesystem images, not partitions embedded in a
  bigger disk image).
- For legacy BIOS/MBR boot, embeds ``core.img`` directly into the reserved
  MBR gap and patches the boot sector's kernel-sector field by hand, instead
  of running ``grub-bios-setup`` (which requires a real, mountable device to
  probe).
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import cast

from craft_cli import emit
from craft_parts.filesystem_mounts import FilesystemMount
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models.volume import (
    MBRStructureItem,
    PartitionSchema,
    StructureList,
)
from imagecraft.pack import gptutil, imgfs, mbrutil
from imagecraft.pack.image import Image
from imagecraft.subprocesses import run

_ARCH_TO_GRUB_EFI_TARGET: dict[str, str] = {
    DebianArchitecture.AMD64: "x86_64-efi",
    DebianArchitecture.ARM64: "arm64-efi",
    DebianArchitecture.ARMHF: "arm-efi",
}

_GRUB_BIOS_TARGET = "i386-pc"
_GRUB_BIOS_ARCHS = {DebianArchitecture.AMD64, DebianArchitecture.I386}

# Maps grub EFI target -> (grub binary filename, UEFI fallback filename).
_EFI_TARGET_TO_FILENAMES: dict[str, tuple[str, str]] = {
    "x86_64-efi": ("grubx64.efi", "BOOTX64.EFI"),
    "arm64-efi": ("grubaa64.efi", "BOOTAA64.EFI"),
    "arm-efi": ("grubarm.efi", "BOOTARM.EFI"),
}

# Maps grub EFI target -> shim filename, for Secure Boot deployments.
_EFI_TARGET_TO_SHIM_FILENAME: dict[str, str] = {
    "x86_64-efi": "shimx64.efi",
    "arm64-efi": "shimaa64.efi",
    "arm-efi": "shimarm.efi",
}

# Core modules embedded into the standalone GRUB EFI image so it can find
# and load the rest of GRUB (partition tables, filesystems, search-by-UUID).
_EFI_CORE_MODULES = [
    "part_gpt",
    "part_msdos",
    "fat",
    "ext2",
    "normal",
    "search",
    "search_fs_uuid",
    "search_label",
    "search_fs_file",
    "boot",
    "linux",
    "configfile",
    "echo",
    "loadenv",
    "test",
    "efi_gop",
    "gfxterm",
    "font",
]

_BIOS_CORE_MODULES = [
    "biosdisk",
    "part_msdos",
    "part_gpt",
    "ext2",
    "fat",
    "normal",
    "search",
    "search_fs_uuid",
    "boot",
    "linux",
    "configfile",
]

# Signed shim/grub filename suffixes, in preference order.
_SIGNED_SHIM_SUFFIXES = (".efi.signed.latest", ".efi.signed", ".efi.dualsigned")

# Offset (in bytes) of boot.img's 8-byte little-endian "kernel sector" field:
# the absolute LBA where core.img begins. This is the only part of boot.img
# that needs patching; see GRUB_BOOT_MACHINE_KERNEL_SECTOR in GRUB's
# grub-core/boot/i386/pc/boot.S.
_BIOS_KERNEL_SECTOR_OFFSET = 0x5C
# Bytes at and beyond this offset in the target's sector 0 are the disk
# signature, partition table, and 0x55AA boot signature; they must be
# preserved from the disk already partitioned by sfdisk, not overwritten
# with boot.img's own (irrelevant) template bytes.
_BIOS_BOOT_CODE_SIZE = 0x1B8
# First sector of the MBR gap (right after the MBR itself) where core.img is
# embedded. The gap reserved by mbrutil (mbrutil.MBR_RESERVED_SIZE) is far
# larger than any core.img we build.
_BIOS_CORE_IMG_START_SECTOR = 4

# Offset (in bytes) of core.img's first sector (diskboot.img)'s embedded
# "blocklist" entry describing where the *rest* of core.img (i.e. beyond
# this first sector) lives on disk. grub-mkimage leaves the start-sector
# field as a placeholder (logical sector 2 relative to core.img itself) and
# only fills in the length; grub-bios-setup is normally responsible for
# patching the start field with the real absolute disk LBA. See
# blocklist_default_start/grub_boot_blocklist in GRUB's
# grub-core/boot/i386/pc/diskboot.S and include/grub/i386/pc/boot.h.
_BIOS_BLOCKLIST_START_OFFSET = 0x1F4


def setup_grub(
    image: Image,
    workdir: Path,  # noqa: ARG001 (kept for call-site compatibility)
    arch: str,
    filesystem_mount: FilesystemMount,
) -> None:
    """Set up GRUB directly on the disk image.

    :param image: Image object handling the actual disk file
    :param workdir: working directory (unused, kept for interface stability)
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

    if not _check_grub_mkimage_available():
        emit.progress(
            "Skipping GRUB installation because grub-mkimage is not available",
            permanent=True,
        )
        return

    try:
        if grub_target == _GRUB_BIOS_TARGET:
            _setup_grub_bios(image, filesystem_mount)
        else:
            _setup_grub_efi(image, grub_target, filesystem_mount)
    except errors.ImageError as err:
        emit.progress(f"Cannot install GRUB on this rootfs: {err}", permanent=True)


def _check_grub_mkimage_available() -> bool:
    try:
        run("grub-mkimage", "-V")
    except FileNotFoundError:
        return False
    return True


def _mount_entry(filesystem_mount: FilesystemMount, mount: str) -> str | None:
    for entry in filesystem_mount:
        if entry.mount.rstrip("/") == mount.rstrip("/") or (
            mount == "/" and entry.mount in ("", "/")
        ):
            return entry.device
    return None


def _partition_geometry(
    disk_path: Path,
    structure: StructureList,
    filesystem_mount: FilesystemMount,
    mount: str,
) -> tuple[str, int, int]:
    """Return (partition_name, offset_sectors, size_sectors) for the given mountpoint."""
    device = _mount_entry(filesystem_mount, mount)
    if device is None:
        raise errors.ImageError(message=f"No partition mounted at {mount!r}")
    partition_name = _partition_name_from_device(device)
    partnum = _part_num(partition_name, structure)
    if partnum is None:
        raise errors.ImageError(
            message=f"Cannot find a partition named {partition_name}"
        )
    if isinstance(structure[0], MBRStructureItem):
        # MBR partitions aren't named in sfdisk's output; look them up by
        # their 1-based position instead.
        offset = gptutil.get_partition_sector_offset_by_number(disk_path, partnum)
        size = gptutil.get_partition_size_sectors_by_number(disk_path, partnum)
    else:
        offset = gptutil.get_partition_sector_offset(disk_path, partition_name)
        size = gptutil.get_partition_size_sectors(disk_path, partition_name)
    return partition_name, offset, size


def _has_separate_boot(filesystem_mount: FilesystemMount) -> bool:
    return _mount_entry(filesystem_mount, "/boot") is not None


def _setup_grub_efi(
    image: Image, grub_target: str, filesystem_mount: FilesystemMount
) -> None:
    """Install GRUB for an EFI-capable (GPT/hybrid) image."""
    structure = image.volume.structure
    disk_path = image.disk_path

    _, root_offset, root_size = _partition_geometry(
        disk_path, structure, filesystem_mount, "/"
    )
    has_separate_boot = _has_separate_boot(filesystem_mount)
    if has_separate_boot:
        _, boot_offset, boot_size = _partition_geometry(
            disk_path, structure, filesystem_mount, "/boot"
        )
    else:
        boot_offset, boot_size = root_offset, root_size
    # When /boot lives on its own partition, that partition's root directory
    # *is* /boot, so paths written to it must not be prefixed with "/boot".
    boot_prefix = "" if has_separate_boot else "/boot"
    _, esp_offset_sectors, _ = _partition_geometry(
        disk_path, structure, filesystem_mount, "/boot/efi"
    )
    esp_offset_bytes = esp_offset_sectors * imgfs.SECTOR_SIZE

    grub_fname, fallback_fname = _EFI_TARGET_TO_FILENAMES[grub_target]
    shim_fname = _EFI_TARGET_TO_SHIM_FILENAME.get(grub_target)

    with tempfile.TemporaryDirectory(prefix="imagecraft-grub-") as tmp_str:
        tmp_dir = Path(tmp_str)
        local_modules_dir = tmp_dir / "modules"
        local_binary = tmp_dir / grub_fname

        with imgfs.edit_ext_partition(disk_path, root_offset, root_size) as root_img:
            signed = _dump_signed_efi_binaries(root_img, grub_target, tmp_dir)
            # Always dump unsigned modules too: even signed images load
            # additional modules from /boot/grub/<target> at runtime.
            _dump_grub_modules(root_img, grub_target, local_modules_dir)
            root_uuid = imgfs.read_ext_uuid(root_img)

            if signed:
                emit.progress(f"Deploying signed GRUB ({grub_target})")
                shutil.copy2(signed["grub"], local_binary)
            else:
                emit.progress(f"Building unsigned GRUB image ({grub_target})")
                # Match Ubuntu's signed grub: bake in /EFI/ubuntu as $prefix
                # (same directory shim loads it from), so it finds the ESP
                # stub grub.cfg written below without needing a device search.
                _grub_mkimage(
                    local_modules_dir,
                    grub_target,
                    local_binary,
                    _EFI_CORE_MODULES,
                    prefix="/EFI/ubuntu",
                )

        _deploy_efi_binary(
            disk_path,
            esp_offset_bytes,
            local_binary,
            grub_fname,
            fallback_fname,
            signed_shim=signed["shim"] if signed else None,
            shim_fname=shim_fname,
        )

        stub_cfg = _efi_stub_grub_cfg(root_uuid)
        local_stub = tmp_dir / "grub.cfg"
        local_stub.write_text(stub_cfg, encoding="utf-8")
        imgfs.mcopy_in(disk_path, esp_offset_bytes, local_stub, "/EFI/ubuntu/grub.cfg")
        imgfs.mcopy_in(disk_path, esp_offset_bytes, local_stub, "/EFI/BOOT/grub.cfg")

        # Deploy runtime modules + the real grub.cfg to <boot_prefix>/grub, on
        # whichever partition holds /boot (root or a separate boot partition).
        with imgfs.edit_ext_partition(disk_path, boot_offset, boot_size) as boot_img:
            _deploy_grub_runtime_assets(
                boot_img, local_modules_dir, grub_target, boot_prefix
            )
            kernels = _find_kernels(boot_img, boot_prefix)
            cfg = _generate_grub_cfg(kernels, root_uuid, boot_prefix)
            local_cfg = tmp_dir / "real-grub.cfg"
            local_cfg.write_text(cfg, encoding="utf-8")
            imgfs.debugfs_write_file(
                boot_img, local_cfg, f"{boot_prefix}/grub/grub.cfg"
            )

    emit.progress("GRUB installation complete")


def _deploy_efi_binary(
    disk_path: Path,
    esp_offset_bytes: int,
    local_binary: Path,
    grub_fname: str,
    fallback_fname: str,
    *,
    signed_shim: Path | None,
    shim_fname: str | None,
) -> None:
    """Deploy the GRUB EFI binary to both the vendor and fallback ESP paths."""
    imgfs.mcopy_in(
        disk_path, esp_offset_bytes, local_binary, f"/EFI/ubuntu/{grub_fname}"
    )
    if signed_shim and shim_fname:
        # Shim is the entry point that chainloads grubx64.efi from the
        # same directory it resides in.
        imgfs.mcopy_in(
            disk_path, esp_offset_bytes, signed_shim, f"/EFI/ubuntu/{shim_fname}"
        )
        imgfs.mcopy_in(
            disk_path, esp_offset_bytes, signed_shim, f"/EFI/BOOT/{fallback_fname}"
        )
        imgfs.mcopy_in(
            disk_path, esp_offset_bytes, local_binary, f"/EFI/BOOT/{grub_fname}"
        )
    else:
        imgfs.mcopy_in(
            disk_path, esp_offset_bytes, local_binary, f"/EFI/BOOT/{fallback_fname}"
        )


def _setup_grub_bios(image: Image, filesystem_mount: FilesystemMount) -> None:
    """Install GRUB for a legacy BIOS/MBR image."""
    structure = image.volume.structure
    disk_path = image.disk_path

    _, root_offset, root_size = _partition_geometry(
        disk_path, structure, filesystem_mount, "/"
    )
    has_separate_boot = _has_separate_boot(filesystem_mount)
    if has_separate_boot:
        boot_partition_name, boot_offset, boot_size = _partition_geometry(
            disk_path, structure, filesystem_mount, "/boot"
        )
    else:
        boot_partition_name, boot_offset, boot_size = _partition_geometry(
            disk_path, structure, filesystem_mount, "/"
        )
    # When /boot lives on its own partition, that partition's root directory
    # *is* /boot, so paths written to it must not be prefixed with "/boot".
    boot_prefix = "" if has_separate_boot else "/boot"
    boot_partnum = _part_num(boot_partition_name, structure)

    with tempfile.TemporaryDirectory(prefix="imagecraft-grub-") as tmp_str:
        tmp_dir = Path(tmp_str)
        local_modules_dir = tmp_dir / "modules"

        with imgfs.edit_ext_partition(disk_path, root_offset, root_size) as root_img:
            _dump_grub_modules(root_img, _GRUB_BIOS_TARGET, local_modules_dir)
            boot_img_path = tmp_dir / "boot.img"
            imgfs.debugfs_read_file(
                root_img, f"/usr/lib/grub/{_GRUB_BIOS_TARGET}/boot.img", boot_img_path
            )
            root_uuid = imgfs.read_ext_uuid(root_img)

        core_img_path = tmp_dir / "core.img"
        _grub_mkimage(
            local_modules_dir,
            _GRUB_BIOS_TARGET,
            core_img_path,
            _BIOS_CORE_MODULES,
            prefix=f"(hd0,msdos{boot_partnum}){boot_prefix}/grub",
        )

        with imgfs.edit_ext_partition(disk_path, boot_offset, boot_size) as boot_img:
            _deploy_grub_runtime_assets(
                boot_img, local_modules_dir, _GRUB_BIOS_TARGET, boot_prefix
            )
            imgfs.debugfs_write_file(
                boot_img,
                core_img_path,
                f"{boot_prefix}/grub/{_GRUB_BIOS_TARGET}/core.img",
            )
            imgfs.debugfs_write_file(
                boot_img,
                boot_img_path,
                f"{boot_prefix}/grub/{_GRUB_BIOS_TARGET}/boot.img",
            )
            kernels = _find_kernels(boot_img, boot_prefix)
            cfg = _generate_grub_cfg(kernels, root_uuid, boot_prefix)
            local_cfg = tmp_dir / "real-grub.cfg"
            local_cfg.write_text(cfg, encoding="utf-8")
            imgfs.debugfs_write_file(
                boot_img, local_cfg, f"{boot_prefix}/grub/grub.cfg"
            )

        _install_bios_boot_sector(disk_path, boot_img_path, core_img_path)

    emit.progress("GRUB installation complete")


def _install_bios_boot_sector(disk_path: Path, boot_img: Path, core_img: Path) -> None:
    """Embed core.img in the MBR gap and patch boot.img's kernel-sector field.

    This replicates what ``grub-bios-setup`` does on disk, without needing a
    real block device for it to probe: boot.img's boot code (the first
    0x1B8 bytes) is written to sector 0 with its kernel-sector field pointing
    at core.img's location, while the disk signature/partition table/boot
    signature already written by sfdisk are preserved untouched. core.img's
    own embedded blocklist (in its first sector, diskboot.img) is also
    patched to point at the disk-absolute sector following core.img's first
    sector, since grub-mkimage only fills in the blocklist's length, not its
    start sector.
    """
    boot_data = bytearray(boot_img.read_bytes())
    if len(boot_data) != imgfs.SECTOR_SIZE:
        raise errors.GRUBInstallError(f"Unexpected boot.img size: {len(boot_data)}")
    boot_data[_BIOS_KERNEL_SECTOR_OFFSET : _BIOS_KERNEL_SECTOR_OFFSET + 8] = (
        _BIOS_CORE_IMG_START_SECTOR.to_bytes(8, "little")
    )

    core_data = bytearray(core_img.read_bytes())
    core_sectors = (len(core_data) + imgfs.SECTOR_SIZE - 1) // imgfs.SECTOR_SIZE
    if (
        _BIOS_CORE_IMG_START_SECTOR + core_sectors
    ) * imgfs.SECTOR_SIZE > mbrutil.MBR_RESERVED_SIZE:
        raise errors.GRUBInstallError("core.img is too large to fit in the MBR gap")

    # The blocklist's start sector is relative to the disk, not to core.img,
    # and points to the sector right after diskboot.img (core.img's own
    # first sector).
    rest_of_core_start_sector = _BIOS_CORE_IMG_START_SECTOR + 1
    core_data[_BIOS_BLOCKLIST_START_OFFSET : _BIOS_BLOCKLIST_START_OFFSET + 8] = (
        rest_of_core_start_sector.to_bytes(8, "little")
    )

    with disk_path.open("r+b") as disk_file:
        existing_sector0 = bytearray(disk_file.read(imgfs.SECTOR_SIZE))
        new_sector0 = bytes(boot_data[:_BIOS_BOOT_CODE_SIZE]) + bytes(
            existing_sector0[_BIOS_BOOT_CODE_SIZE : imgfs.SECTOR_SIZE]
        )
        disk_file.seek(0)
        disk_file.write(new_sector0)
        disk_file.seek(_BIOS_CORE_IMG_START_SECTOR * imgfs.SECTOR_SIZE)
        disk_file.write(core_data)


def _dump_signed_efi_binaries(
    root_img: Path, grub_target: str, dest_dir: Path
) -> dict[str, Path] | None:
    """Dump Ubuntu's pre-signed shim+GRUB from root_img, if both are present.

    Returns a dict with "shim" and "grub" local paths, or None if either
    piece isn't installed (in which case an unsigned image should be built
    with grub-mkimage instead).
    """
    grub_fname, _ = _EFI_TARGET_TO_FILENAMES[grub_target]
    shim_fname = _EFI_TARGET_TO_SHIM_FILENAME.get(grub_target)
    if shim_fname is None:
        return None

    shim_base = shim_fname.removesuffix(".efi")
    shim_src = None
    for suffix in _SIGNED_SHIM_SUFFIXES:
        candidate = f"/usr/lib/shim/{shim_base}{suffix}"
        if imgfs.debugfs_exists(root_img, candidate):
            shim_src = candidate
            break
    grub_src = f"/usr/lib/grub/{grub_target}-signed/{grub_fname}.signed"
    if shim_src is None or not imgfs.debugfs_exists(root_img, grub_src):
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    shim_dest = dest_dir / shim_fname
    grub_dest = dest_dir / f"{grub_fname}.signed"
    imgfs.debugfs_read_file(root_img, shim_src, shim_dest)
    imgfs.debugfs_read_file(root_img, grub_src, grub_dest)
    return {"shim": shim_dest, "grub": grub_dest}


def _dump_grub_modules(root_img: Path, grub_target: str, dest_dir: Path) -> None:
    """Dump GRUB's modules/metadata for grub_target out of root_img.

    Everything under /usr/lib/grub/<target> is dumped (not just *.mod/*.lst):
    grub-mkimage also needs kernel.img and, for i386-pc, compression helpers
    like lzma_decompress.img to build a standalone image.
    """
    src_dir = f"/usr/lib/grub/{grub_target}"
    if not imgfs.debugfs_exists(root_img, src_dir):
        raise errors.ImageError(
            message=f"GRUB modules for {grub_target} are not installed in the image"
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in imgfs.debugfs_list_dir(root_img, src_dir):
        if name == "monolithic":
            # A prebuilt (non-custom) monolithic image directory shipped by
            # grub-efi-amd64-bin; irrelevant since we always build our own
            # standalone image with grub-mkimage.
            continue
        imgfs.debugfs_read_file(root_img, f"{src_dir}/{name}", dest_dir / name)


def _grub_mkimage(
    modules_dir: Path,
    grub_target: str,
    output: Path,
    modules: list[str],
    prefix: str = "/boot/grub",
) -> None:
    """Build a standalone GRUB image from locally-dumped modules.

    This is a plain local host command — no chroot needed, since
    grub-mkimage just reads/writes regular files.
    """
    try:
        run(
            "grub-mkimage",
            "-d",
            str(modules_dir),
            "-o",
            str(output),
            "-O",
            grub_target,
            "-p",
            prefix,
            *modules,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError(
            f"Failed to build GRUB image for {grub_target} with grub-mkimage"
        ) from err


def _deploy_grub_runtime_assets(
    boot_img: Path, local_modules_dir: Path, grub_target: str, boot_prefix: str
) -> None:
    """Copy GRUB modules/metadata into <boot_prefix>/grub/<target> on boot_img."""
    if not local_modules_dir.is_dir():
        return
    for item in sorted(local_modules_dir.iterdir()):
        if item.name in ("boot.img", "cdboot.img", "kernel.img"):
            continue
        imgfs.debugfs_write_file(
            boot_img, item, f"{boot_prefix}/grub/{grub_target}/{item.name}"
        )


def _find_kernels(boot_img: Path, boot_prefix: str) -> list[tuple[str, str]]:
    """Return (vmlinuz, initrd) filename pairs found under boot_prefix on boot_img."""
    search_dir = boot_prefix or "/"
    if not imgfs.debugfs_exists(boot_img, search_dir):
        return []
    names = imgfs.debugfs_list_dir(boot_img, search_dir)
    vmlinuzes = sorted(n for n in names if n.startswith("vmlinuz-"))
    kernels = []
    for vmlinuz in vmlinuzes:
        version = vmlinuz.removeprefix("vmlinuz-")
        initrd = f"initrd.img-{version}"
        kernels.append((vmlinuz, initrd if initrd in names else ""))
    return kernels


def _generate_grub_cfg(
    kernels: list[tuple[str, str]], root_uuid: str, boot_prefix: str
) -> str:
    """Hand-generate a minimal grub.cfg with a menu entry per kernel found."""
    lines = [
        "set default=0",
        "set timeout=5",
        "insmod part_gpt",
        "insmod part_msdos",
        "insmod ext2",
        f"search --no-floppy --fs-uuid --set=root {root_uuid}",
        "",
    ]
    for vmlinuz, initrd in kernels:
        lines.append(f'menuentry "{vmlinuz}" {{')
        lines.append(f"\tlinux {boot_prefix}/{vmlinuz} root=UUID={root_uuid} ro")
        if initrd:
            lines.append(f"\tinitrd {boot_prefix}/{initrd}")
        lines.append("}")
    return "\n".join(lines) + "\n"


def _efi_stub_grub_cfg(root_uuid: str) -> str:
    """Build the tiny loader config placed on the ESP that chains to the real config."""
    return (
        "\n".join(
            [
                "insmod part_gpt",
                "insmod ext2",
                f"search.fs_uuid {root_uuid} root",
                "set prefix=($root)'/boot/grub'",
                "configfile $prefix/grub.cfg",
            ]
        )
        + "\n"
    )


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
                return cast(int, explicit)
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
