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

import re
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from craft_cli import emit
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models import get_partition_name
from imagecraft.models.project import FilesystemsDictT
from imagecraft.models.volume import (
    FileSystem,
    GptType,
    GPTVolume,
    HybridVolume,
    MBRVolume,
    PartitionSchema,
    StructureItem,
)
from imagecraft.pack.bootloader.bios import PCBiosInstaller
from imagecraft.pack.bootloader.staging import stage_grub_modules
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

_FAT_FILESYSTEMS = (FileSystem.VFAT, FileSystem.FAT16)


def _is_esp_item(item: StructureItem | None) -> bool:
    """Whether a structure item is an EFI System Partition."""
    structure_type = getattr(item, "structure_type", None)
    if isinstance(structure_type, GptType):
        return structure_type == GptType.EFI_SYSTEM
    if isinstance(structure_type, str) and "," in structure_type:
        return structure_type.split(",", 1)[1].upper() == GptType.EFI_SYSTEM.value
    return False


def _new_filesystem_id(filesystem: FileSystem) -> str:
    """Generate a filesystem ID assignable at format time.

    FAT filesystems carry a 32-bit volume serial that GRUB probes as
    ``XXXX-XXXX``; other filesystems take a regular UUID.
    """
    if filesystem in _FAT_FILESYSTEMS:
        hex_id = uuid4().hex[:8].upper()
        return f"{hex_id[:4]}-{hex_id[4:]}"
    return str(uuid4())


