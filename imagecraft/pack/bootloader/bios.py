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

"""Non-EFI (legacy BIOS) bootloader installation via raw sector patching.

Unlike ``grub-install``, this never mounts the target image or attaches a
loop device: GRUB's ``boot.img``/``core.img`` are patched in memory and
written directly to the raw disk image file at fixed byte offsets.
"""

import struct
import tempfile
from pathlib import Path, PurePosixPath
from uuid import UUID

from imagecraft import errors
from imagecraft.models.volume import GptType, GPTVolume, HybridVolume, MBRVolume
from imagecraft.pack import gptutil
from imagecraft.pack.bootloader.config import render_early_cfg
from imagecraft.pack.bootloader.const import (
    CORE_BIOS_MODULES,
    DEFAULT_SECTOR_SIZE,
    GRUB_BOOT_IMAGE_CORE_LBA_OFFSET,
    GRUB_DISKBOOT_IMAGE_NEXT_SECTOR_OFFSET,
    MBR_BOOT_CODE_SIZE,
)
from imagecraft.pack.bootloader.fs import safe_copytree
from imagecraft.pack.bootloader.mkimage import GrubMkimage
from imagecraft.pack.bootloader.models import NonEfiInstallResult

_GRUB_BIOS_FORMAT = "i386-pc"


def _bios_mod_dir(root_dir: Path) -> Path:
    """Return the path to the rootfs's installed i386-pc GRUB module directory."""
    return root_dir / "usr" / "lib" / "grub" / _GRUB_BIOS_FORMAT


def stage_non_efi_modules(root_dir: Path, boot_dir: Path | None = None) -> Path:
    """Stage BIOS GRUB runtime modules into the ``/boot`` prime directory.

    Must be called *before* the partitions are formatted (unlike the rest of
    this module, which patches the raw image file after formatting), since it
    writes into a prime directory that ``diskutil.format_device`` will later
    embed via ``mke2fs -d``.

    :param root_dir: Prime directory of the root filesystem partition (used
        to locate the rootfs's installed GRUB modules).
    :param boot_dir: Prime directory that corresponds to ``/boot``. Defaults
        to ``root_dir / "boot"`` when ``/boot`` isn't a dedicated partition.
    :return: The directory the modules were copied into.
    :raises errors.BootloaderToolsMissingError: If the GRUB BIOS modules
        directory isn't present in the staged rootfs.
    """
    mod_dir = _bios_mod_dir(root_dir)
    if not mod_dir.is_dir():
        raise errors.BootloaderToolsMissingError(
            f"GRUB BIOS modules directory not found: {mod_dir}"
        )

    effective_boot_dir = boot_dir if boot_dir is not None else root_dir / "boot"
    target_mod_dir = effective_boot_dir / "grub" / _GRUB_BIOS_FORMAT
    safe_copytree(mod_dir, target_mod_dir)
    return target_mod_dir


def determine_bios_target_sector(
    image_path: Path,
    volume: GPTVolume | MBRVolume | HybridVolume,
    core_img_size_bytes: int,
    sector_size: int = DEFAULT_SECTOR_SIZE,
) -> tuple[int, int]:
    """Determine the target sector and available capacity to embed core.img.

    For GPT/hybrid volumes, searches the structure for a BIOS Boot partition
    (type GUID ``21686148-6449-6E6F-744E-656564454649``). For MBR volumes,
    core.img is embedded in the post-MBR gap (sector 1 up to the first
    partition).

    :param image_path: Path to the (already-partitioned) raw disk image.
    :param volume: The volume layout that was used to partition the image.
    :param core_img_size_bytes: Size in bytes of the core.img to embed.
    :param sector_size: Sector size in bytes.
    :return: Tuple of (target_sector, max_available_sectors).
    :raises errors.BootloaderError: If no space is available, or core.img
        does not fit.
    """
    core_sectors = (core_img_size_bytes + sector_size - 1) // sector_size

    bios_boot_name = next(
        (
            item.name
            for item in volume.structure
            if getattr(item, "structure_type", None) == GptType.BIOS_BOOT
        ),
        None,
    )

    if bios_boot_name is not None:
        target_sector = gptutil.get_partition_sector_offset(image_path, bios_boot_name)
        max_sectors = gptutil.get_partition_size_sectors(image_path, bios_boot_name)
    else:
        target_sector = 1
        max_sectors = (
            gptutil.get_partition_sector_offset_by_number(image_path, 1) - target_sector
        )

    if max_sectors <= 0:
        raise errors.BootloaderError(
            "No space available to embed GRUB core.img (BIOS Boot partition or "
            "post-MBR gap)."
        )
    if core_sectors > max_sectors:
        raise errors.BootloaderError(
            f"GRUB core.img ({core_sectors} sectors) exceeds available capacity "
            f"({max_sectors} sectors)."
        )
    return target_sector, max_sectors


