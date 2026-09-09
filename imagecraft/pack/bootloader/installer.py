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

Coordinates the two phases of bootloader installation:

1. :meth:`BootloaderInstaller.prepare_rootfs` -- run *before* the partitions
   are formatted. Writes ``/etc/fstab``, generates ``/boot/grub/grub.cfg``,
   and (for EFI targets) stages the EFI binaries and early search stub into
   the partitions' prime directories, which ``diskutil.format_device`` then
   embeds via ``mke2fs -d``/``mcopy``.
2. :meth:`BootloaderInstaller.install_image_boot_code` -- run *after* the
   final disk image has been assembled; BIOS targets only.
"""

import uuid
from pathlib import Path
from typing import Protocol
from uuid import UUID

from craft_cli import emit
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models import get_partition_name
from imagecraft.models.volume import (
    GPTVolume,
    HybridVolume,
    MBRVolume,
    PartitionSchema,
    StructureItem,
)
from imagecraft.pack.bootloader.bios import PCBiosInstaller
from imagecraft.pack.bootloader.chrootenv import stage_grub_modules
from imagecraft.pack.bootloader.const import ArchSpec, BootMethod, get_arch_spec
from imagecraft.pack.bootloader.efi import EfiInstaller
from imagecraft.pack.bootloader.mkconfig import generate_grub_cfg

AnyVolume = GPTVolume | MBRVolume | HybridVolume


class PrimeDirs(Protocol):
    """Minimal protocol for resolving partition prime directories."""

    def get_prime_dir(self, partition: str | None = None) -> Path:
        """Return the prime directory for the given partition."""
        ...


_DEFAULT_FSTAB_OPTIONS = "defaults,errors=remount-ro"


def configure_fstab(root_dir: Path, root_uuid: UUID | str) -> None:
    """Ensure /etc/fstab contains an entry for the root filesystem UUID.

    An existing non-comment root entry (e.g. ``LABEL=writable / ...``) is
    replaced rather than duplicated.
    """
    fstab_path = root_dir / "etc" / "fstab"
    fstab_path.parent.mkdir(parents=True, exist_ok=True)
    str_uuid = str(root_uuid)
    fstab_entry = f"UUID={str_uuid} / ext4 {_DEFAULT_FSTAB_OPTIONS} 0 1\n"

    if not fstab_path.is_file():
        content = "# /etc/fstab: static file system information.\n" + fstab_entry
        fstab_path.write_text(content)
        return

    existing_content = fstab_path.read_text()
    if str_uuid in existing_content:
        return

    lines = existing_content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        fields = line.split()
        if (
            fields
            and not line.lstrip().startswith("#")
            and len(fields) > 1
            and fields[1] == "/"
        ):
            lines[index] = fstab_entry
            fstab_path.write_text("".join(lines))
            return

    separator = "" if existing_content.endswith("\n") else "\n"
    fstab_path.write_text(existing_content + separator + fstab_entry)


class BootloaderInstaller:
    """Coordinates loopless GRUB installation for a single image volume."""

    def __init__(self, *, volume: AnyVolume, arch: DebianArchitecture | str) -> None:
        """Initialize the bootloader installer.

        :param volume: The volume layout being packed.
        :param arch: Target architecture (invalid or unsupported values
            disable bootloader installation).
        """
        self.volume = volume
        self.arch: DebianArchitecture | None
        self._spec: ArchSpec | None
        try:
            self.arch = (
                arch
                if isinstance(arch, DebianArchitecture)
                else DebianArchitecture(arch)
            )
            self._spec = get_arch_spec(self.arch)
        except ValueError:
            self.arch = None
            self._spec = None

        self.root_item = volume.root_partition
        self.esp_item = volume.esp_partition
        self.boot_item = volume.boot_partition
        self.root_uuid = uuid.uuid4()
        self.boot_uuid = uuid.uuid4() if self.boot_item is not None else None
        self._root_dir: Path | None = None

    @property
    def partition_uuids(self) -> dict[str, str]:
        """Map structure item names to the filesystem UUIDs to assign them."""
        uuids: dict[str, str] = {}
        if self.root_item is not None:
            uuids[self.root_item.name] = str(self.root_uuid)
        if self.boot_item is not None and self.boot_uuid is not None:
            uuids[self.boot_item.name] = str(self.boot_uuid)
        return uuids

    def resolve_boot_method(self) -> BootMethod:
        """Determine which boot method (if any) applies to this volume/arch."""
        if self.root_item is None:
            emit.progress(
                "Skipping bootloader installation because no data partition was found",
                permanent=True,
            )
            return BootMethod.NONE

        if self._spec is None:
            emit.progress(
                "Cannot install a bootloader for this architecture", permanent=True
            )
            return BootMethod.NONE

        if self.esp_item is not None:
            return BootMethod.EFI

        is_mbr_schema = self.volume.volume_schema == PartitionSchema.MBR
        if (
            is_mbr_schema or self.volume.has_bios_boot_partition
        ) and self._spec.non_efi_format is not None:
            return BootMethod.BIOS

        emit.progress(
            "Skipping bootloader installation because no suitable boot "
            "partition was found",
            permanent=True,
        )
        return BootMethod.NONE

    def _prime_dir(
        self, project_dirs: PrimeDirs, volume_name: str, item: StructureItem
    ) -> Path:
        return project_dirs.get_prime_dir(
            partition=get_partition_name(volume_name, item)
        )

    def prepare_rootfs(
        self, *, project_dirs: PrimeDirs, volume_name: str
    ) -> BootMethod:
        """Stage bootloader files into prime directories before formatting.

        :param project_dirs: The lifecycle's project directories.
        :param volume_name: Name of the volume being packed.
        :return: The boot method staged for (``BootMethod.NONE`` if skipped).
        """
        boot_method = self.resolve_boot_method()
        if boot_method == BootMethod.NONE:
            return boot_method
        # resolve_boot_method() only returns a non-NONE method when the arch
        # has a spec, so these are always safe here.
        assert self.arch is not None  # noqa: S101
        assert self._spec is not None  # noqa: S101
        assert self.root_item is not None  # noqa: S101

        self._root_dir = self._prime_dir(project_dirs, volume_name, self.root_item)
        esp_dir = (
            self._prime_dir(project_dirs, volume_name, self.esp_item)
            if self.esp_item is not None
            else None
        )
        boot_dir = (
            self._prime_dir(project_dirs, volume_name, self.boot_item)
            if self.boot_item is not None
            else None
        )

        emit.progress("Preparing bootloader files")
        configure_fstab(self._root_dir, self.root_uuid)
        partition_map = (
            "msdos" if self.volume.volume_schema == PartitionSchema.MBR else "gpt"
        )
        try:
            generate_grub_cfg(
                self._root_dir,
                self.root_uuid,
                boot_dir=boot_dir,
                boot_uuid=self.boot_uuid,
                partition_map=partition_map,
            )
        except errors.BootloaderToolsMissingError as err:
            emit.progress(f"Skipping bootloader installation: {err}", permanent=True)
            return BootMethod.NONE

        if boot_method == BootMethod.EFI:
            if esp_dir is None:
                emit.progress(
                    "Skipping EFI bootloader installation because no EFI "
                    "System Partition prime directory is available",
                    permanent=True,
                )
                return BootMethod.NONE
            try:
                EfiInstaller(
                    root_dir=self._root_dir,
                    esp_dir=esp_dir,
                    root_uuid=self.root_uuid,
                    arch=self.arch,
                    boot_dir=boot_dir,
                    boot_uuid=self.boot_uuid,
                ).install()
            except errors.BootloaderToolsMissingError as err:
                emit.progress(
                    f"Skipping EFI bootloader installation: {err}", permanent=True
                )
                return BootMethod.NONE
        elif boot_method == BootMethod.BIOS:
            # resolve_boot_method() only returns BIOS when a non-EFI target
            # exists for this architecture.
            assert self._spec.non_efi_format is not None  # noqa: S101
            try:
                stage_grub_modules(self._root_dir, boot_dir, self._spec.non_efi_format)
            except errors.BootloaderToolsMissingError as err:
                emit.progress(
                    f"Skipping BIOS bootloader installation: {err}", permanent=True
                )
                return BootMethod.NONE

        return boot_method

    def install_image_boot_code(self, *, image_path: Path) -> None:
        """Install BIOS boot code into the raw disk image, if applicable.

        No-op for non-BIOS volumes. Must be called after the image's
        partitions have been formatted and finalized, and after
        :meth:`prepare_rootfs`.

        :param image_path: Path to the final, partitioned disk image file.
        """
        if self.resolve_boot_method() != BootMethod.BIOS or self._root_dir is None:
            return
        # resolve_boot_method() only returns BIOS when the arch has a spec.
        assert self.arch is not None  # noqa: S101

        emit.progress("Installing BIOS bootloader into the image")
        try:
            PCBiosInstaller(
                image_path=image_path,
                root_dir=self._root_dir,
                root_uuid=self.root_uuid,
                arch=self.arch,
                volume=self.volume,
                boot_uuid=self.boot_uuid,
            ).install()
        except errors.BootloaderToolsMissingError as err:
            emit.progress(
                f"Skipping BIOS bootloader installation: {err}", permanent=True
            )
