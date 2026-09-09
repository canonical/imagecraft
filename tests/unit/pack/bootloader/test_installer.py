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
"""Unit tests for the bootloader installer coordinator."""

import uuid

from craft_platforms import DebianArchitecture
from imagecraft import errors
from imagecraft.models.volume import GPTVolume, HybridVolume, MBRVolume
from imagecraft.pack.bootloader import installer as installer_mod
from imagecraft.pack.bootloader.installer import (
    BootloaderInstaller,
    BootMethod,
    find_boot_structure_item,
    find_esp_structure_item,
    find_root_structure_item,
)

_AMD64 = DebianArchitecture.AMD64

ESP_GUID = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
LINUX_DATA_GUID = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
BIOS_BOOT_GUID = "21686148-6449-6E6F-744E-656564454649"


def _gpt_volume(structure: list[dict]) -> GPTVolume:
    return GPTVolume.model_validate({"schema": "gpt", "structure": structure})


def _mbr_volume(structure: list[dict]) -> MBRVolume:
    return MBRVolume.model_validate({"schema": "mbr", "structure": structure})


def _hybrid_volume(structure: list[dict]) -> HybridVolume:
    return HybridVolume.model_validate({"schema": "mbr,gpt", "structure": structure})


ESP_ITEM = {
    "name": "efi",
    "type": ESP_GUID,
    "filesystem": "vfat",
    "role": "system-boot",
    "filesystem-label": "ESP",
    "size": "256M",
}
ROOT_ITEM = {
    "name": "rootfs",
    "type": LINUX_DATA_GUID,
    "filesystem": "ext4",
    "filesystem-label": "writable",
    "role": "system-data",
    "size": "2G",
}
BOOT_ITEM = {
    "name": "boot",
    "type": LINUX_DATA_GUID,
    "filesystem": "ext4",
    "filesystem-label": "boot",
    "role": "system-boot",
    "size": "256M",
}
BIOS_BOOT_ITEM = {
    "name": "biosboot",
    "type": BIOS_BOOT_GUID,
    "filesystem": "ext4",
    "role": "system-boot",
    "size": "2M",
}


class TestFindStructureItems:
    def test_root_and_esp_found(self):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        assert find_root_structure_item(volume).name == "rootfs"  # type: ignore[union-attr]
        assert find_esp_structure_item(volume).name == "efi"  # type: ignore[union-attr]

    def test_no_esp_for_mbr(self):
        volume = _mbr_volume(
            [
                {**ROOT_ITEM, "type": "83"},
            ]
        )
        assert find_esp_structure_item(volume) is None
        assert find_root_structure_item(volume).name == "rootfs"  # type: ignore[union-attr]

    def test_hybrid_esp_detected(self):
        """Hybrid items encode the GPT type as '<mbr>,<gpt>'; must still match."""
        volume = _hybrid_volume(
            [
                {**ESP_ITEM, "type": f"0C,{ESP_GUID}"},
                {**ROOT_ITEM, "type": f"83,{LINUX_DATA_GUID}"},
            ]
        )
        esp = find_esp_structure_item(volume)
        assert esp is not None
        assert esp.name == "efi"

    def test_hybrid_lowercase_guid(self):
        volume = _hybrid_volume(
            [
                {**ESP_ITEM, "type": f"0c,{ESP_GUID.lower()}"},
                {**ROOT_ITEM, "type": f"83,{LINUX_DATA_GUID.lower()}"},
            ]
        )
        assert find_esp_structure_item(volume) is not None

    def test_boot_item_is_none_when_only_esp(self):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        assert find_boot_structure_item(volume) is None

    def test_boot_item_found_when_distinct_from_esp(self):
        volume = _gpt_volume([ESP_ITEM, BOOT_ITEM, ROOT_ITEM])
        boot = find_boot_structure_item(volume)
        assert boot is not None
        assert boot.name == "boot"

    def test_boot_item_found_for_mbr(self):
        volume = _mbr_volume(
            [
                {**BOOT_ITEM, "type": "83"},
                {**ROOT_ITEM, "type": "83"},
            ]
        )
        boot = find_boot_structure_item(volume)
        assert boot is not None
        assert boot.name == "boot"

    def test_bios_boot_partition_is_not_a_boot_partition(self):
        """A raw BIOS Boot partition (core.img embedding area) is not /boot."""
        volume = _gpt_volume([BIOS_BOOT_ITEM, ROOT_ITEM])
        assert find_boot_structure_item(volume) is None


