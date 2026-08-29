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
from craft_platforms import DebianArchitecture
from imagecraft import errors
from imagecraft.models.volume import (
    GPTStructureItem,
    GPTVolume,
    MBRStructureItem,
    MBRVolume,
    PartitionSchema,
)
from imagecraft.pack import diskutil, gptutil, grubutil, mbrutil
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
        pytest.fail(
            "Missing required tool(s) for grubutil integration tests: "
            f"{', '.join(missing)}. Run `make setup` to install them.",
            pytrace=False,
        )


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
        pytest.fail("grub-mkimage is required but not installed on this system")
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


def _mount_ext_partition(disk_path: Path, name: str, *, number: int | None = None):
    """Mount an ext partition by name (GPT) or number (MBR) through FUSE."""
    if number is not None:
        offset = gptutil.get_partition_sector_offset_by_number(disk_path, number)
        size = gptutil.get_partition_size_sectors_by_number(disk_path, number)
    else:
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


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_signed(new_dir, fake_kernel_files):
    """Signed shim+GRUB, when present in the rootfs, are deployed as-is."""
    from imagecraft.models.volume import FileSystem, GptType, Role  # noqa: PLC0415

    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path("/usr/lib/grub/x86_64-efi"), root_content / "usr/lib/grub/x86_64-efi"
    )
    signed_grub = Path("/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed")
    signed_shim = Path("/usr/lib/shim/shimx64.efi.signed.latest")
    if not (signed_grub.is_file() and signed_shim.is_file()):
        pytest.skip("signed shim/grub not installed on this system")
    (root_content / "usr/lib/grub/x86_64-efi-signed").mkdir(parents=True)
    shutil.copy2(
        signed_grub, root_content / "usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed"
    )
    (root_content / "usr/lib/shim").mkdir(parents=True)
    shutil.copy2(signed_shim, root_content / "usr/lib/shim/shimx64.efi.signed.latest")
    fake_kernel_files(root_content / "boot")

    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)

    volume = GPTVolume(
        schema=PartitionSchema.GPT,
        structure=[
            GPTStructureItem(
                name="efi",
                role=Role.SYSTEM_BOOT,
                size="64M",
                filesystem=FileSystem.VFAT,
                type=GptType("C12A7328-F81F-11D2-BA4B-00A0C93EC93B"),
            ),
            GPTStructureItem(
                name="rootfs",
                role=Role.SYSTEM_DATA,
                size="256M",
                filesystem=FileSystem.EXT4,
                type=GptType("0FC63DAF-8483-4772-8E79-3D69D8477DE4"),
            ),
        ],
    )
    disk_path = tmp_path / "disk.img"
    gptutil.create_empty_gpt_image(imagepath=disk_path, sector_size=512, layout=volume)
    for item, content in (
        (volume.structure[0], esp_content),
        (volume.structure[1], root_content),
    ):
        _build_and_inject_partition(
            disk_path=disk_path,
            tmp_path=tmp_path,
            fstype=item.filesystem,
            content_dir=content,
            label=item.filesystem_label,
            partition_name=item.name,
        )

    image = Image(volume=volume, disk_path=disk_path)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
        ]
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    ubuntu = _esp_mdir(disk_path, "/EFI/ubuntu")
    assert "grubx64" in ubuntu
    assert "shimx64" in ubuntu
    boot = _esp_mdir(disk_path, "/EFI/BOOT")
    # Shim chainloads grub from beside itself, so the removable path
    # needs its own copy for the fallback boot to work.
    assert "BOOTX64" in boot
    assert "grubx64" in boot

    with _mount_ext_partition(disk_path, "rootfs") as rootfs:
        cfg = (rootfs / "boot/grub/grub.cfg").read_text()
        assert "vmlinuz-6.8.0-generic" in cfg
        assert "initrd.img-6.8.0-generic" in cfg


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_unsigned_requires_grub_mkimage_in_image(
    new_dir, fake_kernel_files
):
    """The in-image grub-mkimage is required; modules alone do not suffice."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path("/usr/lib/grub/x86_64-efi"), root_content / "usr/lib/grub/x86_64-efi"
    )
    fake_kernel_files(root_content / "boot")
    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)

    volume = _make_volume(boot_partition=False)
    disk_path = tmp_path / "disk.img"
    gptutil.create_empty_gpt_image(imagepath=disk_path, sector_size=512, layout=volume)
    for item, content in (
        (volume.structure[0], esp_content),
        (volume.structure[1], root_content),
    ):
        _build_and_inject_partition(
            disk_path=disk_path,
            tmp_path=tmp_path,
            fstype=item.filesystem,
            content_dir=content,
            label=item.filesystem_label,
            partition_name=item.name,
        )

    image = Image(volume=volume, disk_path=disk_path)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
        ]
    )

    with pytest.raises(errors.GRUBInstallError, match="grub-mkimage failed"):
        grubutil.setup_grub(
            image=image,
            workdir=tmp_path / "work",
            arch=DebianArchitecture.AMD64,
            filesystem_mount=filesystem_mount,
        )


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_skips_without_grub_modules(new_dir, fake_kernel_files, emitter):
    """A rootfs with no GRUB package installed gets no bootloader, not an error."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    fake_kernel_files(root_content / "boot")
    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)

    volume = _make_volume(boot_partition=False)
    disk_path = tmp_path / "disk.img"
    gptutil.create_empty_gpt_image(imagepath=disk_path, sector_size=512, layout=volume)
    for item, content in (
        (volume.structure[0], esp_content),
        (volume.structure[1], root_content),
    ):
        _build_and_inject_partition(
            disk_path=disk_path,
            tmp_path=tmp_path,
            fstype=item.filesystem,
            content_dir=content,
            label=item.filesystem_label,
            partition_name=item.name,
        )

    image = Image(volume=volume, disk_path=disk_path)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
        ]
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    emitter.assert_progress(
        "Cannot install GRUB on this rootfs: GRUB modules for x86_64-efi "
        "are not installed in the image",
        permanent=True,
    )


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_unsigned(new_dir, fake_kernel_files):
    """Without signed shim/GRUB, an unsigned standalone image is built."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path("/usr/lib/grub/x86_64-efi"), root_content / "usr/lib/grub/x86_64-efi"
    )
    _copy_grub_mkimage(root_content)
    fake_kernel_files(root_content / "boot")
    (root_content / "etc/default").mkdir(parents=True)
    (root_content / "etc/default/grub").write_text(
        'GRUB_CMDLINE_LINUX_DEFAULT="console=ttyS0,115200n8"\n'
    )

    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)

    volume = _make_volume(boot_partition=False)
    disk_path = tmp_path / "disk.img"
    gptutil.create_empty_gpt_image(imagepath=disk_path, sector_size=512, layout=volume)
    for item, content in (
        (volume.structure[0], esp_content),
        (volume.structure[1], root_content),
    ):
        _build_and_inject_partition(
            disk_path=disk_path,
            tmp_path=tmp_path,
            fstype=item.filesystem,
            content_dir=content,
            label=item.filesystem_label,
            partition_name=item.name,
        )

    image = Image(volume=volume, disk_path=disk_path)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
        ]
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    ubuntu = _esp_mdir(disk_path, "/EFI/ubuntu")
    assert "grubx64" in ubuntu
    # No signed shim was available, so no shim binary should be deployed.
    assert "shimx64" not in ubuntu

    with _mount_ext_partition(disk_path, "rootfs") as rootfs:
        cfg = (rootfs / "boot/grub/grub.cfg").read_text()
        assert "console=ttyS0,115200n8" in cfg
        # The temporary in-image build output must not ship in the final image.
        assert not (rootfs / "tmp/imagecraft-grubx64.efi").exists()


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_efi_separate_boot_partition(new_dir, fake_kernel_files):
    """With a dedicated /boot partition, its root (not /boot/...) holds GRUB/kernels."""
    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path("/usr/lib/grub/x86_64-efi"), root_content / "usr/lib/grub/x86_64-efi"
    )
    _copy_grub_mkimage(root_content)
    boot_content = tmp_path / "boot_content"
    fake_kernel_files(boot_content)

    esp_content = tmp_path / "esp_content"
    (esp_content / "EFI/BOOT").mkdir(parents=True)

    volume = _make_volume(boot_partition=True)
    disk_path = tmp_path / "disk.img"
    gptutil.create_empty_gpt_image(imagepath=disk_path, sector_size=512, layout=volume)
    content_map = {"efi": esp_content, "boot": boot_content, "rootfs": root_content}
    for item in volume.structure:
        _build_and_inject_partition(
            disk_path=disk_path,
            tmp_path=tmp_path,
            fstype=item.filesystem,
            content_dir=content_map[item.name],
            label=item.filesystem_label,
            partition_name=item.name,
        )

    image = Image(volume=volume, disk_path=disk_path)
    filesystem_mount = FilesystemMount.unmarshal(
        [
            {"mount": "/", "device": "(volume/pc/rootfs)"},
            {"mount": "/boot/", "device": "(volume/pc/boot)"},
            {"mount": "/boot/efi/", "device": "(volume/pc/efi)"},
        ]
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    with _mount_ext_partition(disk_path, "boot") as bootfs:
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
            disk_path,
            gptutil.get_partition_sector_offset(disk_path, "boot") * 512,
        )

    root_uuid = grubutil._read_ext_uuid(
        disk_path,
        gptutil.get_partition_sector_offset(disk_path, "rootfs") * 512,
    )

    assert boot_uuid != root_uuid
    # GRUB loads the kernel off the boot partition but boots the root one.
    assert f"search --no-floppy --fs-uuid --set=root {boot_uuid}" in cfg
    assert f"root=UUID={root_uuid}" in cfg

    stub = _esp_type(disk_path, "/EFI/ubuntu/grub.cfg")
    # The ESP stub has to chain to the config on the boot partition.
    assert f"search.fs_uuid {boot_uuid} root" in stub
    assert "set prefix=($root)'/grub'" in stub


@pytest.mark.slow
@pytest.mark.requires_root
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_bios_mbr(new_dir, fake_kernel_files):
    """Legacy BIOS/MBR: core.img is embedded and the boot sector patched by hand."""
    from imagecraft.models.volume import (  # noqa: PLC0415
        FileSystem,
        MBRPartitionType,
        Role,
    )

    tmp_path = Path(new_dir)
    root_content = tmp_path / "root_content"
    _copy_grub_target_files(
        Path("/usr/lib/grub/i386-pc"), root_content / "usr/lib/grub/i386-pc"
    )
    _copy_grub_mkimage(root_content)
    fake_kernel_files(root_content / "boot")

    volume = MBRVolume(
        schema=PartitionSchema.MBR,
        structure=[
            MBRStructureItem(
                name="rootfs",
                role=Role.SYSTEM_DATA,
                size="256M",
                filesystem=FileSystem.EXT4,
                type=MBRPartitionType("83"),
                filesystem_label="writable",
            ),
        ],
    )
    disk_path = tmp_path / "disk.img"
    mbrutil.create_empty_mbr_image(imagepath=disk_path, sector_size=512, layout=volume)
    _build_and_inject_partition(
        disk_path=disk_path,
        tmp_path=tmp_path,
        fstype=volume.structure[0].filesystem,
        content_dir=root_content,
        label=volume.structure[0].filesystem_label,
        partition_name="rootfs",
        partition_number=1,
    )
    mbrutil.verify_partition_tables(disk_path)

    image = Image(volume=volume, disk_path=disk_path)
    filesystem_mount = FilesystemMount.unmarshal(
        [{"mount": "/", "device": "(volume/pc/rootfs)"}]
    )

    grubutil.setup_grub(
        image=image,
        workdir=tmp_path / "work",
        arch=DebianArchitecture.AMD64,
        filesystem_mount=filesystem_mount,
    )

    with disk_path.open("rb") as f:
        sector0 = f.read(512)
    # Boot signature must be preserved.
    assert sector0[0x1FE:0x200] == b"\x55\xaa"
    kernel_sector = int.from_bytes(sector0[0x5C:0x64], "little")
    assert kernel_sector == grubutil._BIOS_CORE_IMG_START_SECTOR

    with disk_path.open("rb") as f:
        f.seek(kernel_sector * 512)
        core_start = f.read(512)
    # core.img was embedded in the gap and isn't all zeros/empty.
    assert any(core_start)
    # core.img's own embedded blocklist must point past its first sector,
    # or SeaBIOS hangs loading the rest of core.img from the wrong place.
    blocklist_start = int.from_bytes(
        core_start[
            grubutil._BIOS_BLOCKLIST_START_OFFSET : grubutil._BIOS_BLOCKLIST_START_OFFSET
            + 8
        ],
        "little",
    )
    assert blocklist_start == kernel_sector + 1

    with _mount_ext_partition(disk_path, "rootfs", number=1) as rootfs:
        assert (rootfs / "boot/grub/i386-pc/core.img").is_file()
        assert (rootfs / "boot/grub/i386-pc/boot.img").is_file()
        cfg = (rootfs / "boot/grub/grub.cfg").read_text()
        assert "vmlinuz-6.8.0-generic" in cfg