def configure_fstab(
    root_dir: Path,
    filesystem_uuid: UUID | str,
    *,
    mountpoint: str = "/",
    filesystem: FileSystem = FileSystem.EXT4,
) -> None:
    """Add or update a filesystem's UUID entry in /etc/fstab.

    Preserve the other fields of an existing entry.
    """
    fstab_path = root_dir / "etc" / "fstab"
    fstab_path.parent.mkdir(parents=True, exist_ok=True)
    str_uuid = str(filesystem_uuid)
    is_root = mountpoint == "/"
    filesystem_type = "vfat" if filesystem in _FAT_FILESYSTEMS else filesystem.value
    options = (
        _DEFAULT_FSTAB_OPTIONS
        if is_root and filesystem not in _FAT_FILESYSTEMS
        else "defaults"
    )
    fstab_entry = (
        f"UUID={str_uuid} {mountpoint} {filesystem_type} {options} 0 "
        f"{1 if is_root else 2}\n"
    )

    if not fstab_path.is_file():
        content = "# /etc/fstab: static file system information.\n" + fstab_entry
        fstab_path.write_text(content)
        return

    existing_content = fstab_path.read_text()
    lines = existing_content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        fields = line.split()
        if (
            not line.lstrip().startswith("#")
            and len(fields) > 1
            and Path(fields[1]) == Path(mountpoint)
        ):
            lines[index] = re.sub(r"\S+", f"UUID={str_uuid}", line, count=1)
            break
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(fstab_entry)

    fstab_path.write_text("".join(lines))


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
        self.root_uuid: str = (
            _new_filesystem_id(self.root_item.filesystem)
            if self.root_item is not None
            else str(uuid4())
        )
        self.boot_uuid: str | None = (
            _new_filesystem_id(self.boot_item.filesystem)
            if self.boot_item is not None
            else None
        )
        self._root_dir: Path | None = None
        self._boot_method = BootMethod.NONE

    @property
    def partition_uuids(self) -> dict[str, str]:
        """Map structure item names to the filesystem UUIDs to assign them."""
        uuids: dict[str, str] = {}
        if self.root_item is not None:
            uuids[self.root_item.name] = str(self.root_uuid)
        if self.boot_item is not None:
            uuids[self.boot_item.name] = str(self.boot_uuid)
        return uuids

    def resolve_boot_method(self) -> BootMethod:
        """Determine which boot method (if any) applies to this volume/arch."""
        if self.root_item is None:
            emit.warning(
                "Skipping bootloader installation because no data partition was found",
                prefix="",
            )
            return BootMethod.NONE

        if self._spec is None:
            emit.warning(
                "Cannot install a bootloader for this architecture",
                prefix="",
            )
            return BootMethod.NONE

        if self.esp_item is not None:
            return BootMethod.EFI

        if (
            self.volume.volume_schema == PartitionSchema.MBR
            or self.volume.has_bios_boot_partition
        ) and self._spec.non_efi_format is not None:
            return BootMethod.BIOS

        emit.warning(
            "Skipping bootloader installation because no suitable boot "
            "partition was found",
            prefix="",
        )
        return BootMethod.NONE

    def _prime_dir(
        self, project_dirs: PrimeDirs, volume_name: str, item: StructureItem | None
    ) -> Path | None:
        if item is None:
            return None
        return project_dirs.get_prime_dir(
            partition=get_partition_name(volume_name, item)
        )

    def _mounted_item(
        self, filesystems: FilesystemsDictT, volume_name: str, mountpoint: str
    ) -> StructureItem | None:
        """Return the structure item mounted at mountpoint for this volume."""
        for entry in filesystems.get("default", []):
            if Path(entry["mount"]) != Path(mountpoint):
                continue
            device = str(entry["device"]).strip("()")
            return next(
                (
                    item
                    for item in self.volume.structure
                    if get_partition_name(volume_name, item) == device
                ),
                None,
            )
        return None

    def _resolve_mapped_items(
        self, filesystems: FilesystemsDictT, volume_name: str
    ) -> None:
        """Resolve the staged root and dedicated /boot items from mount mappings."""
        root_item = self._mounted_item(filesystems, volume_name, "/")
        if root_item is not None and root_item is not self.root_item:
            self.root_item = root_item
            self.root_uuid = _new_filesystem_id(root_item.filesystem)

        boot_item = self._mounted_item(filesystems, volume_name, "/boot")
        if boot_item is None or boot_item is self.root_item or boot_item is self.esp_item:
            self.boot_item = None
            self.boot_uuid = None
        elif boot_item is not self.boot_item:
            self.boot_item = boot_item
            self.boot_uuid = _new_filesystem_id(boot_item.filesystem)

        if any(
            Path(entry["mount"]) == Path("/boot/efi")
            for entry in filesystems.get("default", [])
        ):
            esp_item = self._mounted_item(filesystems, volume_name, "/boot/efi")
            self.esp_item = esp_item if _is_esp_item(esp_item) else None

    def prepare_rootfs(
        self,
        *,
        project_dirs: PrimeDirs,
        volume_name: str,
        filesystems: FilesystemsDictT,
    ) -> BootMethod:
        """Stage bootloader files into prime directories before formatting.

        :param project_dirs: The lifecycle's project directories.
        :param volume_name: Name of the volume being packed.
        :param filesystems: Project partition mount mappings.
        :return: The boot method staged for (``BootMethod.NONE`` if skipped).
        """
        self._resolve_mapped_items(filesystems, volume_name)
        boot_method = self.resolve_boot_method()
        if boot_method == BootMethod.NONE:
            return boot_method
        # resolve_boot_method() only returns a non-NONE method when the arch
        # has a spec, so these are always safe here.
        assert self.arch is not None  # noqa: S101
        assert self._spec is not None  # noqa: S101
        assert self.root_item is not None  # noqa: S101

        root_dir = self._prime_dir(project_dirs, volume_name, self.root_item)
        assert root_dir is not None  # noqa: S101
        self._root_dir = root_dir
        esp_dir = self._prime_dir(project_dirs, volume_name, self.esp_item)
        boot_dir = self._prime_dir(project_dirs, volume_name, self.boot_item)

        if boot_method == BootMethod.EFI and esp_dir is None:
            emit.warning(
                "Skipping EFI bootloader installation because no EFI "
                "System Partition prime directory is available",
                prefix="",
            )
            return BootMethod.NONE

        emit.progress("Preparing bootloader files")
        configure_fstab(
            self._root_dir, self.root_uuid, filesystem=self.root_item.filesystem
        )
        if self.boot_item is not None:
            assert self.boot_uuid is not None  # noqa: S101
            configure_fstab(
                self._root_dir,
                self.boot_uuid,
                mountpoint="/boot",
                filesystem=self.boot_item.filesystem,
            )
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
            if boot_method == BootMethod.EFI:
                assert esp_dir is not None  # noqa: S101
                EfiInstaller(
                    root_dir=self._root_dir,
                    esp_dir=esp_dir,
                    root_uuid=self.root_uuid,
                    arch=self.arch,
                    boot_dir=boot_dir,
                    boot_uuid=self.boot_uuid,
                ).install()
            elif boot_method == BootMethod.BIOS:
                # resolve_boot_method() only returns BIOS when a non-EFI
                # target exists for this architecture.
                assert self._spec.non_efi_format is not None  # noqa: S101
                stage_grub_modules(self._root_dir, boot_dir, self._spec.non_efi_format)
        except errors.BootloaderToolsMissingError as err:
            emit.warning(f"Skipping bootloader installation: {err}", prefix="")
            return BootMethod.NONE

        self._boot_method = boot_method
        return boot_method

    def install_image_boot_code(self, *, image_path: Path) -> None:
        """Install BIOS boot code into the raw disk image, if applicable.

        No-op for non-BIOS volumes. Must be called after the image's
        partitions have been formatted and finalized, and after
        :meth:`prepare_rootfs`.

        :param image_path: Path to the final, partitioned disk image file.
        """
        if self._boot_method != BootMethod.BIOS:
            return
        # prepare_rootfs() sets _root_dir before _boot_method becomes BIOS.
        assert self._root_dir is not None  # noqa: S101
        assert self.arch is not None  # noqa: S101

        emit.progress("Installing BIOS bootloader into the image")
        try:
            PCBiosInstaller(
                image_path=image_path,
                root_dir=self._root_dir,
                root_uuid=self.root_uuid,
                root_item=self.root_item,
                arch=self.arch,
                volume=self.volume,
                boot_uuid=self.boot_uuid,
                boot_item=self.boot_item,
            ).install()
        except errors.BootloaderToolsMissingError as err:
            emit.warning(
                f"Skipping BIOS bootloader installation: {err}", prefix=""
            )
