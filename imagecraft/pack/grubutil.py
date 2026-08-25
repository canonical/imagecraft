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

Installs and configures GRUB for EFI-capable (GPT/hybrid) images directly
against a raw disk image, without attaching loop devices, chrooting, or
spinning up a VM. This lets imagecraft build images in unprivileged
containers that can't do any of those things.

For EFI images, this module:

- Builds GRUB boot images with ``grub-mkimage`` (or deploys Ubuntu's
  pre-signed Secure Boot shim/GRUB, when available) and writes them straight
  into the EFI System Partition.
- Writes GRUB runtime assets and ``grub.cfg`` into the ext4 boot partition.

Ext partitions are accessed through the FUSE mounts provided by
:mod:`imagecraft.utils.mount`, which expose a partition of a raw disk image
as a regular directory. The ESP is written in place with ``mtools``.

Legacy BIOS/MBR images still take the original privileged path, installing
GRUB with ``grub-install`` inside a chroot over a loop device. They are
converted to direct disk image manipulation in a follow-up change, after
which the chroot machinery is removed entirely.
"""

import contextlib
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import NamedTuple, cast

from craft_cli import emit
from craft_parts.filesystem_mounts import FilesystemMount
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models.volume import (
    MBRStructureItem,
    PartitionSchema,
    StructureList,
)
from imagecraft.pack import gptutil, mbrutil
from imagecraft.pack.image import Image
from imagecraft.subprocesses import run
from imagecraft.utils.mount import mount_partition

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
    # Ubuntu's 10_linux always emits "insmod gzio"; compressed kernels and
    # initrds are unreadable without it.
    "gzio",
]

# Signed shim/grub filename suffixes, in preference order.
# Core modules embedded into the standalone GRUB BIOS image.
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

# Layout of GRUB's boot.img loaded by a legacy BIOS:
_BIOS_KERNEL_SECTOR_OFFSET = 0x5C  # absolute sector of core.img (kernel)
_BIOS_BOOT_CODE_SIZE = 0x1B8  # boot code length before the disk signature
_BIOS_CORE_IMG_START_SECTOR = 4  # first sector of the MBR gap we may use
# Offset of core.img's embedded blocklist start sector inside diskboot.img.
_BIOS_BLOCKLIST_START_OFFSET = 0x1F4

_SIGNED_SHIM_SUFFIXES = (".efi.signed.latest", ".efi.signed", ".efi.dualsigned")

_DEFAULT_GRUB_PATH = "/etc/default/grub"

# Split a filename into digit and non-digit runs, so versions compare
# numerically rather than lexicographically.
_VERSION_PART_RE = re.compile(r"(\d+)")

# Match the shell assignments in /etc/default/grub that carry kernel
# arguments, with an optionally quoted value. Commented-out lines are skipped.
_GRUB_CMDLINE_RE = re.compile(
    r"^[ \t]*(?:export[ \t]+)?"
    r"(?P<key>GRUB_CMDLINE_LINUX(?:_DEFAULT)?|GRUB_TIMEOUT)="
    r"""(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)'|(?P<bare>[^\s#]*))""",
    re.MULTILINE,
)
# A reference to one of the keys above, which shell would have expanded when
# it sourced the file: `GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX foo"`.
_GRUB_VAR_REF_RE = re.compile(r"\$\{?(GRUB_CMDLINE_LINUX(?:_DEFAULT)?|GRUB_TIMEOUT)\}?")
# A shell line continuation, which joins the next line onto this one.
_LINE_CONTINUATION_RE = re.compile(r"\\\n")

_DEFAULT_GRUB_TIMEOUT = 5


class GrubDefaults(NamedTuple):
    """The subset of ``/etc/default/grub`` that the generated config honours."""

    cmdline: str = ""
    timeout: int = _DEFAULT_GRUB_TIMEOUT


_STOCK_GRUB_DEFAULTS = GrubDefaults()


