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

"""FUSE partition and volume mounting utilities."""

import abc
import contextlib
import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Any

from craft_cli import emit

from imagecraft import errors
from imagecraft.errors import MountError
from imagecraft.models import (
    FileSystem,
    GPTVolume,
    PartitionSchema,
    Role,
    Volume,
)
from imagecraft.pack import gptutil
from imagecraft.subprocesses import run


def _try_fuse_command(command: Sequence[str], *, err_msg: str) -> None:
    """Run a FUSE helper command, wrapping failures in ``MountError``.

    :param command: The command and arguments to run.
    :param err_msg: Human-readable error message to raise on failure.
    :raises errors.MountError: If the command fails or the binary is missing.
    """
    try:
        run(*command)
    except subprocess.CalledProcessError as err:
        raise errors.MountError(
            f"{err_msg}: {err.stderr}",
            details=err.stderr,
        ) from err


def _unmount_path(
    target: Path,
    *,
    lazy: bool = False,
    prefer_fuse2: bool = False,
    retries: int = 1,
    err_msg: str = "Failed to unmount",
) -> None:
    """Unmount a FUSE mountpoint or virtual device file.

    Tries fusermount, fusermount3, and umount depending on prefer_fuse2.
    """
    fuser_args = ["-u"]
    if lazy:
        fuser_args.append("-z")
    fuser_args.append(str(target.resolve()))

    umount_args = ["-l", str(target.resolve())] if lazy else [str(target.resolve())]

    candidates = (
        ["fusermount", "fusermount3", "umount"]
        if prefer_fuse2
        else ["fusermount3", "fusermount", "umount"]
    )

    last_err: errors.MountError | None = None
    for _ in range(retries):
        for cmd in candidates:
            if shutil.which(cmd) is None:
                continue
            args = umount_args if cmd == "umount" else fuser_args
            try:
                _try_fuse_command([cmd, *args], err_msg=err_msg)
            except errors.MountError as err:
                last_err = err
            else:
                return
        time.sleep(0.1)

    if last_err is not None:
        raise last_err


