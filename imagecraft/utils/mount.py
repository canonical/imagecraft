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

from craft_cli import emit

from imagecraft import errors
from imagecraft.models import (
    FileSystem,
    GPTVolume,
    PartitionSchema,
    Role,
    Volume,
)
from imagecraft.pack import gptutil
from imagecraft.subprocesses import run


def _unmount_path(
    target: Path,
    *,
    lazy: bool = False,
    prefer_fuse2: bool = False,
    retries: int = 1,
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

    last_err: Exception | None = None
    for _ in range(retries):
        for cmd in candidates:
            if shutil.which(cmd) is None:
                continue
            args = umount_args if cmd == "umount" else fuser_args
            try:
                run(cmd, *args)
            except (subprocess.CalledProcessError, FileNotFoundError) as err:
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

    @property
    def _mountpoint(self) -> Path | None:
        """Alias for mountpoint property for internal consistency."""
        return self.mountpoint

    @_mountpoint.setter
    def _mountpoint(self, value: Path | None) -> None:
        self.mountpoint = value

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


class VirtualOffsetDevice:
    """Virtual partition device exposing a sub-slice of a disk image via fusefile.

    Used when mounting FAT filesystems with an offset > 0, as fusefat lacks native
    offset parameters.
    """

    disk_path: Path
    offset: int
    size: int
    part_file: Path | None
    _temp_dir: tempfile.TemporaryDirectory[str] | None
    _is_mounted: bool

    def __init__(self, disk_path: Path, offset: int, size: int) -> None:
        self.disk_path = disk_path
        self.offset = offset
        self.size = size
        self.part_file = None
        self._temp_dir = None
        self._is_mounted = False

    @property
    def is_mounted(self) -> bool:
        """Check if the virtual device is mounted."""
        return self._is_mounted

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
            run("fusefile", str(self.part_file), spec)
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            self._cleanup()
            raise errors.MountError(
                f"Failed to create virtual offset device with fusefile: {err}"
            ) from err

        self._is_mounted = True
        return self.part_file

    def unmount(self, *, lazy: bool = False) -> None:
        """Unmount the virtual device."""
        if not self._is_mounted or self.part_file is None:
            return

        part_file = self.part_file
        emit.debug(f"Unmounting virtual offset device {part_file}")
        try:
            _unmount_path(part_file, lazy=lazy, prefer_fuse2=True, retries=30)
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            raise errors.MountError(
                f"Failed to unmount virtual offset device {part_file}: {err}"
            ) from err
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        self._is_mounted = False
        self.part_file = None
        if self._temp_dir is not None:
            with contextlib.suppress(Exception):
                self._temp_dir.cleanup()
            self._temp_dir = None

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


class ExtFuseMount(BaseMount):
    """Mount an ext2/ext3/ext4 partition using fuse2fs.

    :param imagepath: Path to the disk image or partition image.
    :param offset: Byte offset of the partition within the image (0 if standalone).
    :param mountpoint: Optional host directory mount point.
    :param read_only: If True, mount read-only.
    :param allow_other: If True, allow other users to access the mount.
    :param fakeroot: If True, pass fakeroot option to fuse2fs.
    """

    imagepath: Path
    offset: int
    read_only: bool
    allow_other: bool
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
        super().__init__(mountpoint=mountpoint)
        self.imagepath = imagepath
        self.offset = offset
        self.read_only = read_only
        self.allow_other = allow_other
        self.fakeroot = fakeroot

    def mount(self) -> Path:
        """Mount the ext partition using fuse2fs."""
        if self.is_mounted and self.mountpoint is not None:
            return self.mountpoint

        mountpoint = self._ensure_mountpoint("imagecraft-ext-mount-")

        options: list[str] = []
        if self.offset > 0:
            options.append(f"offset={self.offset}")
        if self.read_only:
            options.append("ro")
        else:
            options.append("rw")
        if self.allow_other:
            options.append("allow_other")
        if self.fakeroot:
            options.append("fakeroot")

        cmd: list[str] = ["fuse2fs"]
        if options:
            cmd.extend(["-o", ",".join(options)])
        cmd.extend([str(self.imagepath.resolve()), str(mountpoint.resolve())])

        emit.debug(f"Mounting ext partition with: {cmd}")
        try:
            run(*cmd)
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            self._cleanup()
            raise errors.MountError(
                f"Failed to mount ext partition {self.imagepath} at {mountpoint}: {err}"
            ) from err

        self._is_mounted = True
        return mountpoint

    def unmount(self, *, lazy: bool = False) -> None:
        """Unmount the ext partition."""
        if not self.is_mounted or self._mountpoint is None:
            return

        mountpoint = self._mountpoint
        emit.debug(f"Unmounting ext partition at {mountpoint}")
        try:
            _unmount_path(mountpoint, lazy=lazy, retries=10)
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            raise errors.MountError(
                f"Failed to unmount ext partition at {mountpoint}: {err}"
            ) from err
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        self._is_mounted = False
        if self._temp_dir is not None:
            with contextlib.suppress(Exception):
                self._temp_dir.cleanup()
            self._temp_dir = None
            self._mountpoint = None


class FatFuseMount(BaseMount):
    """Mount a FAT16/FAT32/VFAT partition using fusefat.

    :param imagepath: Path to the disk image or partition image.
    :param offset: Byte offset of the partition within the image (0 if standalone).
    :param size: Byte size of the partition (required if offset > 0).
    :param mountpoint: Optional host directory mount point.
    :param read_only: If True, mount read-only.
    :param allow_other: If True, allow other users to access the mount.
    """

    imagepath: Path
    offset: int
    size: int | None
    read_only: bool
    allow_other: bool
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
        super().__init__(mountpoint=mountpoint)
        self.imagepath = imagepath
        self.offset = offset
        self.size = size
        self.read_only = read_only
        self.allow_other = allow_other
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

        options = ["ro"] if self.read_only else ["rw+"]
        if self.allow_other:
            options.append("allow_other")

        cmd = [
            "fusefat",
            "-o",
            ",".join(options),
            str(target_file.resolve()),
            str(mountpoint.resolve()),
        ]

        emit.debug(f"Mounting FAT partition with: {cmd}")
        try:
            run(*cmd)
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            if self._vpart is not None:
                with contextlib.suppress(Exception):
                    self._vpart.unmount()
                self._vpart = None
            self._cleanup()
            raise errors.MountError(
                f"Failed to mount FAT partition {self.imagepath} at {mountpoint}: {err}"
            ) from err

        self._is_mounted = True
        return mountpoint

    def unmount(self, *, lazy: bool = False) -> None:
        """Unmount the FAT partition and its virtual offset device if used."""
        if not self.is_mounted or self._mountpoint is None:
            return

        mountpoint = self._mountpoint
        emit.debug(f"Unmounting FAT partition at {mountpoint}")
        err_mount: Exception | None = None
        try:
            _unmount_path(mountpoint, lazy=lazy, retries=10)
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
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
            self._cleanup()

        if err_mount is not None:
            raise errors.MountError(
                f"Failed to unmount FAT partition at {mountpoint}: {err_mount}"
            ) from err_mount

    def _cleanup(self) -> None:
        self._is_mounted = False
        if self._temp_dir is not None:
            with contextlib.suppress(Exception):
                self._temp_dir.cleanup()
            self._temp_dir = None
            self._mountpoint = None


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
    if isinstance(filesystem, FileSystem):
        fs_str = filesystem.value.lower()
    else:
        fs_str = str(filesystem).lower()
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
            key=lambda item: (
                len(Path(item[0].strip("/")).parts) if item[0].strip("/") else 0
            ),
        )

        try:
            for rel_path_str, mount_obj in sorted_entries:
                rel_path = rel_path_str.strip("/")
                target_dir = mountpoint if not rel_path else mountpoint / rel_path
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
            mount_obj = self._mounted_stack.pop()
            try:
                mount_obj.unmount(lazy=lazy)
            except Exception as err:  # noqa: BLE001
                errors_encountered.append(err)

        self._is_mounted = False
        if self._temp_dir is not None:
            with contextlib.suppress(Exception):
                self._temp_dir.cleanup()
            self._temp_dir = None
            self._mountpoint = None

        if errors_encountered:
            raise errors.MountError(
                f"Errors occurred during composite unmount: {errors_encountered}"
            )


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

        # Determine relative mount path
        rel_path: str
        if item.name in mountpoint_overrides:
            rel_path = mountpoint_overrides[item.name]
        elif item.role == Role.SYSTEM_DATA:
            rel_path = ""
        elif item.role == Role.SYSTEM_BOOT:
            rel_path = "boot/efi"
        elif item.role == Role.SYSTEM_SEED:
            rel_path = "var/lib/snapd/seed"
        else:
            rel_path = f"mnt/{item.name}"

        # Calculate byte offset and size
        if is_gpt:
            start_sector = gptutil.get_partition_sector_offset(disk_path, item.name)
            size_sectors = gptutil.get_partition_size_sectors(disk_path, item.name)
        else:
            start_sector = gptutil.get_partition_sector_offset_by_number(disk_path, idx)
            size_sectors = gptutil.get_partition_size_sectors_by_number(disk_path, idx)

        offset_bytes = start_sector * gptutil.SECTOR_SIZE_512
        size_bytes = size_sectors * gptutil.SECTOR_SIZE_512

        part_mount = mount_partition(
            disk_path,
            filesystem,
            offset=offset_bytes,
            size=size_bytes,
            read_only=read_only,
            allow_other=allow_other,
            fakeroot=fakeroot,
        )
        mount_entries.append((rel_path, part_mount))

    return CompositeMount(mounts=mount_entries, mountpoint=mountpoint)