def setup_grub(
    image: Image,
    workdir: Path,  # noqa: ARG001 (kept for caller compatibility)
    arch: str,
    filesystem_mount: FilesystemMount,
) -> None:
    """Set up GRUB directly on the disk image.

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
        # Legacy BIOS/MBR images are still installed through a loop device
        # and a chroot. They move over to direct image manipulation in a
        # follow-up change, once the EFI path has settled.
        _setup_grub_bios(image, filesystem_mount)
        return

    # GPT or hybrid — EFI boot
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

    try:
        _setup_grub_efi(image, grub_target, filesystem_mount)
    except errors.ImageError as err:
        emit.progress(f"Cannot install GRUB on this rootfs: {err}", permanent=True)


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
    """Install GRUB for an EFI-capable (GPT/hybrid) image.

    The root (and optional boot) ext partitions are exposed through FUSE
    mounts, and GRUB's EFI binary is built with the image's own
    ``grub-mkimage`` inside a chroot of the mounted rootfs — guaranteeing the
    builder matches the modules it consumes. ESP files are written in place
    with mtools, and all grub.cfg content is generated here because
    ``grub-mkconfig`` needs a real block device that FUSE cannot provide.
    """
    structure = image.volume.structure
    disk_path = image.disk_path
    sector = gptutil.SECTOR_SIZE_512

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
    _, esp_offset_sectors, esp_size_sectors = _partition_geometry(
        disk_path, structure, filesystem_mount, "/boot/efi"
    )
    esp_offset_bytes = esp_offset_sectors * sector

    grub_fname, fallback_fname = _EFI_TARGET_TO_FILENAMES[grub_target]
    shim_fname = _EFI_TARGET_TO_SHIM_FILENAME.get(grub_target)

    with tempfile.TemporaryDirectory(prefix="imagecraft-grub-") as tmp_str:
        tmp_dir = Path(tmp_str)

        # Each partition gets its own FUSE mount. They deliberately stay
        # flat: stacking a FAT-over-fusefile mount inside the fuse2fs
        # mountpoint breaks path traversal, so /boot and /boot/efi are
        # separate handles rather than a nested tree.
        with contextlib.ExitStack() as stack:
            rootfs = stack.enter_context(
                mount_partition(
                    disk_path,
                    "ext4",
                    offset=root_offset * sector,
                    size=root_size * sector,
                )
            )
            if has_separate_boot:
                bootfs = stack.enter_context(
                    mount_partition(
                        disk_path,
                        "ext4",
                        offset=boot_offset * sector,
                        size=boot_size * sector,
                    )
                )
            else:
                bootfs = rootfs
            signed = _dump_signed_efi_binaries(rootfs, grub_target, tmp_dir)

            if signed:
                emit.progress(f"Deploying signed GRUB ({grub_target})")
                local_binary = tmp_dir / grub_fname
                shutil.copy2(signed["grub"], local_binary)
            else:
                emit.progress(f"Building unsigned GRUB image ({grub_target})")
                local_binary = _build_standalone_image(
                    rootfs,
                    grub_target,
                    prefix="/EFI/ubuntu",
                    modules=_EFI_CORE_MODULES,
                    output_name=grub_fname,
                )

            _deploy_efi_binary(
                disk_path,
                esp_offset_bytes,
                tmp_dir,
                local_binary,
                grub_fname,
                fallback_fname,
                signed_shim=signed["shim"] if signed else None,
                shim_fname=shim_fname,
            )
            if not signed:
                # The binary was built inside the image's /tmp; remove it so
                # it doesn't ship in the final image.
                local_binary.unlink(missing_ok=True)

            # GRUB has to find its config and the kernels on whichever
            # partition holds /boot, which isn't necessarily the root one.
            boot_uuid = _read_ext_uuid(disk_path, boot_offset * sector)
            root_uuid = _read_ext_uuid(disk_path, root_offset * sector)
            kernels = _find_kernels(bootfs, boot_prefix)
            emit.progress("Generating grub configuration file")
            emit.progress("Adding boot menu entry for UEFI Firmware Settings")
            cfg = _generate_grub_cfg(
                kernels,
                root_uuid,
                boot_uuid,
                boot_prefix,
                _read_grub_defaults(rootfs),
                include_fw_setup=True,
            )
            _write_ext_file(bootfs, cfg.encode(), f"{boot_prefix}/grub/grub.cfg")

            stub_cfg = _efi_stub_grub_cfg(boot_uuid, boot_prefix)
            _write_esp_file(
                disk_path,
                esp_offset_bytes,
                tmp_dir,
                stub_cfg.encode(),
                "/EFI/ubuntu/grub.cfg",
            )
            _write_esp_file(
                disk_path,
                esp_offset_bytes,
                tmp_dir,
                stub_cfg.encode(),
                "/EFI/BOOT/grub.cfg",
            )

    emit.progress("GRUB installation complete")


def _build_standalone_image(
    rootfs: Path,
    grub_target: str,
    *,
    prefix: str,
    modules: list[str],
    output_name: str,
) -> Path:
    """Build a standalone GRUB image using the target rootfs's own grub-mkimage.

    Running ``grub-mkimage`` via ``chroot(1)`` of the mounted rootfs
    guarantees the builder matches the module files it consumes — no
    host/image version skew. The binary is built into ``/tmp`` inside the
    tree; the returned path is on the host side of the same mount.

    :raises errors.ImageError: If the image has no GRUB modules installed.
    :raises errors.GRUBInstallError: If the image's grub-mkimage fails.
    """
    modules_dir = rootfs / "usr/lib/grub" / grub_target
    if not modules_dir.is_dir():
        # A rootfs with no GRUB package installed simply gets no bootloader;
        # setup_grub turns this into a skip rather than failing the pack.
        raise errors.ImageError(
            message=f"GRUB modules for {grub_target} are not installed in the image"
        )

    # A fixed location inside the image's own /tmp — not a host temp file.
    output_rel = Path("/tmp") / f"imagecraft-{output_name}"  # noqa: S108
    output_host = rootfs / output_rel.relative_to("/")
    output_host.parent.mkdir(parents=True, exist_ok=True)

    # Run via chroot(1) as a plain subprocess: a clean single-threaded
    # process, unaffected by any threads in this one.
    try:
        run(
            "chroot",
            str(rootfs),
            "grub-mkimage",
            "-d",
            f"/usr/lib/grub/{grub_target}",
            "-o",
            str(output_rel),
            "-O",
            grub_target,
            "-p",
            prefix,
            *modules,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError as err:
        raise errors.GRUBInstallError(
            "Cannot build a GRUB image: chroot is not available"
        ) from err
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError(
            f"Cannot build a GRUB image: grub-mkimage failed for {grub_target}: {err}"
        ) from err

    return output_host


def _fat_mkdir_p(spec: str, target_dir: str) -> None:
    """Recursively create a directory inside a FAT filesystem, ignoring existing."""
    target_dir = target_dir.strip("/")
    if not target_dir:
        return
    current = ""
    for part in target_dir.split("/"):
        current += f"/{part}"
        # mmd fails if the directory already exists; that's fine here, and
        # mtools reports it the same way as a genuine failure, so the result
        # is verified below instead.
        subprocess.run(
            ["mmd", "-i", spec, f"::{current}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def _write_esp_file(
    disk_path: Path,
    esp_offset_bytes: int,
    tmp_dir: Path,
    data: bytes,
    target_path: str,
) -> None:
    """Write raw bytes into the ESP at target_path using mtools.

    The FAT partition is addressed in place via mtools' ``image@@offset``
    syntax — no mount required.
    """
    spec = f"{disk_path}@@{esp_offset_bytes}"
    local = tmp_dir / "esp-payload"
    local.write_bytes(data)
    _fat_mkdir_p(spec, str(PurePosixPath(target_path).parent))
    try:
        run("mcopy", "-n", "-o", "-i", spec, str(local), f"::{target_path}")
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        raise errors.GRUBInstallError(
            f"Failed writing {target_path} to the EFI System Partition"
        ) from err


def _write_ext_file(rootfs: Path, data: bytes, target_path: str) -> None:
    """Write raw bytes into a mounted ext partition at target_path."""
    dest = rootfs / target_path.lstrip("/")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except OSError as err:
        raise errors.GRUBInstallError(
            f"Failed writing {target_path} to the boot partition"
        ) from err


_EXT_UUID_BYTES = 16  # Length of an ext filesystem UUID (s_uuid field).


def _read_ext_uuid(disk_path: Path, partition_offset_bytes: int) -> str:
    """Return the filesystem UUID of the ext partition at the given offset.

    The ext2/3/4 superblock starts 1024 bytes into the filesystem, and its
    ``s_uuid`` field sits 104 bytes into the superblock.
    """
    superblock_offset = partition_offset_bytes + 1024 + 104
    with disk_path.open("rb") as disk_file:
        disk_file.seek(superblock_offset)
        raw = disk_file.read(_EXT_UUID_BYTES)
    if len(raw) != _EXT_UUID_BYTES:
        raise errors.GRUBInstallError(
            f"Failed to read the filesystem UUID at offset {partition_offset_bytes} "
            f"of {disk_path}"
        )
    return str(uuid.UUID(bytes=raw))


def _deploy_efi_binary(
    disk_path: Path,
    esp_offset_bytes: int,
    tmp_dir: Path,
    local_binary: Path,
    grub_fname: str,
    fallback_fname: str,
    *,
    signed_shim: Path | None,
    shim_fname: str | None,
) -> None:
    """Deploy the GRUB EFI binary to both the vendor and fallback ESP paths."""
    _write_esp_file(
        disk_path,
        esp_offset_bytes,
        tmp_dir,
        local_binary.read_bytes(),
        f"/EFI/ubuntu/{grub_fname}",
    )
    if signed_shim and shim_fname:
        # Shim is the entry point that chainloads grubx64.efi from the
        # same directory it resides in.
        _write_esp_file(
            disk_path,
            esp_offset_bytes,
            tmp_dir,
            signed_shim.read_bytes(),
            f"/EFI/ubuntu/{shim_fname}",
        )
        _write_esp_file(
            disk_path,
            esp_offset_bytes,
            tmp_dir,
            signed_shim.read_bytes(),
            f"/EFI/BOOT/{fallback_fname}",
        )
        _write_esp_file(
            disk_path,
            esp_offset_bytes,
            tmp_dir,
            local_binary.read_bytes(),
            f"/EFI/BOOT/{grub_fname}",
        )
    else:
        _write_esp_file(
            disk_path,
            esp_offset_bytes,
            tmp_dir,
            local_binary.read_bytes(),
            f"/EFI/BOOT/{fallback_fname}",
        )


def _dump_signed_efi_binaries(
    rootfs: Path, grub_target: str, dest_dir: Path
) -> dict[str, Path] | None:
    """Dump Ubuntu's pre-signed shim+GRUB from rootfs, if both are present.

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
        # Ubuntu ships some of these as symlinks managed by update-alternatives,
        # so a candidate that doesn't resolve to a real file has to be skipped.
        candidate = rootfs / f"usr/lib/shim/{shim_base}{suffix}".lstrip("/")
        if candidate.is_file():
            shim_src = candidate
            break
    grub_src = rootfs / f"usr/lib/grub/{grub_target}-signed/{grub_fname}.signed"
    if shim_src is None or not grub_src.is_file():
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    shim_dest = dest_dir / shim_fname
    grub_dest = dest_dir / f"{grub_fname}.signed"
    shutil.copy2(shim_src, shim_dest)
    shutil.copy2(grub_src, grub_dest)
    return {"shim": shim_dest, "grub": grub_dest}