class BaseMount(abc.ABC):
    """Abstract base class for all filesystem mounts.

    Subclasses implement mounting and unmounting of specific filesystems or virtual
    offset devices. Implements Python context manager protocol (__enter__/__exit__).
    """

    mountpoint: Path | None
    _temp_dir: tempfile.TemporaryDirectory[str] | None
    _is_mounted: bool

    def __init__(self, *, mountpoint: Path | None = None) -> None:
        self.mountpoint = mountpoint
        self._temp_dir = None
        self._is_mounted = False

    @property
    def is_mounted(self) -> bool:
        """Check if the filesystem is currently mounted."""
        return self._is_mounted

    def _ensure_mountpoint(self, prefix: str) -> Path:
        """Ensure mountpoint directory exists and return it as a Path."""
        if self.mountpoint is None:
            self._temp_dir = tempfile.TemporaryDirectory(prefix=prefix)
            self.mountpoint = Path(self._temp_dir.name)
        else:
            self.mountpoint.mkdir(parents=True, exist_ok=True)
        return self.mountpoint

    @abc.abstractmethod
    def mount(self) -> Path:
        """Mount the filesystem and return the mountpoint path.

        :raises errors.MountError: If mounting fails.
        """

    @abc.abstractmethod
    def unmount(self, *, lazy: bool = False) -> None:
        """Unmount the filesystem.

        :param lazy: If True, request lazy/detach unmount.
        :raises errors.MountError: If unmounting fails.
        """

    def __enter__(self) -> Path:
        """Enter context manager."""
        return self.mount()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager."""
        self.unmount()

    def _cleanup(self) -> None:
        """Reset mount state and remove the temporary mountpoint directory."""
        self._is_mounted = False
        if self._temp_dir is not None:
            with contextlib.suppress(Exception):
                self._temp_dir.cleanup()
            self._temp_dir = None
            self.mountpoint = None


class VirtualOffsetDevice(BaseMount):
    """Virtual partition device exposing a sub-slice of a disk image via fusefile.

    Used when mounting FAT filesystems with an offset > 0, as fusefat lacks native
    offset parameters.
    """

    disk_path: Path
    offset: int
    size: int
    part_file: Path | None

    def __init__(self, disk_path: Path, offset: int, size: int) -> None:
        super().__init__()
        self.disk_path = disk_path
        self.offset = offset
        self.size = size
        self.part_file = None

    def mount(self) -> Path:
        """Create the virtual file and mount the slice via fusefile.

        :raises errors.MountError: If mounting the virtual device fails.
        """
        if self._is_mounted and self.part_file is not None:
            return self.part_file

        self._temp_dir = tempfile.TemporaryDirectory(prefix="imagecraft-vpart-")
        self.part_file = Path(self._temp_dir.name) / "part.img"
        self.part_file.touch()

        spec = f"{self.disk_path.resolve()}/{self.offset}+{self.size}"
        emit.debug(f"Mounting virtual offset device {self.part_file} from {spec}")

        try:
            _try_fuse_command(
                ["fusefile", str(self.part_file), spec],
                err_msg="Failed to create virtual offset device with fusefile",
            )
        except errors.MountError:
            self._cleanup()
            raise

        self._is_mounted = True
        return self.part_file

    def unmount(self, *, lazy: bool = False) -> None:
        """Unmount the virtual device."""
        if not self._is_mounted or self.part_file is None:
            return

        part_file = self.part_file
        emit.debug(f"Unmounting virtual offset device {part_file}")
        try:
            _unmount_path(
                part_file,
                lazy=lazy,
                prefer_fuse2=True,
                retries=30,
                err_msg=f"Failed to unmount virtual offset device {part_file}",
            )
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        super()._cleanup()
        self.part_file = None


class ImageDevDir:
    """Expose all partitions from a disk image as files via fusefile.

    Creates and mounts device files that represent the partitions of a disk image
    in the given ``dev_dir``, replicating how the block devices would look in ``/dev``
    if they were on a real block device.
    """

    image_path: Path

    def __init__(self, *, image_path: Path, dev_dir: Path) -> None:
        self.image_path = image_path
        self.dev_dir = dev_dir
        self._is_mounted = False
        self.partition_table: dict[str, Any] | None = None
        self._remove_on_unmount: set[Path] = set()
        self._devices: dict[int | str | None, Path] | None = None

    @property
    def is_mounted(self) -> bool:
        """Check if the device directory is currently mounted."""
        return self._is_mounted

    def _reset_mount_state(self) -> None:
        """Reset internal mount bookkeeping without interacting with the system."""
        self._devices = None
        self.partition_table = None
        self._is_mounted = False
        self._remove_on_unmount.clear()

    def _create_device_file(self, path: Path) -> None:
        """Create an empty placeholder for a device file and track it for cleanup.

        :param path: The device file to create.
        :raises errors.MountError: If the path exists but is not a regular file,
            or if the file cannot be created.
        """
        if path.exists():
            if path.is_dir():
                raise errors.MountError(
                    f"Error creating device file {path}: path is a directory"
                )
            return
        try:
            path.touch()
        except OSError as err:
            raise errors.MountError(
                f"Error creating device file {path}: {err}"
            ) from err
        self._remove_on_unmount.add(path)

    def _unmount_device_file(self, path: Path) -> None:
        """Unmount a device file and remove it if we created it.

        Errors during unmount are suppressed; the caller decides whether to
        report accumulated failures.

        :param path: The device path to unmount.
        """
        with contextlib.suppress(errors.MountError):
            _unmount_path(path)
        if path in self._remove_on_unmount:
            with contextlib.suppress(OSError):
                path.unlink()
            self._remove_on_unmount.discard(path)

    def mount(self) -> dict[int | str | None, Path]:
        """Create and mount the files for the disk's partitions, including itself.

        :returns: A dictionary that maps the partition numbers and names to the
            device paths. The key ``None`` also maps to a bind-mounted form of the
            full image.
        :raises errors.MountError: If mounting has already happened or if any
            step of the mount process fails.
        """
        if self._devices is not None:
            raise MountError(f"{self.image_path} already mounted")
        self.partition_table = gptutil.get_partition_table(self.image_path)
        device_name: str = Path(self.partition_table["device"]).name
        sector_size = int(self.partition_table["sectorsize"])

        device_path = self.dev_dir / device_name
        self._create_device_file(device_path)
        try:
            _try_fuse_command(
                ["mount", "--bind", str(self.image_path), str(device_path)],
                err_msg=f"Error bind-mounting {self.image_path}",
            )
        except errors.MountError:
            self._cleanup_created_files()
            self._reset_mount_state()
            raise
        self._devices = {None: device_path}

        try:
            for part_num, partition in enumerate(
                self.partition_table["partitions"], start=1
            ):
                part_path = self.dev_dir / Path(partition["node"]).name
                self._create_device_file(part_path)
                part_start_bytes = partition["start"] * sector_size
                part_length_bytes = partition["size"] * sector_size
                fragment_str = (
                    f"{self.image_path}/{part_start_bytes}+{part_length_bytes}"
                )
                try:
                    _try_fuse_command(
                        ["fusefile", str(part_path), fragment_str],
                        err_msg=f"Error mounting partition {part_num} of {self.image_path}",
                    )
                except errors.MountError:
                    self._cleanup_created_files()
                    self._reset_mount_state()
                    raise
                self._devices[part_num] = self._devices[part_path.name] = part_path
        except errors.MountError:
            raise
        except Exception as err:
            self._cleanup_created_files()
            self._reset_mount_state()
            raise errors.MountError(
                f"Unexpected error while mounting {self.image_path}: {err}"
            ) from err

        self._is_mounted = True
        return self._devices

    def _cleanup_created_files(self) -> None:
        """Unmount and remove all tracked device files that still exist."""
        for path in list(self._remove_on_unmount):
            self._unmount_device_file(path)

    def unmount(self) -> None:
        """Unmount the fake dev directory.

        Any errors raised while unmounting individual devices are collected
        and re-raised after attempting to clean up everything else.

        :raises errors.MountError: If the directory is not mounted or if any
            unmount operation fails.
        """
        if self._devices is None:
            raise MountError(f"Not mounted: {self.image_path}")
        errors_encountered: list[errors.MountError] = []

        for idx, part_path in self._devices.items():
            # Partitions are keyed by both number and name; unmount each only once.
            if not isinstance(idx, int):
                continue
            try:
                _unmount_path(part_path)
            except errors.MountError as err:
                errors_encountered.append(err)
            if part_path in self._remove_on_unmount:
                try:
                    part_path.unlink()
                except OSError as err:
                    errors_encountered.append(
                        errors.MountError(
                            f"Failed to remove device file {part_path}: {err}"
                        )
                    )
                self._remove_on_unmount.discard(part_path)

        image_dev_path = self._devices[None]
        try:
            _unmount_path(image_dev_path)
        except errors.MountError as err:
            errors_encountered.append(err)

        for path in list(self._remove_on_unmount):
            try:
                _unmount_path(path)
            except errors.MountError as err:
                errors_encountered.append(err)
            try:
                path.unlink()
            except OSError as err:
                errors_encountered.append(
                    errors.MountError(f"Failed to remove device file {path}: {err}")
                )
            self._remove_on_unmount.discard(path)

        self._reset_mount_state()
        if errors_encountered:
            raise errors.MountError(
                f"Errors occurred while unmounting {self.image_path}: {errors_encountered}"
            )

    def __enter__(self) -> dict[int | str | None, Path]:
        """Enter context manager."""
        return self.mount()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager."""
        self.unmount()


