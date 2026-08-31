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
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from typing import cast

from craft_cli import emit
from craft_platforms import DebianArchitecture

from imagecraft import errors
from imagecraft.models import volume
from imagecraft.pack import chroot, gptutil, mbrutil
from imagecraft.pack.image import Image
from imagecraft.subprocesses import run
from imagecraft.utils import mount as fusemount

_ARCH_TO_GRUB_EFI_TARGET: dict[str, str] = {
    DebianArchitecture.AMD64: "x86_64-efi",
    DebianArchitecture.ARM64: "arm64-efi",
    DebianArchitecture.ARMHF: "arm-efi",
    DebianArchitecture.RISCV64: "riscv64-efi",
}

_GRUB_BIOS_TARGET = "i386-pc"
_GRUB_BIOS_ARCHS = {DebianArchitecture.AMD64, DebianArchitecture.I386}

_ROLE_MOUNT_PAIRS: list[tuple[Callable[[volume.StructureItem], bool], str]] = [
    (lambda s: s.role == volume.Role.SYSTEM_DATA, "/"),
    (lambda s: s.role == volume.Role.SYSTEM_BOOT and not _is_efi_partition(s), "/boot"),
]

# GRUB target -> UEFI removable-media architecture token.
#
# These tokens are the architecture identifiers mandated by the UEFI
# specification for the fallback boot path (\EFI\BOOT\BOOT<token>.EFI) and
# appear nowhere in the image itself — grub-install computes them the same
# way (grub-core/osdep/linux/platform.c). Only the unsigned standalone path
# needs this table; the signed path derives every filename from the shim and
# GRUB binaries actually shipped in the rootfs.
# See UEFI Specification 2.10, section 3.5.1.1 "Removable Media Boot Behavior":
# https://uefi.org/specs/UEFI/2.10/03_Boot_Manager.html#removable-media-boot-behavior
_GRUB_TARGET_TO_UEFI_ARCH: dict[str, str] = {
    "x86_64-efi": "X64",
    "arm64-efi": "AA64",
    "arm-efi": "ARM",
    "riscv64-efi": "RISCV64",
}

# Seed modules embedded into the standalone GRUB EFI image. ``grub-mkimage``
# only embeds the names passed to it, so every module the generated grub.cfg
# references (plus graphics/compression support the stock scripts rely on)
# must be seeded here; the full set is then computed as the transitive
# closure over the image's own moddep.lst — not a brittle hardcoded list.
_EFI_CORE_MODULES = [
    # Referenced by the generated grub.cfg / ESP stub.
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
    "gfxterm",
    "font",
    "efi_gop",
    # Compressed kernels and initrds are unreadable without gzio, even though
    # no script here emits it (in stock Ubuntu, /etc/grub.d/10_linux does).
    "gzio",
]

# Signed shim/grub filename suffixes, in preference order.
_SIGNED_SHIM_SUFFIXES = (".efi.signed.latest", ".efi.signed", ".efi.dualsigned")

# Split a filename into digit and non-digit runs, so versions compare
# numerically rather than lexicographically.
_VERSION_PART_RE = re.compile(r"(\d+)")


def setup_grub(
    image: Image,
    workdir: pathlib.Path,
    arch: str,
) -> None:
    """Set up GRUB directly on the disk image.

    :param image: Image object handling the actual disk file
    :param workdir: working directory
    :param arch: architecture the image is built for
    """
    emit.progress("Setting up GRUB in the image")

    if not image.has_data_partition:
        emit.progress(
            "Skipping GRUB installation because no data partition was found",
        )
        return

    if image.volume.volume_schema == volume.PartitionSchema.MBR:
        # Legacy BIOS/MBR images are still installed through a loop device
        # and a chroot. They move over to direct image manipulation in a
        # follow-up change, once the EFI path has settled.
        _setup_grub_bios_chroot(image, workdir, _GRUB_BIOS_TARGET)
        return

    # GPT or hybrid — EFI boot
    if not image.has_boot_partition:
        emit.progress(
            "Skipping GRUB installation because no boot partition was found",
        )
        return
    if arch not in _ARCH_TO_GRUB_EFI_TARGET:
        emit.progress("Cannot install GRUB on this architecture", permanent=True)
        return
    grub_target = _ARCH_TO_GRUB_EFI_TARGET[arch]

    _setup_grub_efi(image, grub_target)