def patch_boot_img(boot_bytes: bytes, target_sector: int) -> bytes:
    """Patch boot.img's embedded 64-bit LBA pointer to point at target_sector.

    :param boot_bytes: Raw bytes of GRUB's boot.img (at least 512 bytes).
    :param target_sector: Starting LBA sector where core.img is embedded.
    :return: Patched boot.img bytes.
    :raises errors.BootloaderError: If boot_bytes is smaller than 512 bytes.
    """
    if len(boot_bytes) < DEFAULT_SECTOR_SIZE:
        raise errors.BootloaderError(
            f"Invalid boot.img size: expected at least {DEFAULT_SECTOR_SIZE} "
            f"bytes, got {len(boot_bytes)}"
        )

    data = bytearray(boot_bytes)
    struct.pack_into("<Q", data, GRUB_BOOT_IMAGE_CORE_LBA_OFFSET, target_sector)
    return bytes(data)


def embed_mbr_boot_code(
    image_path: Path, boot_code: bytes, max_bytes: int = MBR_BOOT_CODE_SIZE
) -> None:
    """Write boot code into Sector 0, preserving the partition table and signature.

    Only bytes ``0..max_bytes`` (default 440) of Sector 0 are overwritten,
    leaving the partition table (bytes 446-509) and the boot signature
    (0x55AA, bytes 510-511) untouched.

    :param image_path: Path to the target raw disk image.
    :param boot_code: Patched boot code bytes to write.
    :param max_bytes: Maximum byte boundary to write in Sector 0.
    """
    if not image_path.is_file():
        raise FileNotFoundError(f"Target disk image not found: {image_path}")

    with image_path.open("r+b") as image_file:
        image_file.seek(0)
        image_file.write(boot_code[:max_bytes])


def patch_core_img(core_bytes: bytes, target_sector: int) -> bytes:
    """Patch core.img's diskboot block with a pointer to the next sector.

    :param core_bytes: Raw bytes of GRUB's core.img.
    :param target_sector: Starting LBA sector where core.img begins.
    :return: Patched core.img bytes.
    """
    if len(core_bytes) < DEFAULT_SECTOR_SIZE:
        return core_bytes

    data = bytearray(core_bytes)
    struct.pack_into(
        "<I", data, GRUB_DISKBOOT_IMAGE_NEXT_SECTOR_OFFSET, target_sector + 1
    )
    return bytes(data)


def embed_core_img(
    image_path: Path,
    core_bytes: bytes,
    target_sector: int,
    sector_size: int = DEFAULT_SECTOR_SIZE,
) -> None:
    """Write the patched core.img directly at target_sector in the raw disk image.

    :param image_path: Path to the target raw disk image.
    :param core_bytes: Patched core.img bytes.
    :param target_sector: Starting sector offset.
    :param sector_size: Sector size in bytes.
    """
    if not image_path.is_file():
        raise FileNotFoundError(f"Target disk image not found: {image_path}")

    with image_path.open("r+b") as image_file:
        image_file.seek(target_sector * sector_size)
        image_file.write(core_bytes)