class BasePartitionMount(BaseMount):
    """Abstract base class for FUSE partition mounts.

    :param imagepath: Path to the disk image or partition image.
    :param offset: Byte offset of the partition within the image (0 if standalone).
    :param mountpoint: Optional host directory mount point.
    :param read_only: If True, mount read-only.
    :param allow_other: If True, allow other users to access the mount.
    """

    imagepath: Path
    offset: int
    read_only: bool
    allow_other: bool

    def __init__(
        self,
        imagepath: Path,
        *,
        offset: int = 0,
        mountpoint: Path | None = None,
        read_only: bool = False,
        allow_other: bool = False,
    ) -> None:
        super().__init__(mountpoint=mountpoint)
        self.imagepath = imagepath
        self.offset = offset
        self.read_only = read_only
        self.allow_other = allow_other

    def _build_options(self, *, rw_flag: str = "rw") -> list[str]:
        """Build common FUSE mount options."""
        options = ["ro"] if self.read_only else [rw_flag]
        if self.allow_other:
            options.append("allow_other")
        return options

    def unmount(self, *, lazy: bool = False) -> None:
        """Unmount the partition."""
        if not self.is_mounted or self.mountpoint is None:
            return

        mountpoint = self.mountpoint
        emit.debug(f"Unmounting partition at {mountpoint}")
        try:
            _unmount_path(
                mountpoint,
                lazy=lazy,
                retries=10,
                err_msg=f"Failed to unmount partition at {mountpoint}",
            )
        finally:
            self._cleanup()