def _discover_grub_target(rootfs: pathlib.Path, build_for_target: str) -> str:
    """Return the GRUB EFI target directory actually installed in the rootfs.

    Normally the rootfs carries exactly one ``/usr/lib/grub/*-efi`` directory,
    so no lookup table is needed at all. When several are present (a foreign
    architecture's modules were installed alongside), the project's
    ``build-for`` architecture (already resolved to a GRUB target by
    ``setup_grub``) selects the right one.

    :raises errors.ImageError: If no GRUB EFI modules are installed.
    """
    grub_dir = rootfs / "usr/lib/grub"
    candidates = (
        sorted(
            d.name for d in grub_dir.iterdir() if d.is_dir() and d.name.endswith("-efi")
        )
        if grub_dir.is_dir()
        else []
    )
    if build_for_target in candidates:
        return build_for_target
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise errors.ImageError(
            message=f"GRUB modules for {build_for_target} are not installed in the image"
        )
    raise errors.ImageError(
        message=f"Multiple GRUB EFI module sets present ({', '.join(candidates)}) "
        f"but none matches the build architecture ({build_for_target})"
    )


def _unsigned_shim_name(signed_name: str) -> str:
    """Strip the signing suffix from a shim filename (``shimx64.efi.signed`` -> ``shimx64.efi``)."""
    for suffix in _SIGNED_SHIM_SUFFIXES:
        if signed_name.endswith(suffix):
            return signed_name.removesuffix(suffix) + ".efi"
    return signed_name


def _efi_filenames(
    grub_target: str, signed: dict[str, pathlib.Path] | None
) -> tuple[str, str, str | None]:
    """Return (grub_fname, fallback_fname, shim_fname) for the ESP.

    With signed binaries present, every name derives from the files Ubuntu
    ships in the image — no per-architecture table is needed. Without them,
    the names follow the UEFI spec's arch-token convention.
    """
    if signed:
        grub_fname = signed["grub"].name.removesuffix(".signed")
        shim_fname = _unsigned_shim_name(signed["shim"].name)
        uefi_arch = shim_fname.removeprefix("shim").removesuffix(".efi")
        return grub_fname, f"BOOT{uefi_arch.upper()}.EFI", shim_fname
    uefi_arch = _GRUB_TARGET_TO_UEFI_ARCH[grub_target]
    return f"grub{uefi_arch.lower()}.efi", f"BOOT{uefi_arch}.EFI", None


def _is_efi_partition(item: volume.StructureItem) -> bool:
    """Return True for the EFI system partition (GPT only)."""
    return (
        isinstance(item, volume.GPTStructureItem)
        and item.structure_type == volume.GptType.EFI_SYSTEM
    )


def _find_structure_item(
    structure: volume.StructureList,
    predicate: Callable[[volume.StructureItem], bool],
) -> volume.StructureItem:
    """Return the first structure item matching *predicate*."""
    for item in structure:
        if predicate(item):
            return item
    raise errors.ImageError(message="No matching partition found")


def _partition_offset_size(
    disk_path: pathlib.Path,
    structure: volume.StructureList,
    predicate: Callable[[volume.StructureItem], bool],
) -> tuple[int, int]:
    """Return (offset_sectors, size_sectors) for the first structure item matching *predicate*. Works for both GPT and MBR schemas."""
    item = _find_structure_item(structure, predicate)
    partnum = _part_num(item.name, structure)
    if partnum is None:
        raise errors.ImageError(message=f"Cannot find a partition named {item.name}")
    if isinstance(structure[0], volume.MBRStructureItem):
        offset = gptutil.get_partition_sector_offset_by_number(disk_path, partnum)
        size = gptutil.get_partition_size_sectors_by_number(disk_path, partnum)
    else:
        offset = gptutil.get_partition_sector_offset(disk_path, item.name)
        size = gptutil.get_partition_size_sectors(disk_path, item.name)
    return offset, size


