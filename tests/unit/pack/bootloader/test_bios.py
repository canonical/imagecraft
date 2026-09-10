# This file is part of imagecraft.
#
# Copyright 2026 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Unit tests for the BIOS (non-EFI) installer."""

import uuid
from pathlib import Path

import pytest
from craft_platforms import DebianArchitecture
from imagecraft import errors
from imagecraft.pack.bootloader.bios import PCBiosInstaller
from imagecraft.pack.bootloader.chrootenv import stage_grub_modules

from .test_installer import BOOT_ITEM, ROOT_ITEM, _mbr_volume


def _make_installer(tmp_path: Path, **kwargs) -> PCBiosInstaller:
    kwargs.setdefault("arch", DebianArchitecture.AMD64)
    kwargs.setdefault("root_uuid", uuid.uuid4())
    volume = kwargs.pop("volume", None) or _mbr_volume([{**ROOT_ITEM, "type": "83"}])
    return PCBiosInstaller(
        image_path=tmp_path / "disk.img",
        root_dir=tmp_path / "root",
        volume=volume,
        **kwargs,
    )


class TestPCBiosInstallerChecks:
    @pytest.mark.parametrize("filesystem", ["fat16", "vfat"])
    def test_fat_boot_requires_fat_module(self, tmp_path, filesystem):
        volume = _mbr_volume(
            [
                {**BOOT_ITEM, "type": "0C", "filesystem": filesystem},
                {**ROOT_ITEM, "type": "83"},
            ]
        )
        mod_dir = tmp_path / "root/usr/lib/grub/i386-pc"
        mod_dir.mkdir(parents=True)
        installer = _make_installer(tmp_path, volume=volume, boot_uuid="1234-ABCD")

        with pytest.raises(errors.BootloaderToolsMissingError, match="FAT module"):
            installer.install()

    def test_embeds_fat_module(self, tmp_path, mocker):
        volume = _mbr_volume(
            [
                {**BOOT_ITEM, "type": "0C", "filesystem": "vfat"},
                {**ROOT_ITEM, "type": "83"},
            ]
        )
        installer = _make_installer(tmp_path, volume=volume, boot_uuid="1234-ABCD")
        mod_dir = installer.root_dir / "usr/lib/grub/i386-pc"
        mod_dir.mkdir(parents=True)
        for name in ("boot.img", "grub-bios-setup", "fat.mod", "ext2.mod"):
            (mod_dir / name).touch()
        mocker.patch(
            "imagecraft.pack.bootloader.bios.require_chroot_binary",
            return_value=Path("usr/bin/grub-mkimage"),
        )
        mocker.patch(
            "imagecraft.pack.bootloader.bios.shutil.which", return_value="fuse2fs"
        )
        mocker.patch.object(installer, "_root_partition_offset", return_value=2048)
        mount = mocker.patch("imagecraft.pack.bootloader.bios.ExtFuseMount")
        mount.return_value.__enter__.return_value = installer.root_dir
        chroot = mocker.patch("imagecraft.pack.bootloader.bios.build_prime_chroot")
        chroot.return_value.execute.return_value = ""

        installer.install()

        assert "fat" in chroot.return_value.execute.call_args.kwargs["modules"]

    def test_arch_without_non_efi_target_rejected(self, tmp_path):
        with pytest.raises(errors.BootloaderError, match="no non-EFI GRUB target"):
            _make_installer(tmp_path, arch=DebianArchitecture.ARM64)

    def test_missing_modules_dir(self, tmp_path):
        (tmp_path / "root").mkdir()
        installer = _make_installer(tmp_path)
        with pytest.raises(errors.BootloaderToolsMissingError, match="modules"):
            installer.install()

    def test_missing_boot_img(self, tmp_path):
        mod_dir = tmp_path / "root" / "usr" / "lib" / "grub" / "i386-pc"
        mod_dir.mkdir(parents=True)
        installer = _make_installer(tmp_path)
        with pytest.raises(errors.BootloaderToolsMissingError, match="boot.img"):
            installer.install()

    def test_missing_bios_setup(self, tmp_path):
        mod_dir = tmp_path / "root" / "usr" / "lib" / "grub" / "i386-pc"
        mod_dir.mkdir(parents=True)
        (mod_dir / "boot.img").write_bytes(b"x" * 512)
        installer = _make_installer(tmp_path)
        with pytest.raises(errors.BootloaderToolsMissingError, match="grub-bios-setup"):
            installer.install()

    def test_missing_mkimage(self, tmp_path):
        mod_dir = tmp_path / "root" / "usr" / "lib" / "grub" / "i386-pc"
        mod_dir.mkdir(parents=True)
        (mod_dir / "boot.img").write_bytes(b"x" * 512)
        (mod_dir / "grub-bios-setup").write_bytes(b"x")
        installer = _make_installer(tmp_path)
        with pytest.raises(errors.BootloaderToolsMissingError, match="grub-mkimage"):
            installer.install()

    def test_dedicated_boot_uuid_changes_search_and_prefix(self, tmp_path):
        boot_uuid = uuid.uuid4()
        installer = _make_installer(tmp_path, boot_uuid=boot_uuid)
        assert installer.search_uuid == str(boot_uuid)
        assert installer.boot_prefix == "/grub"

    def test_shared_boot_uses_root_uuid(self, tmp_path):
        root_uuid = uuid.uuid4()
        installer = _make_installer(tmp_path, root_uuid=root_uuid)
        assert installer.search_uuid == str(root_uuid)
        assert installer.boot_prefix == "/boot/grub"