class ExtFuseMount(BasePartitionMount):
    """Mount an ext2/ext3/ext4 partition using fuse2fs.

    :param imagepath: Path to the disk image or partition image.
    :param offset: Byte offset of the partition within the image (0 if standalone).
    :param mountpoint: Optional host directory mount point.
    :param read_only: If True, mount read-only.
    :param allow_other: If True, allow other users to access the mount.
    :param fakeroot: If True, pass fakeroot option to fuse2fs.
    """

    fakeroot: bool

    def __init__(
        self,
        imagepath: Path,
        *,
        offset: int = 0,
        mountpoint: Path | None = None,
        read_only: bool = False,
        allow_other: bool = False,
        fakeroot: bool = False,
    ) -> None:
        super().__init__(
            imagepath,
            offset=offset,
            mountpoint=mountpoint,
            read_only=read_only,
            allow_other=allow_other,
        )
        self.fakeroot = fakeroot

    def mount(self) -> Path:
        """Mount the ext partition using fuse2fs."""
        if self.is_mounted and self.mountpoint is not None:
            return self.mountpoint

        mountpoint = self._ensure_mountpoint("imagecraft-ext-mount-")

        options = self._build_options(rw_flag="rw")
        if self.offset > 0:
            options.insert(0, f"offset={self.offset}")
        if self.fakeroot:
            options.append("fakeroot")

        cmd = [
            "fuse2fs",
            "-o",
            ",".join(options),
            str(self.imagepath.resolve()),
            str(mountpoint.resolve()),
        ]

        emit.debug(f"Mounting ext partition with: {cmd}")
        try:
            _try_fuse_command(
                cmd,
                err_msg=f"Failed to mount ext partition {self.imagepath} at {mountpoint}",
            )
        except errors.MountError:
            self._cleanup()
            raise

        self._is_mounted = True
        return mountpoint


