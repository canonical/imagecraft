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

"""Integration tests for GRUB installation via imagecraft.pack.grubutil."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from craft_parts.filesystem_mounts import FilesystemMount
from craft_platforms import DebianArchitecture
from imagecraft.models import FileSystem, GPTVolume
from imagecraft.pack import diskutil, gptutil, grubutil
from imagecraft.pack.image import Image
from imagecraft.utils import mount


@pytest.fixture
def rootfs_with_grub(tmp_path: Path) -> Path:
    """Build a minimal Ubuntu 26.04 rootfs containing GRUB and a Linux kernel.

    The fixture uses ``chisel`` to cut a minimal root file system, then uses
    ``apt`` inside a chroot to install ``grub-efi-amd64-bin`` and
    ``linux-image-generic``.  It skips the test when ``chisel`` is not
    available.
    """
    if shutil.which("chisel") is None:
        pytest.skip("chisel is required to build the test rootfs")

    rootfs = tmp_path / "rootfs"
    rootfs.mkdir()

    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"

    slices = [
        "base-files_base",
        "base-files_release-info",
        "base-files_chisel",
        "base-files_bin",
        "base-files_tmp",
        "base-files_var",
        "base-files_etc",
        "ca-certificates_data",
        "apt_apt-get",
        "dpkg_bins",
        "bash_bins",
    ]
    subprocess.run(
        [
            "chisel",
            "cut",
            "--release",
            "ubuntu-26.04",
            "--root",
            str(rootfs),
            "--arch",
            "amd64",
            *slices,
        ],
        check=True,
        env=env,
    )

    # Provide basic identity databases and DNS resolution so apt and
    # maintainer scripts can run inside the chroot.
    (rootfs / "etc" / "passwd").write_text("root:x:0:0:root:/root:/bin/bash\n")
    (rootfs / "etc" / "group").write_text(
        "root:x:0:\nmail:x:8:\ntty:x:5:\nutmp:x:43:\n"
    )
    _write_resolv_conf(rootfs)

    virtual_dirs = ["dev", "dev/pts", "proc", "sys", "run"]
    for name in virtual_dirs:
        (rootfs / name).mkdir(parents=True, exist_ok=True)
    subprocess.run(["mount", "--bind", "/dev", str(rootfs / "dev")], check=True)
    subprocess.run(
        ["mount", "--bind", "/dev/pts", str(rootfs / "dev" / "pts")], check=True
    )
    subprocess.run(["mount", "--bind", "/proc", str(rootfs / "proc")], check=True)
    subprocess.run(["mount", "--bind", "/sys", str(rootfs / "sys")], check=True)
    subprocess.run(["mount", "--bind", "/run", str(rootfs / "run")], check=True)

    try:
        subprocess.run(
            ["chroot", str(rootfs), "/usr/bin/apt-get", "update"],
            check=True,
            env=env,
        )
        subprocess.run(
            [
                "chroot",
                str(rootfs),
                "/usr/bin/apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "debconf",
                "perl-base",
            ],
            check=True,
            env=env,
        )
        subprocess.run(
            [
                "chroot",
                str(rootfs),
                "/usr/bin/apt-get",
                "install",
                "-y",
                "--no-install-recommends",
                "grub-efi-amd64-bin",
                "linux-image-generic",
                "libc-bin",
                "zstd",
                "kmod",
                "grep",
                "mawk",
                "findutils",
                "debianutils",
                "util-linux",
                "hostname",
            ],
            check=True,
            env=env,
        )
        subprocess.run(
            ["chroot", str(rootfs), "/usr/bin/apt-get", "clean"],
            check=True,
            env=env,
        )
    finally:
        for name in reversed(virtual_dirs):
            subprocess.run(["umount", str(rootfs / name)], check=True)

    (rootfs / "boot" / "grub").mkdir(parents=True, exist_ok=True)
    (rootfs / "boot" / "efi").mkdir(parents=True, exist_ok=True)

    fstab = rootfs / "etc" / "fstab"
    fstab.parent.mkdir(parents=True, exist_ok=True)
    fstab.write_text("LABEL=writable / ext4 defaults 0 1\n")

    return rootfs


def _write_resolv_conf(rootfs: Path) -> None:
    """Write a minimal resolv.conf using the host's upstream DNS servers.

    systemd-resolved's stub resolver (127.0.0.53) is not reachable inside a
    chroot, so copy the real upstream nameservers from its resolv.conf.
    """
    resolved_conf = Path("/run/systemd/resolve/resolv.conf")
    upstream = "8.8.8.8"
    if resolved_conf.exists():
        for line in resolved_conf.read_text().splitlines():
            if line.startswith("nameserver"):
                candidate = line.split()[1]
                if not candidate.startswith(("127.", "::1", "fe80:")):
                    upstream = candidate
                    break
    (rootfs / "etc" / "resolv.conf").write_text(f"nameserver {upstream}\n")


@pytest.mark.slow
@pytest.mark.requires_root
def test_setup_grub_installs_grub_efi(rootfs_with_grub: Path, tmp_path: Path, emitter):
    """Create a minimal GPT disk with ESP + root and verify setup_grub installs EFI."""
    sector_size = gptutil.SECTOR_SIZE_512
    volume = GPTVolume.unmarshal(
        {
            "schema": "gpt",
            "structure": [
                {
                    "name": "efi",
                    "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                    "filesystem": "vfat",
                    "filesystem-label": "",
                    "role": "system-boot",
                    "size": "200M",
                },
                {
                    "name": "rootfs",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "filesystem-label": "writable",
                    "role": "system-data",
                    "size": "4G",
                },
            ],
        }
    )
    image_path = tmp_path / "pc.img"
    gptutil.create_empty_gpt_image(image_path, sector_size, volume)

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    # fusefat incorrectly exposes a FAT volume label as a regular root file.
    for item in volume.structure:
        part_file = tmp_path / f"{item.name}.img"
        with part_file.open("wb") as f:
            f.truncate(int(item.size))
        content_dir = (
            rootfs_with_grub if item.role.value == "system-data" else empty_dir
        )
        diskutil.format_populate_partition(
            fstype=item.filesystem,
            content_dir=content_dir,
            partitionpath=part_file,
            label=None if item.filesystem == FileSystem.VFAT else item.filesystem_label,
        )
        start_sector = gptutil.get_partition_sector_offset(image_path, item.name)
        diskutil.inject_partition_into_image(
            partition=part_file,
            imagepath=image_path,
            sector_offset=start_sector,
            disk_size=diskutil.DiskSize(
                bytesize=int(item.size), sector_size=sector_size
            ),
        )
    image = Image(volume=volume, disk_path=image_path)
    grubutil.setup_grub(
        image=image,
        workdir=tmp_path,
        arch=DebianArchitecture.AMD64,
        filesystem_mount=FilesystemMount.unmarshal(
            [
                {"mount": "/", "device": "(volume/pc/rootfs)"},
                {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
            ]
        ),
    )

    mountpoint = tmp_path / "verify"
    mountpoint.mkdir()
    root_mount = mount.mount_partition(
        image_path,
        FileSystem.EXT4,
        offset=gptutil.get_partition_sector_offset_by_number(image_path, 2)
        * sector_size,
        mountpoint=mountpoint,
        read_only=True,
        allow_other=True,
    )
    esp_mountpoint = tmp_path / "verify-esp"
    esp_mountpoint.mkdir()
    esp_mount = mount.mount_partition(
        image_path,
        FileSystem.VFAT,
        offset=gptutil.get_partition_sector_offset_by_number(image_path, 1)
        * sector_size,
        size=gptutil.get_partition_size_sectors_by_number(image_path, 1) * sector_size,
        mountpoint=esp_mountpoint,
        read_only=True,
        allow_other=True,
    )
    try:
        root_mount.mount()
        esp_mount.mount()
        grub_cfg = mountpoint / "boot" / "grub" / "grub.cfg"
        assert grub_cfg.exists(), "GRUB configuration file was not generated"
        cfg_text = grub_cfg.read_text()
        assert "generated by grub-mkconfig" in cfg_text, (
            "grub.cfg was not generated by update-grub"
        )

        boot_efi = esp_mountpoint / "EFI" / "BOOT" / "BOOTX64.EFI"
        assert boot_efi.exists(), "EFI bootloader was not installed"
    finally:
        esp_mount.unmount(lazy=True)
        root_mount.unmount(lazy=True)