class TestResolveBootMethod:
    def test_no_root_partition(self):
        volume = _gpt_volume([ESP_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        assert installer.resolve_boot_method() == BootMethod.NONE

    def test_efi_when_esp_present(self):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        assert installer.resolve_boot_method() == BootMethod.EFI

    def test_efi_when_esp_present_hybrid(self):
        volume = _hybrid_volume(
            [
                {**ESP_ITEM, "type": f"0C,{ESP_GUID}"},
                {**ROOT_ITEM, "type": f"83,{LINUX_DATA_GUID}"},
            ]
        )
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        assert installer.resolve_boot_method() == BootMethod.EFI

    def test_bios_for_mbr(self):
        volume = _mbr_volume([{**ROOT_ITEM, "type": "83"}])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        assert installer.resolve_boot_method() == BootMethod.BIOS

    def test_bios_for_gpt_with_bios_boot_partition(self):
        volume = _gpt_volume([BIOS_BOOT_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        assert installer.resolve_boot_method() == BootMethod.BIOS

    def test_bios_for_hybrid_with_bios_boot_partition(self):
        volume = _hybrid_volume(
            [
                {**BIOS_BOOT_ITEM, "type": f"83,{BIOS_BOOT_GUID}"},
                {**ROOT_ITEM, "type": f"83,{LINUX_DATA_GUID}"},
            ]
        )
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        assert installer.resolve_boot_method() == BootMethod.BIOS

    def test_none_for_gpt_without_esp_or_bios_boot(self):
        volume = _gpt_volume([ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        assert installer.resolve_boot_method() == BootMethod.NONE

    def test_none_for_bios_incable_arch(self):
        volume = _mbr_volume([{**ROOT_ITEM, "type": "83"}])
        installer = BootloaderInstaller(volume=volume, arch=DebianArchitecture.ARM64)
        assert installer.resolve_boot_method() == BootMethod.NONE

    def test_none_for_unknown_arch_string(self):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch="not-an-arch")
        assert installer.resolve_boot_method() == BootMethod.NONE

    def test_none_for_valid_arch_without_spec(self):
        """Valid DebianArchitecture values missing from ARCH_SPECS skip cleanly."""
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=DebianArchitecture.S390X)
        assert installer.resolve_boot_method() == BootMethod.NONE


class TestGracefulSkip:
    """Missing GRUB tooling in the rootfs must not crash pack."""

    def test_prepare_rootfs_skips_when_mkconfig_missing(self, tmp_path, mocker):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        root_dir = tmp_path / "root"
        esp_dir = tmp_path / "esp"
        root_dir.mkdir()
        esp_dir.mkdir()
        mocker.patch.object(
            installer_mod,
            "generate_grub_cfg",
            side_effect=errors.BootloaderToolsMissingError("no grub-mkconfig"),
        )
        boot_method = installer.prepare_rootfs(
            root_dir=root_dir, esp_dir=esp_dir, root_uuid=uuid.uuid4()
        )
        assert boot_method == BootMethod.NONE
        # fstab is still written even when GRUB tooling is missing.
        assert (root_dir / "etc" / "fstab").is_file()

    def test_prepare_rootfs_skips_efi_when_modules_missing(self, tmp_path, mocker):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        root_dir = tmp_path / "root"
        esp_dir = tmp_path / "esp"
        root_dir.mkdir()
        esp_dir.mkdir()
        mocker.patch.object(
            installer_mod,
            "generate_grub_cfg",
            return_value=root_dir / "boot/grub/grub.cfg",
        )
        mocker.patch.object(
            installer_mod,
            "install_efi",
            side_effect=errors.BootloaderToolsMissingError("no modules"),
        )
        boot_method = installer.prepare_rootfs(
            root_dir=root_dir, esp_dir=esp_dir, root_uuid=uuid.uuid4()
        )
        assert boot_method == BootMethod.NONE

    def test_prepare_rootfs_skips_bios_staging_when_modules_missing(
        self, tmp_path, mocker
    ):
        volume = _mbr_volume([{**ROOT_ITEM, "type": "83"}])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        root_dir = tmp_path / "root"
        root_dir.mkdir()
        mocker.patch.object(
            installer_mod,
            "generate_grub_cfg",
            return_value=root_dir / "boot/grub/grub.cfg",
        )
        mocker.patch.object(
            installer_mod,
            "stage_non_efi_modules",
            side_effect=errors.BootloaderToolsMissingError("no modules"),
        )
        boot_method = installer.prepare_rootfs(
            root_dir=root_dir, esp_dir=None, root_uuid=uuid.uuid4()
        )
        assert boot_method == BootMethod.NONE

    def test_install_image_boot_code_skips_when_tools_missing(self, tmp_path, mocker):
        volume = _mbr_volume([{**ROOT_ITEM, "type": "83"}])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        mocker.patch.object(
            installer_mod,
            "install_non_efi",
            side_effect=errors.BootloaderToolsMissingError("no grub-bios-setup"),
        )
        installer.install_image_boot_code(
            image_path=tmp_path / "disk.img",
            root_dir=tmp_path,
            root_uuid=uuid.uuid4(),
        )

    def test_install_image_boot_code_noop_for_efi(self, tmp_path, mocker):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        mock_install = mocker.patch.object(installer_mod, "install_non_efi")
        installer.install_image_boot_code(
            image_path=tmp_path / "disk.img",
            root_dir=tmp_path,
            root_uuid=uuid.uuid4(),
        )
        mock_install.assert_not_called()