class FatFuseMount(BasePartitionMount):
    """Mount a FAT16/FAT32/VFAT partition using fusefat.

    :param imagepath: Path to the disk image or partition image.
    :param offset: Byte offset of the partition within the image (0 if standalone).
    :param size: Byte size of the partition (required if offset > 0).
    :param mountpoint: Optional host directory mount point.
    :param read_only: If True, mount read-only.
    :param allow_other: If True, allow other users to access the mount.
    """

    size: int | None
    _vpart: VirtualOffsetDevice | None

    def __init__(
        self,
        imagepath: Path,
        *,
        offset: int = 0,
        size: int | None = None,
        mountpoint: Path | None = None,
        read_only: bool = False,
        allow_other: bool = False,
    ) -> None:
        super().__init__(
            imagepath,
            offset=offset,
            mountpoint=mountpoint,
            read_only=read_only,
            allow_other=allow_other,
        )
        self.size = size
        self._vpart = None

    def mount(self) -> Path:
        """Mount the FAT partition using fusefat."""
        if self.is_mounted and self.mountpoint is not None:
            return self.mountpoint

        mountpoint = self._ensure_mountpoint("imagecraft-fat-mount-")

        target_file: Path
        if self.offset > 0:
            if self.size is None:
                raise errors.MountError(
                    "Partition size must be specified when offset > 0 for FAT partition."
                )
            self._vpart = VirtualOffsetDevice(self.imagepath, self.offset, self.size)
            target_file = self._vpart.mount()
        else:
            target_file = self.imagepath

        options = self._build_options(rw_flag="rw+")
        cmd = [
            "fusefat",
            "-o",
            ",".join(options),
            str(target_file.resolve()),
            str(mountpoint.resolve()),
        ]

        emit.debug(f"Mounting FAT partition with: {cmd}")
        try:
            _try_fuse_command(
                cmd,
                err_msg=f"Failed to mount FAT partition {self.imagepath} at {mountpoint}",
            )
        except errors.MountError:
            if self._vpart is not None:
                with contextlib.suppress(Exception):
                    self._vpart.unmount()
                self._vpart = None
            self._cleanup()
            raise

        self._is_mounted = True
        return mountpoint

    def unmount(self, *, lazy: bool = False) -> None:
        """Unmount the FAT partition and its virtual offset device if used."""
        err_mount: Exception | None = None
        try:
            super().unmount(lazy=lazy)
        except errors.MountError as err:
            err_mount = err
        finally:
            if self._vpart is not None:
                try:
                    self._vpart.unmount(lazy=lazy)
                except Exception as err_vpart:  # noqa: BLE001
                    if err_mount is None:
                        err_mount = err_vpart
                finally:
                    self._vpart = None

        if err_mount is not None:
            raise err_mount


def mount_partition(
    imagepath: Path,
    filesystem: FileSystem | str,
    *,
    offset: int = 0,
    size: int | None = None,
    mountpoint: Path | None = None,
    read_only: bool = False,
    allow_other: bool = False,
    fakeroot: bool = False,
) -> BaseMount:
    """Create the appropriate BaseMount instance for a partition.

    :param imagepath: Path to the disk image or partition image.
    :param filesystem: Filesystem type (e.g. ext4, fat32, vfat).
    :param offset: Byte offset within the disk image.
    :param size: Byte size of the partition (required for FAT when offset > 0).
    :param mountpoint: Optional host mountpoint path.
    :param read_only: If True, mount read-only.
    :param allow_other: If True, pass allow_other option to FUSE.
    :param fakeroot: If True, pass fakeroot option to FUSE (ext only).
    :raises errors.MountError: If the filesystem type is unsupported.
    """
    fs_str = (
        filesystem.value.lower()
        if isinstance(filesystem, FileSystem)
        else str(filesystem).lower()
    )
    if fs_str in ("ext2", "ext3", "ext4"):
        return ExtFuseMount(
            imagepath,
            offset=offset,
            mountpoint=mountpoint,
            read_only=read_only,
            allow_other=allow_other,
            fakeroot=fakeroot,
        )
    if fs_str in ("fat16", "fat32", "vfat"):
        return FatFuseMount(
            imagepath,
            offset=offset,
            size=size,
            mountpoint=mountpoint,
            read_only=read_only,
            allow_other=allow_other,
        )
    raise errors.MountError(f"Unsupported filesystem for mounting: {filesystem}")