def _version_sort_key(name: str) -> tuple[object, ...]:
    """Order kernel filenames by version, comparing digit runs numerically.

    A plain string sort puts ``vmlinuz-6.8.0-100`` before ``vmlinuz-6.8.0-9``,
    which would make the newest kernel look like the oldest.
    """
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part)
        for part in _VERSION_PART_RE.split(name)
        if part
    )


def _find_kernels(bootfs: Path, boot_prefix: str) -> list[tuple[str, str]]:
    """Return (vmlinuz, initrd) filename pairs found under boot_prefix on bootfs.

    Newest kernel first, so the generated ``default=0`` entry boots it — the
    same ordering ``update-grub`` produces.
    """
    search_dir = bootfs / boot_prefix.lstrip("/")
    if not search_dir.is_dir():
        return []
    names = [entry.name for entry in search_dir.iterdir()]
    vmlinuzes = sorted(
        (n for n in names if n.startswith("vmlinuz-")),
        key=_version_sort_key,
        reverse=True,
    )
    kernels = []
    for vmlinuz in vmlinuzes:
        version = vmlinuz.removeprefix("vmlinuz-")
        initrd = f"initrd.img-{version}"
        kernels.append((vmlinuz, initrd if initrd in names else ""))
    return kernels


def _read_grub_defaults(rootfs: Path) -> GrubDefaults:
    """Read the settings configured in ``/etc/default/grub``.

    ``update-grub`` is not run any more, so the settings that would have fed
    the generated menu entries have to be honoured here instead. Mirrors
    stock ``/etc/grub.d/10_linux``, which appends ``GRUB_CMDLINE_LINUX``
    followed by ``GRUB_CMDLINE_LINUX_DEFAULT`` to the default entry.
    """
    defaults_file = rootfs / _DEFAULT_GRUB_PATH.lstrip("/")
    if not defaults_file.is_file():
        return GrubDefaults()
    content = defaults_file.read_text(encoding="utf-8", errors="replace")

    values: dict[str, str] = {}
    # Shell joins continuation lines before assigning, and collapsing the
    # result keeps a value that spanned lines from breaking the generated
    # config, whose `linux` directive has to stay on one line.
    for match in _GRUB_CMDLINE_RE.finditer(_LINE_CONTINUATION_RE.sub(" ", content)):
        raw = match.group("dq") or match.group("sq") or match.group("bare") or ""
        if match.group("sq") is None:
            # Single quotes suppress expansion; anything else expands, and an
            # undefined variable expands to nothing, as it would in shell.
            raw = _GRUB_VAR_REF_RE.sub(lambda m: values.get(m.group(1), ""), raw)
        values[match.group("key")] = " ".join(raw.split())

    parts = [
        values.get("GRUB_CMDLINE_LINUX", ""),
        values.get("GRUB_CMDLINE_LINUX_DEFAULT", ""),
    ]
    timeout = _DEFAULT_GRUB_TIMEOUT
    with contextlib.suppress(ValueError):
        timeout = int(values["GRUB_TIMEOUT"]) if "GRUB_TIMEOUT" in values else timeout
    return GrubDefaults(
        cmdline=" ".join(part for part in parts if part), timeout=timeout
    )


