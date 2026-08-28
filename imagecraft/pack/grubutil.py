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
from imagecraft.pack.chroot import Chroot, Mount
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
    workdir: Path,
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
        _setup_grub_bios_chroot(image, workdir, _GRUB_BIOS_TARGET, filesystem_mount)
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
                local_binary = _build_grub_image(rootfs, grub_target, grub_fname)

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

            stub_cfg = _efi_stub_grub_cfg(boot_uuid, boot_prefix).encode()
            for stub_path in ("/EFI/ubuntu/grub.cfg", "/EFI/BOOT/grub.cfg"):
                _write_esp_file(
                    disk_path, esp_offset_bytes, tmp_dir, stub_cfg, stub_path
                )

    emit.progress("GRUB installation complete")


def _build_grub_image(rootfs: Path, grub_target: str, grub_fname: str) -> Path:
    """Build a standalone GRUB EFI binary using the image's own grub-mkimage.

    Running ``grub-mkimage`` inside a chroot of the mounted rootfs guarantees
    the builder matches the module files it consumes — no host/image version
    skew. The binary is built into ``/tmp`` inside the tree; the returned path
    is on the host side of the same mount.

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
    output_rel = Path("/tmp") / f"imagecraft-{grub_fname}"  # noqa: S108
    output_host = rootfs / output_rel.relative_to("/")
    output_host.parent.mkdir(parents=True, exist_ok=True)

    # Run the image's own grub-mkimage via chroot(1) as a plain subprocess:
    # a clean single-threaded process, unaffected by any threads in this one.
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
            "/EFI/ubuntu",
            *_EFI_CORE_MODULES,
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
    current = ""
    for part in target_dir.strip("/").split("/"):
        if not part:
            continue
        current += f"/{part}"
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
    bin_data = local_binary.read_bytes()
    _write_esp_file(
        disk_path, esp_offset_bytes, tmp_dir, bin_data, f"/EFI/ubuntu/{grub_fname}"
    )
    if signed_shim and shim_fname:
        shim_data = signed_shim.read_bytes()
        _write_esp_file(
            disk_path, esp_offset_bytes, tmp_dir, shim_data, f"/EFI/ubuntu/{shim_fname}"
        )
        _write_esp_file(
            disk_path,
            esp_offset_bytes,
            tmp_dir,
            shim_data,
            f"/EFI/BOOT/{fallback_fname}",
        )
        _write_esp_file(
            disk_path, esp_offset_bytes, tmp_dir, bin_data, f"/EFI/BOOT/{grub_fname}"
        )
    else:
        _write_esp_file(
            disk_path,
            esp_offset_bytes,
            tmp_dir,
            bin_data,
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
    shim_src = next(
        (
            candidate
            for suffix in _SIGNED_SHIM_SUFFIXES
            if (
                candidate := rootfs / f"usr/lib/shim/{shim_base}{suffix}".lstrip("/")
            ).is_file()
        ),
        None,
    )
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
    names = {entry.name for entry in search_dir.iterdir()}
    vmlinuzes = sorted(
        (n for n in names if n.startswith("vmlinuz-")),
        key=_version_sort_key,
        reverse=True,
    )
    return [
        (
            v,
            initrd
            if (initrd := f"initrd.img-{v.removeprefix('vmlinuz-')}") in names
            else "",
        )
        for v in vmlinuzes
    ]


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

    cmdline = " ".join(
        filter(
            None,
            [
                values.get("GRUB_CMDLINE_LINUX"),
                values.get("GRUB_CMDLINE_LINUX_DEFAULT"),
            ],
        )
    )
    timeout = _DEFAULT_GRUB_TIMEOUT
    with contextlib.suppress(ValueError, KeyError):
        timeout = int(values["GRUB_TIMEOUT"])
    return GrubDefaults(cmdline=cmdline, timeout=timeout)


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
        lines.extend(
            [
                f'menuentry "{vmlinuz}" {{',
                f"\tlinux {boot_prefix}/{vmlinuz} root=UUID={root_uuid} ro{extra}",
                *([f"\tinitrd {boot_prefix}/{initrd}"] if initrd else []),
                "}",
            ]
        )
    if include_fw_setup:
        lines.extend(
            [
                'if [ "${grub_platform}" = "efi" ]; then',
                "\tmenuentry 'UEFI Firmware Settings' {",
                "\t\tfwsetup",
                "\t}",
                "fi",
            ]
        )
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


def _grub_install(grub_target: str, loop_dev: str) -> None:
    """Install grub in the image.

    :param grub_target: target platform to install grub for.
    :param loop_dev: loop device to install grub on
    """
    check_grub_install = ["grub-install", "-V"]
    if grub_target == _GRUB_BIOS_TARGET:
        grub_install_command = [
            "grub-install",
            "--boot-directory=/boot",
            f"--target={grub_target}",
            loop_dev,
        ]
    else:
        grub_install_command = [
            "grub-install",
            loop_dev,
            "--boot-directory=/boot",
            "--efi-directory=/boot/efi",
            f"--target={grub_target}",
            "--uefi-secure-boot",
            "--no-nvram",
        ]

    update_grub_command = [
        "update-grub",
    ]

    # Divert os-probe to avoid writing wrong output in grub.cfg
    os_prober = "/etc/grub.d/30_os-prober"
    divert_base_command = "dpkg-divert"

    divert_common_args = [
        "--local",
        "--divert",
        os_prober + ".dpkg-divert",
        "--rename",
        os_prober,
    ]

    divert_os_prober_command = [divert_base_command, *list(divert_common_args)]

    undivert_os_prober_command = [
        divert_base_command,
        "--remove",
        *divert_common_args,
    ]

    # Check if grub-install is available, otherwise skip the installation without error
    try:
        run(*check_grub_install)
    except FileNotFoundError:
        emit.progress(
            "Skipping GRUB installation because grub-install is not available",
            permanent=True,
        )
        return

    try:
        for cmd in [
            grub_install_command,
            divert_os_prober_command,
            update_grub_command,
            undivert_os_prober_command,
        ]:
            res = run(*cmd, stderr=subprocess.STDOUT)
            if res.stdout:
                emit.debug(res.stdout)
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError("Fail to install grub") from err
    except FileNotFoundError as err:
        raise errors.GRUBInstallError("Missing tool to install grub") from err


def _setup_grub_bios_chroot(
    image: Image,
    workdir: Path,
    grub_target: str,
    filesystem_mount: FilesystemMount,
) -> None:
    """Install GRUB for a legacy BIOS/MBR image via a loop device and chroot.

    This is the original, privileged installation path. It is retained only
    for BIOS/MBR images until they are converted to direct disk image
    manipulation, at which point this and its helpers are removed.
    """
    mount_dir = workdir / "mount"
    mount_dir.mkdir(exist_ok=True)

    with image.attach_loopdev() as loop_dev:
        mounts: list[Mount] = [
            *_image_mounts(loop_dev, image.volume.structure, filesystem_mount),
            Mount(
                fstype="devtmpfs",
                src="devtmpfs-build",
                relative_mountpoint="/dev",
            ),
            Mount(
                fstype="devpts",
                src="devpts-build",
                relative_mountpoint="/dev/pts",
                options=["-o", "nodev,nosuid"],
            ),
            Mount(fstype="proc", src="proc-build", relative_mountpoint="proc"),
            Mount(fstype="sysfs", src="sysfs-build", relative_mountpoint="/sys"),
            Mount(
                fstype=None, src="/run", relative_mountpoint="/run", options=["--bind"]
            ),
        ]
        chroot = Chroot(path=mount_dir, mounts=mounts)

        try:
            chroot.execute(
                target=_grub_install,
                grub_target=grub_target,
                loop_dev=loop_dev,
            )
        except errors.ChrootMountError as err:
            # Ignore mounting errors indicating the rootfs does not have
            # the needed structure to install grub.
            emit.progress(f"Cannot install GRUB on this rootfs: {err}", permanent=True)


def _image_mounts(
    loop_dev: str, structure: StructureList, filesystem_mount: FilesystemMount
) -> list[Mount]:
    """Generate a list of mounts for the structure, based on the given filesystem_mount.

    :param loop_dev: loop device the disk is associated to
    :param structure: StructureList describing the partition layout of the image
    :param filesystem_mount: order in which partitions should be mounted
    """
    image_mounts: list[Mount] = []

    for entry in filesystem_mount:
        partition_name = _partition_name_from_device(entry.device)
        partnum = _part_num(partition_name, structure)
        if partnum is None:
            raise errors.ImageError(
                message=f"Cannot find a partition named {partition_name}"
            )
        image_mounts.append(
            Mount(
                fstype=None,
                src=f"{loop_dev}p{partnum}",
                relative_mountpoint=entry.mount,
            )
        )
    return image_mounts


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
