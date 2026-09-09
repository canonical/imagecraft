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

"""Non-EFI (legacy BIOS) bootloader installation.

``core.img`` is built with the guest rootfs's own ``grub-mkimage`` run in a
chroot over the root partition's prime directory. The resulting image is
then written into the raw disk image by patching bytes directly (Sector 0
and the embedding area), because ``grub-bios-setup`` cannot be used in an
unprivileged build container: it resolves the ``-d`` directory to a block
device via ``/proc/self/mountinfo``, and a plain prime directory has no
resolvable backing device there (verified against GRUB 2.12).
"""

import struct
from pathlib import Path
from uuid import UUID

from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models.volume import GptType, GPTVolume, HybridVolume, MBRVolume
from imagecraft.pack import gptutil
from imagecraft.pack.bootloader.chrootenv import (
    build_prime_chroot,
    find_chroot_binary,
    run_checked,
)
from imagecraft.pack.bootloader.config import render_early_cfg
from imagecraft.pack.bootloader.const import (
    CORE_BIOS_MODULES,
    DEFAULT_SECTOR_SIZE,
    GRUB_BOOT_IMAGE_CORE_LBA_OFFSET,
    GRUB_DISKBOOT_IMAGE_NEXT_SECTOR_OFFSET,
    MBR_BOOT_CODE_SIZE,
    get_arch_spec,
)
from imagecraft.pack.bootloader.fs import safe_copytree
from imagecraft.pack.bootloader.models import NonEfiInstallResult

_CHROOT_WORK_DIR = "/tmp/grub-bios"  # noqa: S108


def _bios_mod_dir(root_dir: Path, grub_format: str) -> Path:
    """Return the path to the rootfs's installed GRUB module directory."""
    return root_dir / "usr" / "lib" / "grub" / grub_format


def stage_non_efi_modules(
    root_dir: Path, boot_dir: Path | None = None, *, grub_format: str
) -> Path:
    """Stage BIOS GRUB runtime modules into the ``/boot`` prime directory.

    Must be called *before* the partitions are formatted (unlike the rest of
    this module, which writes to the raw image file after formatting), since
    it writes into a prime directory that ``diskutil.format_device`` will
    later embed via ``mke2fs -d``.

    :param root_dir: Prime directory of the root filesystem partition (used
        to locate the rootfs's installed GRUB modules).
    :param boot_dir: Prime directory that corresponds to ``/boot``. Defaults
        to ``root_dir / "boot"`` when ``/boot`` isn't a dedicated partition.
    :param grub_format: GRUB non-EFI target format (e.g. ``i386-pc``), from
        the architecture's :class:`~imagecraft.pack.bootloader.const.ArchSpec`.
    :return: The directory the modules were copied into.
    :raises errors.BootloaderToolsMissingError: If the GRUB BIOS modules
        directory isn't present in the staged rootfs.
    """
    mod_dir = _bios_mod_dir(root_dir, grub_format)
    if not mod_dir.is_dir():
        raise errors.BootloaderToolsMissingError(
            f"GRUB BIOS modules directory not found: {mod_dir}"
        )

    effective_boot_dir = boot_dir if boot_dir is not None else root_dir / "boot"
    target_mod_dir = effective_boot_dir / "grub" / grub_format
    safe_copytree(mod_dir, target_mod_dir)
    return target_mod_dir


