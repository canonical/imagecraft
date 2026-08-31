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

"""End-to-end tests for imagecraft.pack.grubutil.

These build small real disk images with the same helpers the production pack
pipeline uses (gptutil/diskutil), populate them with fake-but-realistic GRUB,
shim and kernel content, run the real ``setup_grub()`` — which mounts the
partitions via FUSE and chroots into the rootfs — then inspect the result by
mounting the partitions again.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from craft_parts.filesystem_mounts import FilesystemMount
from imagecraft import errors
from imagecraft.models.volume import (
    GPTStructureItem,
    GPTVolume,
    PartitionSchema,
)
from imagecraft.pack import diskutil, gptutil, grubutil
from imagecraft.pack.diskutil import DiskSize
from imagecraft.pack.image import Image
from imagecraft.utils.mount import mount_partition


@pytest.fixture(autouse=True)
def _require_fuse_tools():
    missing = [
        tool
        for tool in ("fuse2fs", "fusefile", "fusermount3", "mkfs.vfat", "mke2fs")
        if shutil.which(tool) is None
    ]
    if missing:
        pytest.skip(
            "Missing required tool(s) for grubutil integration tests: "
            f"{', '.join(missing)}"
        )


# Architecture mapping: host arch -> (grub_target, grub_fname, shim_fname)
_ARCH_TO_EFI: dict[str, tuple[str, str, str]] = {
    "x86_64": ("x86_64-efi", "grubx64.efi", "shimx64.efi"),
    "aarch64": ("arm64-efi", "grubaa64.efi", "shimaa64.efi"),
    "riscv64": ("riscv64-efi", "grubriscv64.efi", "shimriscv64.efi"),
}
# Architecture mapping: host arch -> DebianArchitecture for setup_grub
_ARCH_TO_DEBIAN: dict[str, str] = {
    "x86_64": "amd64",
    "aarch64": "arm64",
    "riscv64": "riscv64",
}
# Grub target -> ESP fallback binary filename (8.3 format).
_EFI_FALLBACK_FILENAMES: dict[str, str] = {
    "x86_64-efi": "BOOTX64.EFI",
    "arm64-efi": "BOOTAA64.EFI",
    "riscv64-efi": "BOOTRISCV64.EFI",
}


def _host_arch() -> str:
    return subprocess.run(
        ["uname", "-m"], capture_output=True, text=True, check=True
    ).stdout.strip()


def _host_grub_target() -> str:
    return _ARCH_TO_EFI[_host_arch()][0]


def _host_grub_fname() -> str:
    return _ARCH_TO_EFI[_host_arch()][1]


def _host_shim_fname() -> str:
    return _ARCH_TO_EFI[_host_arch()][2]


def _host_debian_arch() -> str:
    return _ARCH_TO_DEBIAN[_host_arch()]


@pytest.fixture
def grub_target() -> str:
    """Skip if host grub modules are not installed for this architecture."""
    target = _host_grub_target()
    if not Path(f"/usr/lib/grub/{target}").is_dir():
        pytest.skip(f"Host grub modules not installed: /usr/lib/grub/{target}")
    return target


@pytest.fixture
def grub_fname() -> str:
    return _host_grub_fname()


@pytest.fixture
def signed_shim_path() -> Path:
    """Skip if signed shim is not installed for the host architecture."""
    path = Path(f"/usr/lib/shim/{_host_shim_fname()}.signed.latest")
    if not path.is_file():
        pytest.skip(f"Signed shim not installed: {path}")
    return path


@pytest.fixture
def signed_grub_path(grub_target: str) -> Path:
    """Skip if signed grub is not installed for the host architecture."""
    path = Path(f"/usr/lib/grub/{grub_target}-signed/{_host_grub_fname()}.signed")
    if not path.is_file():
        pytest.skip(f"Signed grub not installed: {path}")
    return path


def _copy_grub_target_files(src_dir: Path, dest_dir: Path) -> None:
    """Copy a whole real /usr/lib/grub/<target> directory, skipping subdirs."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        if item.is_file():
            shutil.copy2(item, dest_dir / item.name)


