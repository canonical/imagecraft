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

"""High-level bootloader installer coordinator.

Coordinates the two phases of loopless bootloader installation:

1. :meth:`BootloaderInstaller.prepare_rootfs` -- run *before* the root/ESP
   partitions are formatted. Writes ``/etc/fstab``, generates
   ``/boot/grub/grub.cfg`` with the guest's own ``grub-mkconfig`` (run in a
   chroot over the prime directory), and (for EFI targets) stages the EFI
   binaries and early search stub, directly into the partitions' prime
   directories. ``diskutil.format_device`` then embeds these files via
   ``mke2fs -d``/``mcopy``.
2. :meth:`BootloaderInstaller.install_image_boot_code` -- run *after* the
   final disk image has been assembled. For BIOS targets only, runs
   ``grub-mkimage``/``grub-bios-setup`` in a chroot with the image exposed
   at ``/dev/image``.

Neither phase attaches a loop device.
"""

import contextlib
from pathlib import Path
from uuid import UUID

from craft_cli import emit
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models.volume import (
    GptType,
    GPTVolume,
    HybridVolume,
    MBRVolume,
    PartitionSchema,
    Role,
    StructureItem,
)
from imagecraft.pack.bootloader.bios import install_non_efi, stage_non_efi_modules
from imagecraft.pack.bootloader.const import get_arch_spec
from imagecraft.pack.bootloader.efi import install_efi
from imagecraft.pack.bootloader.mkconfig import generate_grub_cfg
from imagecraft.pack.bootloader.models import (
    BootloaderResult,
    BootMethod,
    NonEfiInstallResult,
    RootfsConfigResult,
)
from imagecraft.pack.bootloader.rootfs import configure_fstab

AnyVolume = GPTVolume | MBRVolume | HybridVolume


def find_root_structure_item(volume: AnyVolume) -> StructureItem | None:
    """Return the first system-data (root filesystem) structure item, if any."""
    return next(
        (item for item in volume.structure if item.role == Role.SYSTEM_DATA), None
    )


def _gpt_type_of(item: StructureItem) -> GptType | None:
    """Return the GPT partition type of a structure item, if it has one.

    GPT items carry a :class:`GptType` directly; hybrid items encode it as
    the second component of a combined ``'<mbr-type>,<gpt-type>'`` string;
    MBR items have no GPT type.
    """
    structure_type = getattr(item, "structure_type", None)
    if isinstance(structure_type, GptType):
        return structure_type
    if isinstance(structure_type, str) and "," in structure_type:
        gpt_part = structure_type.split(",", 1)[1]
        with contextlib.suppress(ValueError):
            return GptType(gpt_part.upper())
    return None


def find_esp_structure_item(volume: AnyVolume) -> StructureItem | None:
    """Return the EFI System Partition structure item, if any."""
    return next(
        (item for item in volume.structure if _gpt_type_of(item) == GptType.EFI_SYSTEM),
        None,
    )


def find_boot_structure_item(volume: AnyVolume) -> StructureItem | None:
    """Return a dedicated ``/boot`` partition structure item, if any.

    A "dedicated boot partition" is a ``system-boot``-role item that is
    *not* the EFI System Partition and *not* a raw BIOS Boot partition
    (which holds GRUB's core.img, not a filesystem) -- e.g. an MBR volume
    with a separate ``/boot`` partition, or a GPT volume with distinct ESP
    and ``/boot`` partitions. Returns ``None`` when there's no such partition
    (including the common case where the only ``system-boot``-role item *is*
    the ESP).
    """
    esp_item = find_esp_structure_item(volume)
    return next(
        (
            item
            for item in volume.structure
            if item.role == Role.SYSTEM_BOOT
            and item is not esp_item
            and _gpt_type_of(item) != GptType.BIOS_BOOT
        ),
        None,
    )


def _has_bios_boot_partition(volume: AnyVolume) -> bool:
    return any(_gpt_type_of(item) == GptType.BIOS_BOOT for item in volume.structure)