def _setup_grub_efi(
    image: Image,
    requested_grub_target: str,
) -> None:
    """Install GRUB for an EFI-capable (GPT/hybrid) image.

    The root (and optional boot) ext partitions are exposed through FUSE
    mounts, and GRUB's EFI binary is built with the image's own
    ``grub-mkimage`` inside a chroot of the mounted rootfs — guaranteeing the
    builder matches the modules it consumes. ESP files are written in place
    with mtools, and all grub.cfg content is generated here because
    ``grub-mkconfig`` needs a real block device that FUSE cannot provide.

    ``requested_grub_target`` is the GRUB target implied by the project's
    ``build-for`` architecture; it is used as a tiebreak when the rootfs
    carries GRUB modules for more than one target.
    """
    structure = image.volume.structure
    disk_path = image.disk_path
    sector = gptutil.SECTOR_SIZE_512

    root_offset, root_size = _partition_offset_size(
        disk_path,
        structure,
        lambda s: s.role == volume.Role.SYSTEM_DATA,
    )
    has_separate_boot = any(
        s.role == volume.Role.SYSTEM_BOOT and not _is_efi_partition(s)
        for s in structure
    )
    if has_separate_boot:
        boot_offset, boot_size = _partition_offset_size(
            disk_path,
            structure,
            lambda s: s.role == volume.Role.SYSTEM_BOOT and not _is_efi_partition(s),
        )
    else:
        boot_offset, boot_size = root_offset, root_size
    esp_offset, _ = _partition_offset_size(
        disk_path,
        structure,
        _is_efi_partition,
    )
    esp_offset_bytes = esp_offset * sector

    with tempfile.TemporaryDirectory(prefix="imagecraft-grub-") as tmp_str:
        tmp_dir = pathlib.Path(tmp_str)

        # Each partition gets its own FUSE mount. They deliberately stay
        # flat: stacking a FAT-over-fusefile mount inside the fuse2fs
        # mountpoint breaks path traversal, so /boot and /boot/efi are
        # separate handles rather than a nested tree.
        with contextlib.ExitStack() as stack:
            rootfs = stack.enter_context(
                fusemount.mount_partition(
                    disk_path,
                    "ext4",
                    offset=root_offset * sector,
                    size=root_size * sector,
                )
            )
            if has_separate_boot:
                stack.enter_context(
                    fusemount.mount_partition(
                        disk_path,
                        "ext4",
                        offset=boot_offset * sector,
                        size=boot_size * sector,
                    )
                )
            # The rootfs itself declares which GRUB modules it carries; the
            # build-for target is only a tiebreak if it carries several.
            grub_target = _discover_grub_target(rootfs, requested_grub_target)
            signed = _dump_signed_efi_binaries(rootfs, grub_target, tmp_dir)
            grub_fname, fallback_fname, shim_fname = _efi_filenames(grub_target, signed)

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

            # update-grub finds kernels and generates grub.cfg and the
            # ESP stubs inside the chroot. The grub-probe stub answers
            # its device queries from precomputed UUIDs since the
            # FUSE mount has no block device.
            boot_uuid = _read_ext_uuid(disk_path, boot_offset * sector)
            root_uuid = _read_ext_uuid(disk_path, root_offset * sector)
            _run_update_grub(rootfs, boot_uuid=boot_uuid, root_uuid=root_uuid)

    emit.progress("GRUB installation complete")


_STUB_GRUB_PROBE_PATH = (
    pathlib.Path(__file__).resolve().parents[2] / "shell" / "grub-probe-stub.sh"
)


@contextlib.contextmanager
def _substitute_grub_probe(rootfs: pathlib.Path) -> None:
    """Replace ``/usr/sbin/grub-probe`` with the stub for the duration.

    The original binary is saved at ``<stub>.imagecraft.bak`` and restored
    afterward, even if an exception is raised.
    """
    stub_path = rootfs / "usr/sbin/grub-probe"
    original = stub_path.with_suffix(".imagecraft.bak")
    original.unlink(missing_ok=True)
    shutil.move(str(stub_path), str(original))
    stub_path.write_text(_STUB_GRUB_PROBE_PATH.read_text(), encoding="utf-8")
    stub_path.chmod(0o755)
    try:
        yield
    finally:
        stub_path.unlink()
        shutil.move(str(original), str(stub_path))


def _run_update_grub(
    rootfs: pathlib.Path,
    *,
    boot_uuid: str,
    root_uuid: str,
) -> None:
    """Run ``update-grub`` in the image, behind a stub for ``grub-probe``.

    The stub answers ``grub-probe`` queries from the pre-computed UUIDs,
    because the mounted chroot lacks a real block device and the real
    probe simply fails.
    """
    env = {
        **os.environ,
        "IMAGECRAFT_ROOT_UUID": root_uuid,
        "IMAGECRAFT_BOOT_UUID": boot_uuid,
    }
    try:
        with _substitute_grub_probe(rootfs):
            run("chroot", str(rootfs), "update-grub", env=env)
    except FileNotFoundError as err:
        raise errors.GRUBInstallError(
            "Cannot run update-grub: chroot unavailable"
        ) from err
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError(f"update-grub failed: {err}") from err


def _build_grub_image(
    rootfs: pathlib.Path, grub_target: str, grub_fname: str
) -> pathlib.Path:
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

    # Compute the full embedded-module set as the closure over the image's
    # own dependency manifest rather than relying on a fixed list that would
    # have to be maintained per GRUB version.
    modules = _resolve_core_modules(modules_dir)

    # A fixed location inside the image's own /tmp — not a host temp file.
    output_rel = pathlib.Path("/tmp") / f"imagecraft-{grub_fname}"  # noqa: S108
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