class TestRootPartitionOffset:
    def _offset(self, mocker, installer: PCBiosInstaller) -> tuple[int, int]:
        offset_mock = mocker.patch(
            "imagecraft.pack.bootloader.bios.gptutil"
            ".get_partition_sector_offset_by_number",
            return_value=2048,
        )
        offset = installer._root_partition_offset()
        return offset_mock.call_args[0][1], offset

    def test_simple_mbr_root_is_partition_one(self, tmp_path, mocker):
        installer = _make_installer(tmp_path)
        part_num, offset = self._offset(mocker, installer)
        assert part_num == 1
        assert offset == 2048 * 512

    def test_extended_mbr_root_skips_slot_four(self, tmp_path, mocker):
        """With >4 MBR entries, slot 4 is the extended container."""
        items = [
            {
                "name": name,
                "type": "83",
                "filesystem": "ext4",
                "role": role,
                "size": "100M",
            }
            for name, role in [
                ("boot", "system-boot"),
                ("seed", "system-seed"),
                ("save", "system-save"),
                ("rootfs", "system-data"),
                ("extra", "system-data"),
            ]
        ]
        installer = _make_installer(tmp_path, volume=_mbr_volume(items))
        part_num, _ = self._offset(mocker, installer)
        assert part_num == 5


class TestStageGrubModules:
    def test_copies_modules_to_boot(self, tmp_path):
        root = tmp_path / "root"
        mod_dir = root / "usr" / "lib" / "grub" / "i386-pc"
        mod_dir.mkdir(parents=True)
        (mod_dir / "normal.mod").write_bytes(b"x")
        stage_grub_modules(root, None, "i386-pc")
        target = root / "boot" / "grub" / "i386-pc"
        assert (target / "normal.mod").is_file()

    def test_copies_modules_to_dedicated_boot(self, tmp_path):
        root = tmp_path / "root"
        boot = tmp_path / "boot"
        boot.mkdir()
        mod_dir = root / "usr" / "lib" / "grub" / "i386-pc"
        mod_dir.mkdir(parents=True)
        (mod_dir / "normal.mod").write_bytes(b"x")
        stage_grub_modules(root, boot, "i386-pc")
        target = boot / "grub" / "i386-pc"
        assert (target / "normal.mod").is_file()
        assert not (root / "boot" / "grub").exists()

    def test_missing_modules_raises(self, tmp_path):
        with pytest.raises(errors.BootloaderToolsMissingError):
            stage_grub_modules(tmp_path, None, "i386-pc")