def _generate_grub_cfg(
    kernels: list[tuple[str, str]],
    root_uuid: str,
    boot_uuid: str,
    boot_prefix: str,
    defaults: GrubDefaults = _STOCK_GRUB_DEFAULTS,
    *,
    include_fw_setup: bool = False,
) -> str:
    """Hand-generate a minimal grub.cfg with a menu entry per kernel found.

    :param root_uuid: UUID of the partition to boot as ``/``.
    :param boot_uuid: UUID of the partition holding ``/boot``, which GRUB
        needs to select before it can load a kernel from it. Equal to
        ``root_uuid`` unless ``/boot`` has a partition of its own.
    :param boot_prefix: Path prefix of ``/boot`` on the boot partition.
    :param defaults: Settings read from ``/etc/default/grub``.
    :param include_fw_setup: Add a "UEFI Firmware Settings" menu entry that
        reboots into the firmware setup UI via GRUB's ``fwsetup`` command
        (mirrors what stock Ubuntu's ``/etc/grub.d/30_uefi-firmware`` script
        generates). Only meaningful/available on EFI-booted systems.
    """
    lines = [
        "set default=0",
        f"set timeout={defaults.timeout}",
        "insmod part_gpt",
        "insmod part_msdos",
        "insmod ext2",
        f"search --no-floppy --fs-uuid --set=root {boot_uuid}",
        "",
    ]
    extra = f" {defaults.cmdline}" if defaults.cmdline else ""
    for vmlinuz, initrd in kernels:
        lines.append(f'menuentry "{vmlinuz}" {{')
        lines.append(f"\tlinux {boot_prefix}/{vmlinuz} root=UUID={root_uuid} ro{extra}")
        if initrd:
            lines.append(f"\tinitrd {boot_prefix}/{initrd}")
        lines.append("}")
    if include_fw_setup:
        lines += [
            'if [ "${grub_platform}" = "efi" ]; then',
            "\tmenuentry 'UEFI Firmware Settings' {",
            "\t\tfwsetup",
            "\t}",
            "fi",
        ]
    return "\n".join(lines) + "\n"