class NonEfiInstaller:
    """Assembles, patches, and embeds the BIOS (``i386-pc``) bootloader.

    Only the amd64/i386 ``i386-pc`` target is currently supported; there is
    no non-EFI target for arm64/armhf/riscv64 in this package (those
    architectures always boot via EFI).
    """

    def __init__(
        self,
        *,
        image_path: Path,
        root_dir: Path,
        root_uuid: UUID | str,
        volume: GPTVolume | MBRVolume | HybridVolume,
        mkimage: GrubMkimage | None = None,
    ) -> None:
        """Initialize the non-EFI bootloader installer.

        :param image_path: Path to the raw, partitioned disk image file.
        :param root_dir: Prime directory of the root filesystem partition
            (used to locate GRUB modules and boot.img).
        :param root_uuid: UUID that will be/was assigned to the root filesystem.
        :param volume: The volume layout used to partition the image.
        :param mkimage: Optional GrubMkimage instance (mainly for tests).
        """
        self.image_path = image_path
        self.root_dir = root_dir
        self.root_uuid = str(root_uuid)
        self.volume = volume
        self._mkimage = mkimage

    @property
    def mkimage(self) -> GrubMkimage:
        """Get or lazily initialize the GrubMkimage instance."""
        if self._mkimage is None:
            self._mkimage = GrubMkimage(root_dir=self.root_dir)
        return self._mkimage

    def install(self) -> NonEfiInstallResult:
        """Assemble, patch, and embed the BIOS bootloader into the disk image.

        Assumes :func:`stage_non_efi_modules` has already been called during
        the pre-format staging phase to place GRUB modules into the boot
        partition's prime directory.

        :raises errors.BootloaderToolsMissingError: If GRUB modules or
            boot.img aren't present in the staged rootfs.
        """
        mod_dir = _bios_mod_dir(self.root_dir)
        if not mod_dir.is_dir():
            raise errors.BootloaderToolsMissingError(
                f"GRUB BIOS modules directory not found: {mod_dir}"
            )
        boot_img_file = mod_dir / "boot.img"
        if not boot_img_file.is_file():
            raise errors.BootloaderToolsMissingError(
                f"GRUB stage 1 boot.img not found: {boot_img_file}"
            )

        with tempfile.TemporaryDirectory(prefix="imagecraft-grub-bios-") as tmpdir:
            early_cfg = Path(tmpdir) / "early.cfg"
            core_img = Path(tmpdir) / "core.img"
            early_cfg.write_text(render_early_cfg(self.root_uuid))

            self.mkimage.run(
                grub_format=_GRUB_BIOS_FORMAT,
                output=core_img,
                prefix=PurePosixPath("/boot/grub"),
                config=early_cfg,
                modules=CORE_BIOS_MODULES,
                directory=mod_dir,
            )
            core_bytes = core_img.read_bytes()

        target_sector, _ = determine_bios_target_sector(
            self.image_path, self.volume, len(core_bytes)
        )

        patched_boot = patch_boot_img(boot_img_file.read_bytes(), target_sector)
        embed_mbr_boot_code(self.image_path, patched_boot)

        patched_core = patch_core_img(core_bytes, target_sector)
        embed_core_img(self.image_path, patched_core, target_sector)

        return NonEfiInstallResult(
            format=_GRUB_BIOS_FORMAT,
            target_sector=target_sector,
            core_img_size_bytes=len(core_bytes),
            modules_installed=True,
        )


def install_non_efi(
    *,
    image_path: Path,
    root_dir: Path,
    root_uuid: UUID | str,
    volume: GPTVolume | MBRVolume | HybridVolume,
    mkimage: GrubMkimage | None = None,
) -> NonEfiInstallResult:
    """Install the BIOS bootloader into a raw disk image.

    :param image_path: Path to the raw, partitioned disk image file.
    :param root_dir: Prime directory of the root filesystem partition.
    :param root_uuid: UUID that will be/was assigned to the root filesystem.
    :param volume: The volume layout used to partition the image.
    :param mkimage: Optional GrubMkimage instance (mainly for tests).
    :return: NonEfiInstallResult.
    """
    installer = NonEfiInstaller(
        image_path=image_path,
        root_dir=root_dir,
        root_uuid=root_uuid,
        volume=volume,
        mkimage=mkimage,
    )
    return installer.install()
