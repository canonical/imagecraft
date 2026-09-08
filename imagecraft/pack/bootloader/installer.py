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

Coordinates the two phases of zero-mount bootloader installation:

1. :meth:`BootloaderInstaller.prepare_rootfs` -- run *before* the root/ESP
   partitions are formatted. Writes ``/etc/fstab``, ``/boot/grub/grub.cfg``,
   and (for EFI targets) the EFI binaries and early search stub, directly
   into the partitions' prime directories. ``diskutil.format_device`` then
   embeds these files via ``mke2fs -d``/``mcopy``.
2. :meth:`BootloaderInstaller.install_image_boot_code` -- run *after* the
   final disk image has been assembled. For BIOS targets only, patches
   Sector 0 and embeds ``core.img`` directly into the raw image file.

Neither phase mounts anything or attaches a loop device.
"""

from pathlib import Path
from uuid import UUID

from craft_cli import emit
from craft_platforms import DebianArchitecture

from imagecraft.models.volume import (
    GptType,
    GPTVolume,
    HybridVolume,
    MBRVolume,
    PartitionSchema,
    Role,
    StructureItem,
)
from imagecraft.pack.bootloader.bios import install_non_efi
from imagecraft.pack.bootloader.const import get_arch_spec
from imagecraft.pack.bootloader.efi import install_efi
from imagecraft.pack.bootloader.models import (
    BootloaderResult,
    BootMethod,
    NonEfiInstallResult,
)
from imagecraft.pack.bootloader.rootfs import configure_rootfs

AnyVolume = GPTVolume | MBRVolume | HybridVolume


def find_root_structure_item(volume: AnyVolume) -> StructureItem | None:
    """Return the first system-data (root filesystem) structure item, if any."""
    return next(
        (item for item in volume.structure if item.role == Role.SYSTEM_DATA), None
    )


def find_esp_structure_item(volume: AnyVolume) -> StructureItem | None:
    """Return the EFI System Partition structure item, if any."""
    return next(
        (
            item
            for item in volume.structure
            if getattr(item, "structure_type", None) == GptType.EFI_SYSTEM
        ),
        None,
    )


def _has_bios_boot_partition(volume: AnyVolume) -> bool:
    return any(
        getattr(item, "structure_type", None) == GptType.BIOS_BOOT
        for item in volume.structure
    )


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

        spec = get_arch_spec(self.arch)

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
        self, *, root_dir: Path, esp_dir: Path | None, root_uuid: UUID
    ) -> BootloaderResult:
        """Stage bootloader files into prime directories before formatting.

        :param root_dir: Prime directory of the root filesystem partition.
        :param esp_dir: Prime directory of the EFI System Partition, if any.
        :param root_uuid: UUID that will be assigned to the root filesystem
            when it's formatted.
        """
        boot_method = self.resolve_boot_method()
        if boot_method == BootMethod.NONE:
            return BootloaderResult(boot_method=boot_method)
        # resolve_boot_method() only returns a non-NONE method when self.arch
        # is a valid DebianArchitecture, so this is always safe here.
        assert self.arch is not None  # noqa: S101

        emit.progress("Preparing bootloader files")
        rootfs_result = configure_rootfs(root_dir, root_uuid, self.arch)

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
            efi_result = install_efi(
                root_dir=root_dir,
                esp_dir=esp_dir,
                root_uuid=root_uuid,
                arch=self.arch,
            )

        return BootloaderResult(
            boot_method=boot_method, rootfs_result=rootfs_result, efi_result=efi_result
        )

    def install_image_boot_code(
        self, *, image_path: Path, root_dir: Path, root_uuid: UUID
    ) -> NonEfiInstallResult | None:
        """Patch the raw disk image with BIOS boot code, if applicable.

        Only takes effect for the BIOS boot method; a no-op (returning None)
        otherwise. Must be called after the image's partitions have been
        formatted and finalized.

        :param image_path: Path to the final, partitioned disk image file.
        :param root_dir: Prime directory of the root filesystem partition
            (used to locate GRUB modules/boot.img).
        :param root_uuid: UUID assigned to the root filesystem.
        """
        if self.resolve_boot_method() != BootMethod.BIOS:
            return None

        emit.progress("Installing BIOS bootloader into the image")
        return install_non_efi(
            image_path=image_path,
            root_dir=root_dir,
            root_uuid=root_uuid,
            volume=self.volume,
        )