def _copy_grub_mkimage(root_content: Path) -> None:
    """Copy the host grub-mkimage binary and its libraries into the fake rootfs.

    Inside the real flow the image's own rootfs provides grub-mkimage; these
    fake trees have to be given one explicitly for the in-chroot build to run.
    """
    binary = Path("/usr/bin/grub-mkimage")
    if not binary.is_file():
        pytest.skip("grub-mkimage is required but not installed on this system")
    dest_bin = root_content / "usr/bin/grub-mkimage"
    dest_bin.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(binary, dest_bin)
    for line in subprocess.run(
        ["ldd", str(binary)], capture_output=True, text=True, check=True
    ).stdout.splitlines():
        parts = line.split()
        lib = next((p for p in parts if p.startswith("/")), None)
        if lib is None:
            continue
        lib_dest = root_content / lib.lstrip("/")
        lib_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(lib, lib_dest)


def _build_and_inject_partition(
    *,
    disk_path: Path,
    tmp_path: Path,
    fstype,
    content_dir: Path,
    label: str | None,
    partition_name: str,
    partition_number: int | None = None,
    sector_size: int = 512,
) -> None:
    if partition_number is not None:
        # MBR partitions have no "name" field in sfdisk --json output, so
        # they must be looked up positionally.
        off = gptutil.get_partition_sector_offset_by_number(disk_path, partition_number)
        size = gptutil.get_partition_size_sectors_by_number(disk_path, partition_number)
    else:
        off = gptutil.get_partition_sector_offset(disk_path, partition_name)
        size = gptutil.get_partition_size_sectors(disk_path, partition_name)
    part_file = tmp_path / f"{partition_name}.img"
    subprocess.run(
        ["truncate", "-s", str(size * sector_size), str(part_file)], check=True
    )
    diskutil.format_populate_partition(
        fstype=fstype, content_dir=content_dir, partitionpath=part_file, label=label
    )
    diskutil.inject_partition_into_image(
        partition=part_file,
        imagepath=disk_path,
        sector_offset=off,
        disk_size=DiskSize(bytesize=size * sector_size, sector_size=sector_size),
    )


def _mount_ext_partition(disk_path: Path, name: str):
    """Mount an ext partition by name through the FUSE utilities."""
    offset = gptutil.get_partition_sector_offset(disk_path, name)
    size = gptutil.get_partition_size_sectors(disk_path, name)
    return mount_partition(disk_path, "ext4", offset=offset * 512, size=size * 512)


def _esp_offset(disk_path: Path) -> int:
    return gptutil.get_partition_sector_offset(disk_path, "efi") * 512