def _efi_stub_grub_cfg(boot_uuid: str, boot_prefix: str) -> str:
    """Build the tiny loader config placed on the ESP that chains to the real config."""
    return (
        "\n".join(
            [
                "insmod part_gpt",
                "insmod ext2",
                f"search.fs_uuid {boot_uuid} root",
                f"set prefix=($root)'{boot_prefix}/grub'",
                "configfile $prefix/grub.cfg",
            ]
        )
        + "\n"
    )


def _setup_grub_bios(image: Image, filesystem_mount: FilesystemMount) -> None:
    """Install GRUB for a legacy BIOS/MBR image."""
    structure = image.volume.structure
    disk_path = image.disk_path

    root_partition, root_offset, root_size = _partition_geometry(
        disk_path, structure, filesystem_mount, "/"
    )
    has_separate_boot = _has_separate_boot(filesystem_mount)
    if has_separate_boot:
        _, boot_offset, boot_size = _partition_geometry(
            disk_path, structure, filesystem_mount, "/boot"
        )
    else:
        boot_partition, boot_offset, boot_size = (
            root_partition,
            root_offset,
            root_size,
        )
    # When /boot lives on its own partition, that partition's root directory
    # *is* /boot, so paths written to it must not be prefixed with "/boot".
    boot_prefix = "" if has_separate_boot else "/boot"
    boot_partnum = _part_num(boot_partition, structure)

    with tempfile.TemporaryDirectory(prefix="imagecraft-grub-") as tmp_str:
        tmp_dir = Path(tmp_str)

        with mount_partition(
            disk_path,
            "ext4",
            offset=root_offset * gptutil.SECTOR_SIZE_512,
            size=root_size * gptutil.SECTOR_SIZE_512,
        ) as rootfs:
            modules_dir = rootfs / "usr/lib/grub" / _GRUB_BIOS_TARGET
            if not modules_dir.is_dir():
                # A rootfs with no GRUB package installed simply gets no
                # bootloader; setup_grub turns this into a skip rather than
                # failing the pack.
                raise errors.ImageError(
                    message=(
                        f"GRUB modules for {_GRUB_BIOS_TARGET} are not "
                        "installed in the image"
                    )
                )
            boot_img_path = tmp_dir / "boot.img"
            shutil.copy2(modules_dir / "boot.img", boot_img_path)
            root_uuid = _read_ext_uuid(disk_path, root_offset * gptutil.SECTOR_SIZE_512)
            grub_defaults = _read_grub_defaults(rootfs)

            # The BIOS core image is built by the image's own grub-mkimage
            # (see _build_grub_image); its embedded blocklist is patched
            # below once written to the MBR gap.
            core_img_path = _build_standalone_image(
                rootfs,
                _GRUB_BIOS_TARGET,
                prefix=f"(hd0,msdos{boot_partnum}){boot_prefix}/grub",
                modules=_BIOS_CORE_MODULES,
                output_name="core.img",
            )
            # Read the image back while the rootfs mount is still open, and
            # drop the in-image temporary afterwards.
            core_img = core_img_path.read_bytes()
            core_img_path.unlink(missing_ok=True)

        bootfs_handle = mount_partition(
            disk_path,
            "ext4",
            offset=boot_offset * gptutil.SECTOR_SIZE_512,
            size=boot_size * gptutil.SECTOR_SIZE_512,
        )
        with bootfs_handle as bootfs:
            # GRUB has to find its config and the kernels on whichever
            # partition holds /boot, which isn't necessarily the root one.
            boot_uuid = _read_ext_uuid(disk_path, boot_offset * gptutil.SECTOR_SIZE_512)
            _write_ext_file(
                bootfs,
                core_img,
                f"{boot_prefix}/grub/{_GRUB_BIOS_TARGET}/core.img",
            )
            _write_ext_file(
                bootfs,
                boot_img_path.read_bytes(),
                f"{boot_prefix}/grub/{_GRUB_BIOS_TARGET}/boot.img",
            )

            kernels = _find_kernels(bootfs, boot_prefix)
            emit.progress("Generating grub configuration file")
            cfg = _generate_grub_cfg(
                kernels, root_uuid, boot_uuid, boot_prefix, grub_defaults
            )
            _write_ext_file(bootfs, cfg.encode(), f"{boot_prefix}/grub/grub.cfg")

        _install_bios_boot_sector(disk_path, boot_img_path, core_img)

    emit.progress("GRUB installation complete")