class CompositeMount(BaseMount):
    """Hierarchical composite mount managing multiple nested partition mounts.

    :param mounts: Sequence of (relative_mountpoint_str, mount_instance) pairs.
        The root filesystem should have relative mountpoint "" or "/".
    :param mountpoint: Optional base host directory to mount under.
    """

    _mount_entries: list[tuple[str, BaseMount]]
    _mounted_stack: list[BaseMount]

    def __init__(
        self,
        mounts: Sequence[tuple[str, BaseMount]],
        mountpoint: Path | None = None,
    ) -> None:
        super().__init__(mountpoint=mountpoint)
        self._mount_entries = list(mounts)
        self._mounted_stack = []

    def mount(self) -> Path:
        """Mount all sub-mounts in topological order (root to leaf)."""
        if self.is_mounted and self.mountpoint is not None:
            return self.mountpoint

        mountpoint = self._ensure_mountpoint("imagecraft-composite-mount-")
        sorted_entries = sorted(
            self._mount_entries,
            key=lambda item: len(Path(item[0].strip("/")).parts),
        )

        try:
            for rel_path_str, mount_obj in sorted_entries:
                rel_path = rel_path_str.strip("/")
                target_dir = mountpoint / rel_path if rel_path else mountpoint
                target_dir.mkdir(parents=True, exist_ok=True)
                mount_obj.mountpoint = target_dir
                mount_obj.mount()
                self._mounted_stack.append(mount_obj)
        except Exception as err:
            self.unmount()
            raise errors.MountError(
                f"Failed to mount composite mount hierarchy: {err}"
            ) from err

        self._is_mounted = True
        return mountpoint

    def unmount(self, *, lazy: bool = False) -> None:
        """Unmount all sub-mounts in reverse topological order (leaf to root)."""
        errors_encountered: list[Exception] = []
        while self._mounted_stack:
            try:
                self._mounted_stack.pop().unmount(lazy=lazy)
            except Exception as err:  # noqa: BLE001, PERF203
                errors_encountered.append(err)

        self._cleanup()
        if errors_encountered:
            raise errors.MountError(
                f"Errors occurred during composite unmount: {errors_encountered}"
            )


_DEFAULT_ROLE_MOUNTS: dict[Role, str] = {
    Role.SYSTEM_DATA: "",
    Role.SYSTEM_BOOT: "boot/efi",
    Role.SYSTEM_SEED: "var/lib/snapd/seed",
}


def mount_volume(
    volume: Volume,
    disk_path: Path,
    *,
    mountpoint_overrides: dict[str, str] | None = None,
    mountpoint: Path | None = None,
    read_only: bool = False,
    allow_other: bool = False,
    fakeroot: bool = False,
) -> CompositeMount:
    """Mount all filesystems in a Volume as a composite tree.

    :param volume: Volume definition containing partition structures.
    :param disk_path: Path to the disk image.
    :param mountpoint_overrides: Mapping from structure names to relative
        mount paths inside the mounted root.
    :param mountpoint: Optional host mountpoint path.
    :param read_only: If True, mount all partitions read-only.
    :param allow_other: If True, pass allow_other option to all mounts.
    :param fakeroot: If True, pass fakeroot option to ext mounts.
    :returns: A CompositeMount managing all partition mounts.
    """
    mountpoint_overrides = mountpoint_overrides or {}
    mount_entries: list[tuple[str, BaseMount]] = []

    is_gpt = (
        isinstance(volume, GPTVolume)
        or getattr(volume, "volume_schema", None) == PartitionSchema.GPT
    )

    for idx, item in enumerate(volume.structure, start=1):
        filesystem = getattr(item, "filesystem", None)
        if not filesystem:
            continue

        rel_path = mountpoint_overrides.get(
            item.name,
            _DEFAULT_ROLE_MOUNTS.get(item.role, f"mnt/{item.name}"),
        )

        # Calculate byte offset and size
        if is_gpt:
            start_sector = gptutil.get_partition_sector_offset(disk_path, item.name)
            size_sectors = gptutil.get_partition_size_sectors(disk_path, item.name)
        else:
            start_sector = gptutil.get_partition_sector_offset_by_number(disk_path, idx)
            size_sectors = gptutil.get_partition_size_sectors_by_number(disk_path, idx)

        part_mount = mount_partition(
            disk_path,
            filesystem,
            offset=start_sector * gptutil.SECTOR_SIZE_512,
            size=size_sectors * gptutil.SECTOR_SIZE_512,
            read_only=read_only,
            allow_other=allow_other,
            fakeroot=fakeroot,
        )
        mount_entries.append((rel_path, part_mount))

    return CompositeMount(mounts=mount_entries, mountpoint=mountpoint)