class BootloaderInstaller:
    """Coordinates zero-mount GRUB installation for a single image volume."""

    def __init__(self, *, volume: AnyVolume, arch: DebianArchitecture | str) -> None:
        """Initialize the bootloader installer.

        :param volume: The volume layout being packed.
        :param arch: Target architecture.
        """
        self.volume = volume
        try:
            self.arch: DebianArchitecture | None = (
                arch
                if isinstance(arch, DebianArchitecture)
                else DebianArchitecture(arch)
            )
        except ValueError:
            self.arch = None

    def resolve_boot_method(self) -> BootMethod:
        """Determine which boot method (if any) applies to this volume/arch."""
        if find_root_structure_item(self.volume) is None:
            emit.progress(
                "Skipping bootloader installation because no data partition was found",
                permanent=True,
            )
            return BootMethod.NONE

        if self.arch is None:
            emit.progress(
                "Cannot install a bootloader for this architecture", permanent=True
            )
            return BootMethod.NONE

        try:
            spec = get_arch_spec(self.arch)
        except ValueError:
            emit.progress(
                "Cannot install a bootloader for this architecture", permanent=True
            )
            return BootMethod.NONE

        if find_esp_structure_item(self.volume) is not None:
            return BootMethod.EFI

        is_mbr_schema = self.volume.volume_schema == PartitionSchema.MBR
        if (
            is_mbr_schema or _has_bios_boot_partition(self.volume)
        ) and spec.non_efi_format is not None:
            return BootMethod.BIOS

        emit.progress(
            "Skipping bootloader installation because no suitable boot "
            "partition was found",
            permanent=True,
        )
        return BootMethod.NONE

    def prepare_rootfs(
        self,
        *,
        root_dir: Path,
        esp_dir: Path | None,
        root_uuid: UUID,
        boot_dir: Path | None = None,
        boot_uuid: UUID | None = None,
    ) -> BootloaderResult:
        """Stage bootloader files into prime directories before formatting.

        :param root_dir: Prime directory of the root filesystem partition.
        :param esp_dir: Prime directory of the EFI System Partition, if any.
        :param root_uuid: UUID that will be assigned to the root filesystem
            when it's formatted.
        :param boot_dir: Prime directory of a dedicated ``/boot`` partition,
            if any. Defaults to ``root_dir / "boot"`` when ``/boot`` isn't a
            separate partition.
        :param boot_uuid: UUID that will be assigned to the dedicated
            ``/boot`` partition's filesystem, if any.
        """
        boot_method = self.resolve_boot_method()
        if boot_method == BootMethod.NONE:
            return BootloaderResult(boot_method=boot_method)
        # resolve_boot_method() only returns a non-NONE method when self.arch
        # is a valid DebianArchitecture, so this is always safe here.
        assert self.arch is not None  # noqa: S101
        spec = get_arch_spec(self.arch)

        emit.progress("Preparing bootloader files")
        fstab_path, fstab_updated = configure_fstab(root_dir, root_uuid)
        partition_map = (
            "msdos"
            if self.volume.volume_schema == PartitionSchema.MBR
            else self.volume.volume_schema.value
        )
        try:
            grub_cfg_path = generate_grub_cfg(
                root_dir,
                root_uuid,
                boot_dir=boot_dir,
                boot_uuid=boot_uuid,
                partition_map=partition_map,
            )
        except errors.BootloaderToolsMissingError as err:
            emit.progress(f"Skipping bootloader installation: {err}", permanent=True)
            return BootloaderResult(
                boot_method=BootMethod.NONE,
                rootfs_result=RootfsConfigResult(
                    grub_cfg_path=(boot_dir or root_dir / "boot") / "grub" / "grub.cfg",
                    fstab_path=fstab_path,
                    fstab_updated=fstab_updated,
                ),
            )
        rootfs_result = RootfsConfigResult(
            grub_cfg_path=grub_cfg_path,
            fstab_path=fstab_path,
            fstab_updated=fstab_updated,
        )

        efi_result = None
        if boot_method == BootMethod.EFI:
            if esp_dir is None:
                emit.progress(
                    "Skipping EFI bootloader installation because no EFI "
                    "System Partition prime directory is available",
                    permanent=True,
                )
                return BootloaderResult(
                    boot_method=BootMethod.NONE, rootfs_result=rootfs_result
                )
            try:
                efi_result = install_efi(
                    root_dir=root_dir,
                    esp_dir=esp_dir,
                    root_uuid=root_uuid,
                    arch=self.arch,
                    boot_dir=boot_dir,
                    boot_uuid=boot_uuid,
                )
            except errors.BootloaderToolsMissingError as err:
                emit.progress(
                    f"Skipping EFI bootloader installation: {err}", permanent=True
                )
                return BootloaderResult(
                    boot_method=BootMethod.NONE, rootfs_result=rootfs_result
                )
        elif boot_method == BootMethod.BIOS:
            # resolve_boot_method() only returns BIOS when a non-EFI target
            # exists for this architecture, so this is always safe here.
            assert spec.non_efi_format is not None  # noqa: S101
            try:
                stage_non_efi_modules(
                    root_dir, boot_dir, grub_format=spec.non_efi_format
                )
            except errors.BootloaderToolsMissingError as err:
                emit.progress(
                    f"Skipping BIOS bootloader installation: {err}", permanent=True
                )
                return BootloaderResult(
                    boot_method=BootMethod.NONE, rootfs_result=rootfs_result
                )

        return BootloaderResult(
            boot_method=boot_method, rootfs_result=rootfs_result, efi_result=efi_result
        )

    def install_image_boot_code(
        self,
        *,
        image_path: Path,
        root_dir: Path,
        root_uuid: UUID,
        boot_uuid: UUID | None = None,
    ) -> NonEfiInstallResult | None:
        """Install BIOS boot code into the raw disk image, if applicable.

        Only takes effect for the BIOS boot method; a no-op (returning None)
        otherwise. Must be called after the image's partitions have been
        formatted and finalized.

        :param image_path: Path to the final, partitioned disk image file.
        :param root_dir: Prime directory of the root filesystem partition
            (used as the chroot root for GRUB tooling).
        :param root_uuid: UUID assigned to the root filesystem.
        :param boot_uuid: UUID assigned to the dedicated ``/boot``
            partition's filesystem, if any.
        """
        if self.resolve_boot_method() != BootMethod.BIOS:
            return None
        # resolve_boot_method() only returns BIOS when self.arch is a valid
        # DebianArchitecture, so this is always safe here.
        assert self.arch is not None  # noqa: S101

        emit.progress("Installing BIOS bootloader into the image")
        try:
            return install_non_efi(
                image_path=image_path,
                root_dir=root_dir,
                root_uuid=root_uuid,
                arch=self.arch,
                volume=self.volume,
                boot_uuid=boot_uuid,
            )
        except errors.BootloaderToolsMissingError as err:
            emit.progress(
                f"Skipping BIOS bootloader installation: {err}", permanent=True
            )
            return None