def _esp_mdir(disk_path: Path, path: str) -> str:
    """List an ESP directory with mtools (8.3 names render as columns)."""
    result = subprocess.run(
        ["mdir", "-i", f"{disk_path}@@{_esp_offset(disk_path)}", f"::{path}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _esp_type(disk_path: Path, path: str) -> str:
    """Read a file from the ESP with mtools."""
    return subprocess.run(
        ["mtype", "-i", f"{disk_path}@@{_esp_offset(disk_path)}", f"::{path}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def _make_volume(*, boot_partition: bool):
    from imagecraft.models.volume import FileSystem, GptType, Role  # noqa: PLC0415

    structure = [
        GPTStructureItem(
            name="efi",
            role=Role.SYSTEM_BOOT,
            size="64M",
            filesystem=FileSystem.VFAT,
            type=GptType("C12A7328-F81F-11D2-BA4B-00A0C93EC93B"),
        )
    ]
    if boot_partition:
        structure.append(
            GPTStructureItem(
                name="boot",
                role=Role.SYSTEM_BOOT,
                size="128M",
                filesystem=FileSystem.EXT4,
                type=GptType("0FC63DAF-8483-4772-8E79-3D69D8477DE4"),
            )
        )
    structure.append(
        GPTStructureItem(
            name="rootfs",
            role=Role.SYSTEM_DATA,
            size="256M",
            filesystem=FileSystem.EXT4,
            type=GptType("0FC63DAF-8483-4772-8E79-3D69D8477DE4"),
        )
    )
    return GPTVolume(schema=PartitionSchema.GPT, structure=structure)


@pytest.fixture
def fake_kernel_files():
    def _make(boot_dir: Path) -> None:
        boot_dir.mkdir(parents=True, exist_ok=True)
        (boot_dir / "vmlinuz-6.8.0-generic").write_bytes(b"FAKEKERNEL" * 100)
        (boot_dir / "initrd.img-6.8.0-generic").write_bytes(b"FAKEINITRD" * 100)

    return _make


def _make_esp_content_dir(tmp_path: Path) -> Path:
    """Return an empty ESP content staging directory with the required EFI subdirs."""
    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)
    return esp_content


def _make_standard_gpt_image(
    tmp_path: Path,
    root_content: Path,
    esp_content: Path,
    *,
    boot_content: Path | None = None,
) -> tuple["Image", "FilesystemMount"]:
    """Build a minimal GPT disk image and return (Image, FilesystemMount).

    Creates a 2-partition layout (ESP + rootfs, or 3-partition with /boot) and
    injects *content* directories into each partition.  The returned
    ``FilesystemMount`` uses the standard ``(volume/pc/<name>)`` device
    notation expected by setup_grub.
    """
    volume = _make_volume(boot_partition=boot_content is not None)
    disk_path = tmp_path / "disk.img"
    gptutil.create_empty_gpt_image(imagepath=disk_path, sector_size=512, layout=volume)
    content_map = {"efi": esp_content, "rootfs": root_content}
    mounts = [
        {"mount": "/", "device": "(volume/pc/rootfs)"},
        {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
    ]
    if boot_content is not None:
        content_map["boot"] = boot_content
        mounts.insert(1, {"mount": "/boot", "device": "(volume/pc/boot)"})
    for item in volume.structure:
        _build_and_inject_partition(
            disk_path=disk_path,
            tmp_path=tmp_path,
            fstype=item.filesystem,
            content_dir=content_map[item.name],
            label=item.filesystem_label,
            partition_name=item.name,
        )
    return Image(volume=volume, disk_path=disk_path), FilesystemMount.unmarshal(mounts)


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_signed(
    new_dir,
    fake_kernel_files,
    grub_target,
    grub_fname,
    signed_shim_path,
    signed_grub_path,
):
    """Signed shim+GRUB, when present in the rootfs, are deployed as-is."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path(f"/usr/lib/grub/{grub_target}"),
        root_content / f"usr/lib/grub/{grub_target}",
    )
    (root_content / f"usr/lib/grub/{grub_target}-signed").mkdir(parents=True)
    shutil.copy2(
        signed_grub_path,
        root_content / f"usr/lib/grub/{grub_target}-signed/{grub_fname}.signed",
    )
    (root_content / "usr/lib/shim").mkdir(parents=True)
    shutil.copy2(
        signed_shim_path, root_content / f"usr/lib/shim/{signed_shim_path.name}"
    )
    fake_kernel_files(root_content / "boot")

    image, filesystem_mount = _make_standard_gpt_image(
        tmp_path, root_content, _make_esp_content_dir(tmp_path)
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=_host_debian_arch(),
        filesystem_mount=filesystem_mount,
    )

    grub_basename = grub_fname.removesuffix(".efi")
    shim_basename = signed_shim_path.name.removesuffix(".efi.signed.latest")
    fallback = _EFI_FALLBACK_FILENAMES[grub_target]

    ubuntu = _esp_mdir(image.disk_path, "/EFI/ubuntu")
    assert grub_basename in ubuntu
    assert shim_basename in ubuntu
    boot = _esp_mdir(image.disk_path, "/EFI/BOOT")
    # Shim chainloads grub from beside itself, so the removable path
    # needs its own copy for the fallback boot to work.
    assert fallback.removesuffix(".EFI") in boot
    assert grub_basename in boot

    with _mount_ext_partition(image.disk_path, "rootfs") as rootfs:
        cfg = (rootfs / "boot/grub/grub.cfg").read_text()
        assert "vmlinuz-6.8.0-generic" in cfg
        assert "initrd.img-6.8.0-generic" in cfg


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_unsigned_requires_grub_mkimage_in_image(
    new_dir, fake_kernel_files, grub_target
):
    """The in-image grub-mkimage is required; modules alone do not suffice."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path(f"/usr/lib/grub/{grub_target}"),
        root_content / f"usr/lib/grub/{grub_target}",
    )
    fake_kernel_files(root_content / "boot")
    image, filesystem_mount = _make_standard_gpt_image(
        tmp_path, root_content, _make_esp_content_dir(tmp_path)
    )

    with pytest.raises(errors.GRUBInstallError, match="grub-mkimage failed"):
        grubutil.setup_grub(
            image=image,
            workdir=tmp_path / "work",
            arch=_host_debian_arch(),
            filesystem_mount=filesystem_mount,
        )


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_skips_without_grub_modules(
    new_dir, fake_kernel_files, emitter, grub_target
):
    """A rootfs with no GRUB package installed gets no bootloader, not an error."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    fake_kernel_files(root_content / "boot")
    image, filesystem_mount = _make_standard_gpt_image(
        tmp_path, root_content, _make_esp_content_dir(tmp_path)
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=_host_debian_arch(),
        filesystem_mount=filesystem_mount,
    )

    emitter.assert_progress(
        f"Cannot install GRUB on this rootfs: GRUB modules for {grub_target} "
        "are not installed in the image",
        permanent=True,
    )


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_unsigned(new_dir, fake_kernel_files, grub_target, grub_fname):
    """Without signed shim/GRUB, an unsigned standalone image is built."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path(f"/usr/lib/grub/{grub_target}"),
        root_content / f"usr/lib/grub/{grub_target}",
    )
    _copy_grub_mkimage(root_content)
    fake_kernel_files(root_content / "boot")
    (root_content / "etc/default").mkdir(parents=True)
    (root_content / "etc/default/grub").write_text(
        'GRUB_CMDLINE_LINUX_DEFAULT="console=ttyS0,115200n8"\n'
    )
    image, filesystem_mount = _make_standard_gpt_image(
        tmp_path, root_content, _make_esp_content_dir(tmp_path)
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=_host_debian_arch(),
        filesystem_mount=filesystem_mount,
    )

    grub_basename = grub_fname.removesuffix(".efi")
    ubuntu = _esp_mdir(image.disk_path, "/EFI/ubuntu")
    assert grub_basename in ubuntu
    # No signed shim was available, so no shim binary should be deployed.
    assert "shim" not in ubuntu

    with _mount_ext_partition(image.disk_path, "rootfs") as rootfs:
        cfg = (rootfs / "boot/grub/grub.cfg").read_text()
        assert "console=ttyS0,115200n8" in cfg
        # The temporary in-image build output must not ship in the final image.
        assert not (rootfs / f"tmp/imagecraft-{grub_fname}").exists()


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_separate_boot_partition(
    new_dir, fake_kernel_files, grub_target
):
    """With a dedicated /boot partition, its root (not /boot/...) holds GRUB/kernels."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path(f"/usr/lib/grub/{grub_target}"),
        root_content / f"usr/lib/grub/{grub_target}",
    )
    _copy_grub_mkimage(root_content)
    boot_content = tmp_path / "boot_content"
    fake_kernel_files(boot_content)

    image, filesystem_mount = _make_standard_gpt_image(
        tmp_path,
        root_content,
        _make_esp_content_dir(tmp_path),
        boot_content=boot_content,
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=_host_debian_arch(),
        filesystem_mount=filesystem_mount,
    )

    with _mount_ext_partition(image.disk_path, "boot") as bootfs:
        # The boot partition's *root* is /boot, so grub/kernels live directly
        # at its root, not nested under an extra "boot/" directory.
        entries = {entry.name for entry in bootfs.iterdir()}
        assert "grub" in entries
        assert "vmlinuz-6.8.0-generic" in entries
        assert "initrd.img-6.8.0-generic" in entries
        assert "boot" not in entries

        cfg = (bootfs / "grub/grub.cfg").read_text()
        # Paths in grub.cfg must not be prefixed with /boot, since the
        # kernel/initrd already live at this partition's root.
        assert "linux /vmlinuz-6.8.0-generic" in cfg
        assert "linux /boot/vmlinuz-6.8.0-generic" not in cfg

        boot_uuid = grubutil._read_ext_uuid(
            image.disk_path,
            gptutil.get_partition_sector_offset(image.disk_path, "boot") * 512,
        )

    root_uuid = grubutil._read_ext_uuid(
        image.disk_path,
        gptutil.get_partition_sector_offset(image.disk_path, "rootfs") * 512,
    )

    assert boot_uuid != root_uuid
    # GRUB loads the kernel off the boot partition but boots the root one.
    assert f"search --no-floppy --fs-uuid --set=root {boot_uuid}" in cfg
    assert f"root=UUID={root_uuid}" in cfg

    stub = _esp_type(image.disk_path, "/EFI/ubuntu/grub.cfg")
    # The ESP stub has to chain to the config on the boot partition.
    assert f"search.fs_uuid {boot_uuid} root" in stub
    assert "set prefix=($root)'/grub'" in stub