def _build_core_img_in_chroot(
    *,
    early_cfg_content: str,
    modules: list[str],
    mkimage: str,
    grub_format: str,
    boot_prefix: str,
) -> None:
    """Build core.img with grub-mkimage inside the chroot.

    Must be a top-level function so it can be pickled into the chroot child
    process.

    :param early_cfg_content: Rendered early GRUB config content.
    :param modules: GRUB modules to embed in core.img.
    :param mkimage: In-chroot path to grub-mkimage.
    :param grub_format: GRUB non-EFI target format (e.g. ``i386-pc``).
    :param boot_prefix: GRUB prefix baked into core.img (``/boot/grub``, or
        ``/grub`` when ``/boot`` is a dedicated partition).
    :raises errors.BootloaderError: If grub-mkimage fails.
    """
    mod_dir = f"/usr/lib/grub/{grub_format}"
    work_dir = Path(_CHROOT_WORK_DIR)
    work_dir.mkdir(parents=True, exist_ok=True)
    early_cfg = work_dir / "early.cfg"
    early_cfg.write_text(early_cfg_content)
    run_checked(
        [
            mkimage,
            "-d",
            mod_dir,
            "-O",
            grub_format,
            "-o",
            f"{mod_dir}/core.img",
            "-p",
            boot_prefix,
            "-c",
            str(early_cfg),
            *modules,
        ]
    )


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
    """Installs the BIOS (non-EFI) bootloader using in-chroot GRUB tools.

    Only architectures with a non-EFI target in ``ARCH_SPECS`` (currently
    amd64/i386's ``i386-pc``) are supported; arm64/armhf/riscv64 always boot
    via EFI.
    """

    def __init__(
        self,
        *,
        image_path: Path,
        root_dir: Path,
        root_uuid: UUID | str,
        arch: DebianArchitecture,
        volume: GPTVolume | MBRVolume | HybridVolume,
        boot_uuid: UUID | str | None = None,
    ) -> None:
        """Initialize the non-EFI bootloader installer.

        :param image_path: Path to the raw, partitioned disk image file.
        :param root_dir: Prime directory of the root filesystem partition.
            Used as the chroot root; GRUB modules and tools come from here.
        :param root_uuid: UUID assigned to the root filesystem.
        :param arch: Target architecture.
        :param volume: The volume layout used to partition the image.
        :param boot_uuid: UUID assigned to the dedicated ``/boot``
            partition's filesystem, if any. The early config embedded in
            core.img searches this UUID (with a ``/grub`` prefix) instead of
            the root filesystem's.
        :raises errors.BootloaderError: If the architecture has no non-EFI
            GRUB target.
        """
        spec = get_arch_spec(arch)
        if spec.non_efi_format is None:
            raise errors.BootloaderError(
                f"Architecture {arch.value} has no non-EFI GRUB target"
            )
        self.image_path = image_path
        self.root_dir = root_dir
        self.root_uuid = str(root_uuid)
        self.volume = volume
        self.grub_format = spec.non_efi_format
        self.search_uuid = str(boot_uuid) if boot_uuid is not None else str(root_uuid)
        self.boot_prefix = "/grub" if boot_uuid is not None else "/boot/grub"

    def install(self) -> NonEfiInstallResult:
        """Build core.img in a chroot, then patch and embed it in the image.

        Assumes :func:`stage_non_efi_modules` has already been called during
        the pre-format staging phase to place GRUB runtime modules into the
        boot partition's prime directory.

        :raises errors.BootloaderToolsMissingError: If GRUB modules, boot.img,
            or grub-mkimage aren't present in the staged rootfs.
        """
        mod_dir = _bios_mod_dir(self.root_dir, self.grub_format)
        if not mod_dir.is_dir():
            raise errors.BootloaderToolsMissingError(
                f"GRUB BIOS modules directory not found: {mod_dir}"
            )
        boot_img_file = mod_dir / "boot.img"
        if not boot_img_file.is_file():
            raise errors.BootloaderToolsMissingError(
                f"GRUB stage 1 boot.img not found: {boot_img_file}"
            )
        mkimage = find_chroot_binary(self.root_dir, "grub-mkimage")

        modules = [m for m in CORE_BIOS_MODULES if (mod_dir / f"{m}.mod").is_file()]

        chroot = build_prime_chroot(self.root_dir)
        chroot.execute(
            target=_build_core_img_in_chroot,
            early_cfg_content=render_early_cfg(
                self.search_uuid, boot_prefix=self.boot_prefix
            ),
            modules=modules,
            mkimage=mkimage,
            grub_format=self.grub_format,
            boot_prefix=self.boot_prefix,
        )

        core_img_file = mod_dir / "core.img"
        core_bytes = core_img_file.read_bytes()
        core_img_file.unlink()

        target_sector, _ = determine_bios_target_sector(
            self.image_path, self.volume, len(core_bytes)
        )

        patched_boot = patch_boot_img(boot_img_file.read_bytes(), target_sector)
        embed_mbr_boot_code(self.image_path, patched_boot)

        patched_core = patch_core_img(core_bytes, target_sector)
        embed_core_img(self.image_path, patched_core, target_sector)

        return NonEfiInstallResult(
            format=self.grub_format,
            core_img_size_bytes=len(core_bytes),
            target_sector=target_sector,
            modules_installed=True,
        )


def install_non_efi(
    *,
    image_path: Path,
    root_dir: Path,
    root_uuid: UUID | str,
    arch: DebianArchitecture,
    volume: GPTVolume | MBRVolume | HybridVolume,
    boot_uuid: UUID | str | None = None,
) -> NonEfiInstallResult:
    """Install the BIOS bootloader into a raw disk image.

    :param image_path: Path to the raw, partitioned disk image file.
    :param root_dir: Prime directory of the root filesystem partition.
    :param root_uuid: UUID assigned to the root filesystem.
    :param arch: Target architecture.
    :param volume: The volume layout used to partition the image.
    :param boot_uuid: UUID assigned to the dedicated ``/boot`` partition's
        filesystem, if any.
    :return: NonEfiInstallResult.
    """
    installer = NonEfiInstaller(
        image_path=image_path,
        root_dir=root_dir,
        root_uuid=root_uuid,
        arch=arch,
        volume=volume,
        boot_uuid=boot_uuid,
    )
    return installer.install()
