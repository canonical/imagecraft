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
"""Unit tests for the EFI installer."""

import uuid

import pytest
from craft_platforms import DebianArchitecture
from imagecraft import errors
from imagecraft.pack.bootloader.efi import EfiInstaller, write_esp_stub
from imagecraft.pack.bootloader.models import EfiTier


class TestWriteEspStub:
    def test_shared_boot_stub(self, tmp_path):
        root_uuid = uuid.uuid4()
        stub = write_esp_stub(tmp_path / "EFI" / "BOOT" / "grub.cfg", root_uuid)
        content = stub.read_text()
        assert f"search.fs_uuid {root_uuid} root" in content
        assert "($root)'/boot/grub'" in content

    def test_dedicated_boot_stub(self, tmp_path):
        boot_uuid = uuid.uuid4()
        stub = write_esp_stub(tmp_path / "grub.cfg", boot_uuid, boot_prefix="/grub")
        content = stub.read_text()
        assert f"search.fs_uuid {boot_uuid} root" in content
        assert "($root)'/grub'" in content


def _make_installer(tmp_path, **kwargs) -> EfiInstaller:
    root_dir = tmp_path / "root"
    esp_dir = tmp_path / "esp"
    root_dir.mkdir(exist_ok=True)
    esp_dir.mkdir(exist_ok=True)
    return EfiInstaller(
        root_dir=root_dir,
        esp_dir=esp_dir,
        root_uuid=uuid.uuid4(),
        arch=DebianArchitecture.AMD64,
        **kwargs,
    )


def _add_signed(root_dir):
    shim = root_dir / "usr" / "lib" / "shim"
    shim.mkdir(parents=True)
    (shim / "shimx64.efi.signed").write_bytes(b"shim")
    signed = root_dir / "usr" / "lib" / "grub" / "x86_64-efi-signed"
    signed.mkdir(parents=True)
    (signed / "grubx64.efi.signed").write_bytes(b"grub")
    modules = root_dir / "usr" / "lib" / "grub" / "x86_64-efi"
    modules.mkdir(parents=True)
    (modules / "normal.mod").write_bytes(b"mod")


def _add_unsigned_prebuilt(root_dir):
    monolithic = root_dir / "usr" / "lib" / "grub" / "x86_64-efi" / "monolithic"
    monolithic.mkdir(parents=True)
    (monolithic / "grubx64.efi").write_bytes(b"grub")


class TestEfiTiers:
    def test_signed_tier(self, tmp_path):
        _add_signed(tmp_path / "root")
        installer = _make_installer(tmp_path)
        assert installer.install() == EfiTier.SIGNED
        assert (tmp_path / "esp" / "EFI" / "BOOT" / "BOOTX64.EFI").is_file()

    def test_unsigned_prebuilt_tier(self, tmp_path):
        _add_unsigned_prebuilt(tmp_path / "root")
        installer = _make_installer(tmp_path)
        assert installer.install() == EfiTier.UNSIGNED_PREBUILT

    def test_fallback_build_needs_modules(self, tmp_path):
        """Without any GRUB EFI modules in the rootfs, fail as tools-missing."""
        installer = _make_installer(tmp_path)
        with pytest.raises(errors.BootloaderToolsMissingError):
            installer.install()

    def test_boot_uuid_wiring(self, tmp_path):
        boot_uuid = uuid.uuid4()
        installer = _make_installer(tmp_path, boot_uuid=boot_uuid)
        assert installer.search_uuid == str(boot_uuid)
        assert installer.boot_prefix == "/grub"
        _add_signed(tmp_path / "root")
        installer.install()
        stub = (tmp_path / "esp" / "EFI" / "BOOT" / "grub.cfg").read_text()
        assert str(boot_uuid) in stub
        assert "($root)'/grub'" in stub