def _resolve_core_modules(modules_dir: pathlib.Path) -> list[str]:
    """Close the embedded-core seed set over the image's own moddep.lst.

    grub-mkimage embeds only the modules passed to it; reading the dependency
    manifest shipped with the image guarantees the complete transitive set is
    embedded no matter which GRUB version the image carries. If moddep.lst is
    unavailable (only happens on hand-rolled trees), fall back to the seeds.
    """
    moddep_path = modules_dir / "moddep.lst"
    deps: dict[str, list[str]] = {}
    if moddep_path.is_file():
        for line in moddep_path.read_text(encoding="utf-8").splitlines():
            name, sep, rest = line.partition(":")
            if sep:
                deps[name.strip()] = rest.split()

    seen: set[str] = set()
    stack = list(_EFI_CORE_MODULES)
    while stack:
        mod = stack.pop()
        if mod in seen:
            continue
        seen.add(mod)
        stack.extend(deps.get(mod, []))

    # Deterministic order keeps the resulting image byte-for-byte stable.
    return sorted(seen)


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
    disk_path: pathlib.Path,
    esp_offset_bytes: int,
    tmp_dir: pathlib.Path,
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
    _fat_mkdir_p(spec, str(pathlib.PurePosixPath(target_path).parent))
    try:
        run("mcopy", "-n", "-o", "-i", spec, str(local), f"::{target_path}")
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        raise errors.GRUBInstallError(
            f"Failed writing {target_path} to the EFI System Partition"
        ) from err


def _write_ext_file(
    rootfs: pathlib.Path, data: bytes, target_path: pathlib.PurePosixPath
) -> None:
    """Write raw bytes into a mounted ext partition at target_path.

    ``target_path`` must be absolute (it is interpreted relative to rootfs's
    own root), matching how the ESP helpers treat their target strings.
    """
    dest = rootfs / target_path.relative_to("/")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except OSError as err:
        raise errors.GRUBInstallError(
            f"Failed writing {target_path} to the boot partition"
        ) from err


_EXT_UUID_BYTES = 16  # Length of an ext filesystem UUID (s_uuid field).


def _read_ext_uuid(disk_path: pathlib.Path, partition_offset_bytes: int) -> str:
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
    disk_path: pathlib.Path,
    esp_offset_bytes: int,
    tmp_dir: pathlib.Path,
    local_binary: pathlib.Path,
    grub_fname: str,
    fallback_fname: str,
    *,
    signed_shim: pathlib.Path | None,
    shim_fname: str | None,
) -> None:
    """Deploy the GRUB EFI binary to both the vendor and fallback ESP paths."""
    bin_data = local_binary.read_bytes()
    shim_data = signed_shim.read_bytes() if signed_shim and shim_fname else None
    files = [
        (f"/EFI/ubuntu/{grub_fname}", bin_data),
        (f"/EFI/BOOT/{fallback_fname}", shim_data if shim_data else bin_data),
    ]
    if shim_data and shim_fname:
        files.extend(
            [
                (f"/EFI/ubuntu/{shim_fname}", shim_data),
                (f"/EFI/BOOT/{grub_fname}", bin_data),
            ]
        )
    for target_path, data in files:
        _write_esp_file(disk_path, esp_offset_bytes, tmp_dir, data, target_path)


def _dump_signed_efi_binaries(
    rootfs: pathlib.Path, grub_target: str, dest_dir: pathlib.Path
) -> dict[str, pathlib.Path] | None:
    """Dump Ubuntu's pre-signed shim+GRUB from rootfs, if both are present.

    The binaries are discovered by name pattern rather than a per-architecture
    table, so the returned names are exactly what Ubuntu ships. The caller
    derives the canonical deployment names by stripping the signing suffix.

    Returns a dict with "shim" and "grub" local paths, or None if either
    piece isn't installed (in which case an unsigned image should be built
    with grub-mkimage instead).
    """
    shim_src = next(
        (
            candidate
            for suffix in _SIGNED_SHIM_SUFFIXES
            for candidate in sorted((rootfs / "usr/lib/shim").glob(f"shim*{suffix}"))
            if candidate.is_file()
        ),
        None,
    )
    grub_src = next(
        (
            candidate
            for candidate in sorted(
                (rootfs / "usr/lib/grub" / f"{grub_target}-signed").glob(
                    "grub*.efi.signed"
                )
            )
            if candidate.is_file()
        ),
        None,
    )
    if shim_src is None or grub_src is None:
        return None

    dest_dir.mkdir(parents=True, exist_ok=True)
    shim_dest = dest_dir / shim_src.name
    grub_dest = dest_dir / grub_src.name
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