def _install_bios_boot_sector(disk_path: Path, boot_img: Path, core_img: bytes) -> None:
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
    if len(boot_data) != gptutil.SECTOR_SIZE_512:
        raise errors.GRUBInstallError(f"Unexpected boot.img size: {len(boot_data)}")
    boot_data[_BIOS_KERNEL_SECTOR_OFFSET : _BIOS_KERNEL_SECTOR_OFFSET + 8] = (
        _BIOS_CORE_IMG_START_SECTOR.to_bytes(8, "little")
    )

    core_data = bytearray(core_img)
    core_sectors = (
        len(core_data) + gptutil.SECTOR_SIZE_512 - 1
    ) // gptutil.SECTOR_SIZE_512
    if (
        _BIOS_CORE_IMG_START_SECTOR + core_sectors
    ) * gptutil.SECTOR_SIZE_512 > mbrutil.MBR_RESERVED_SIZE:
        raise errors.GRUBInstallError("core.img is too large to fit in the MBR gap")

    # The blocklist's start sector is relative to the disk, not to core.img,
    # and points to the sector right after diskboot.img (core.img's own
    # first sector).
    rest_of_core_start_sector = _BIOS_CORE_IMG_START_SECTOR + 1
    core_data[_BIOS_BLOCKLIST_START_OFFSET : _BIOS_BLOCKLIST_START_OFFSET + 8] = (
        rest_of_core_start_sector.to_bytes(8, "little")
    )

    with disk_path.open("r+b") as disk_file:
        existing_sector0 = bytearray(disk_file.read(gptutil.SECTOR_SIZE_512))
        new_sector0 = bytes(boot_data[:_BIOS_BOOT_CODE_SIZE]) + bytes(
            existing_sector0[_BIOS_BOOT_CODE_SIZE : gptutil.SECTOR_SIZE_512]
        )
        disk_file.seek(0)
        disk_file.write(new_sector0)
        disk_file.seek(_BIOS_CORE_IMG_START_SECTOR * gptutil.SECTOR_SIZE_512)
        disk_file.write(core_data)


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
