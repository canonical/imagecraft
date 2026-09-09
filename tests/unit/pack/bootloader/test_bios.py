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
from imagecraft.pack.bootloader.bios import NonEfiInstaller, stage_non_efi_modules

from .test_installer import ROOT_ITEM, _mbr_volume


def _make_installer(tmp_path: Path, **kwargs) -> NonEfiInstaller:
    volume = _mbr_volume([{**ROOT_ITEM, "type": "83"}])
    return NonEfiInstaller(
        image_path=tmp_path / "disk.img",
        root_dir=tmp_path / "root",
        root_uuid=uuid.uuid4(),
        arch=DebianArchitecture.AMD64,
        volume=volume,
        **kwargs,
    )


class TestNonEfiInstallerChecks:
    def test_arch_without_non_efi_target_rejected(self, tmp_path):
        volume = _mbr_volume([{**ROOT_ITEM, "type": "83"}])
        with pytest.raises(errors.BootloaderError, match="no non-EFI GRUB target"):
            NonEfiInstaller(
                image_path=tmp_path / "disk.img",
                root_dir=tmp_path / "root",
                root_uuid=uuid.uuid4(),
                arch=DebianArchitecture.ARM64,
                volume=volume,
            )

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
        root_uuid = uuid.uuid4()
        boot_uuid = uuid.uuid4()
        volume = _mbr_volume([{**ROOT_ITEM, "type": "83"}])
        installer = NonEfiInstaller(
            image_path=tmp_path / "disk.img",
            root_dir=tmp_path / "root",
            root_uuid=root_uuid,
            arch=DebianArchitecture.AMD64,
            volume=volume,
            boot_uuid=boot_uuid,
        )
        assert installer.search_uuid == str(boot_uuid)
        assert installer.boot_prefix == "/grub"

    def test_shared_boot_uses_root_uuid(self, tmp_path):
        installer = _make_installer(tmp_path)
        assert installer.search_uuid == installer.root_uuid
        assert installer.boot_prefix == "/boot/grub"


class TestStageNonEfiModules:
    def test_copies_modules_to_boot(self, tmp_path):
        root = tmp_path / "root"
        mod_dir = root / "usr" / "lib" / "grub" / "i386-pc"
        mod_dir.mkdir(parents=True)
        (mod_dir / "normal.mod").write_bytes(b"x")
        target = stage_non_efi_modules(root, grub_format="i386-pc")
        assert target == root / "boot" / "grub" / "i386-pc"
        assert (target / "normal.mod").is_file()

    def test_copies_modules_to_dedicated_boot(self, tmp_path):
        root = tmp_path / "root"
        boot = tmp_path / "boot"
        boot.mkdir()
        mod_dir = root / "usr" / "lib" / "grub" / "i386-pc"
        mod_dir.mkdir(parents=True)
        (mod_dir / "normal.mod").write_bytes(b"x")
        target = stage_non_efi_modules(root, boot, grub_format="i386-pc")
        assert target == boot / "grub" / "i386-pc"
        assert (target / "normal.mod").is_file()
        assert not (root / "boot" / "grub").exists()

    def test_missing_modules_raises(self, tmp_path):
        with pytest.raises(errors.BootloaderToolsMissingError):
            stage_non_efi_modules(tmp_path, grub_format="i386-pc")