def _grub_install(grub_target: str, loop_dev: str) -> None:
    """Install grub in the image.

    :param grub_target: target platform to install grub for.
    :param loop_dev: loop device to install grub on
    """
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

    # Divert os-prober to avoid writing wrong output in grub.cfg
    os_prober = "/etc/grub.d/30_os-prober"
    divert_args = [
        "--local",
        "--divert",
        f"{os_prober}.dpkg-divert",
        "--rename",
        os_prober,
    ]
    commands = [
        grub_install_command,
        ["dpkg-divert", *divert_args],
        ["update-grub"],
        ["dpkg-divert", "--remove", *divert_args],
    ]

    # Check if grub-install is available, otherwise skip the installation without error
    try:
        run("grub-install", "-V")
    except FileNotFoundError:
        emit.progress(
            "Skipping GRUB installation because grub-install is not available",
            permanent=True,
        )
        return

    try:
        for cmd in commands:
            res = run(*cmd, stderr=subprocess.STDOUT)
            if res.stdout:
                emit.debug(res.stdout)
    except subprocess.CalledProcessError as err:
        raise errors.GRUBInstallError("Fail to install grub") from err
    except FileNotFoundError as err:
        raise errors.GRUBInstallError("Missing tool to install grub") from err


def _setup_grub_bios_chroot(
    image: Image,
    workdir: pathlib.Path,
    grub_target: str,
) -> None:
    """Install GRUB for a legacy BIOS/MBR image via a loop device and chroot.

    This is the original, privileged installation path. It is retained only
    for BIOS/MBR images until they are converted to direct disk image
    manipulation, at which point this and its helpers are removed.
    """
    structure = image.volume.structure
    mount_dir = workdir / "mount"
    mount_dir.mkdir(exist_ok=True)

    with image.attach_loopdev() as loop_dev:
        image_mounts = []
        for predicate, mountpoint in _ROLE_MOUNT_PAIRS:
            try:
                item = _find_structure_item(structure, predicate)
            except errors.ImageError:
                continue
            partnum = _part_num(item.name, structure)
            if partnum is None:
                raise errors.ImageError(
                    message=f"Cannot find a partition named {item.name}"
                )
            image_mounts.append(
                chroot.Mount(
                    fstype=None,
                    src=f"{loop_dev}p{partnum}",
                    relative_mountpoint=mountpoint,
                )
            )
        # EFI system partition (GPT only) is mounted at /boot/efi.
        if any(_is_efi_partition(s) for s in structure):
            item = _find_structure_item(structure, _is_efi_partition)
            partnum = _part_num(item.name, structure)
            image_mounts.append(
                chroot.Mount(
                    fstype=None,
                    src=f"{loop_dev}p{partnum}",
                    relative_mountpoint="/boot/efi",
                )
            )
        mounts: list[chroot.Mount] = [
            *image_mounts,
            chroot.Mount(
                fstype="devtmpfs",
                src="devtmpfs-build",
                relative_mountpoint="/dev",
            ),
            chroot.Mount(
                fstype="devpts",
                src="devpts-build",
                relative_mountpoint="/dev/pts",
                options=["-o", "nodev,nosuid"],
            ),
            chroot.Mount(fstype="proc", src="proc-build", relative_mountpoint="proc"),
            chroot.Mount(fstype="sysfs", src="sysfs-build", relative_mountpoint="/sys"),
            chroot.Mount(
                fstype=None, src="/run", relative_mountpoint="/run", options=["--bind"]
            ),
        ]
        chroot_obj = chroot.Chroot(path=mount_dir, mounts=mounts)

        try:
            chroot_obj.execute(
                target=_grub_install,
                grub_target=grub_target,
                loop_dev=loop_dev,
            )
        except errors.ChrootMountError as err:
            # Ignore mounting errors indicating the rootfs does not have
            # the needed structure to install grub.
            emit.progress(f"Cannot install GRUB on this rootfs: {err}", permanent=True)


def _part_num(name: str, structure: volume.StructureList) -> int | None:
    """Get the partition number for a given name based on its position.

    For MBR volumes with extended partitions (>4 entries), logical partitions
    start at 5 because slot 4 is reserved for the synthesised extended container.
    """
    needs_extended = len(structure) > mbrutil.MAX_PRIMARY_SLOTS and isinstance(
        structure[0], volume.MBRStructureItem
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
