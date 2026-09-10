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

import re
import uuid
from pathlib import Path

import pytest
from craft_platforms import DebianArchitecture
from imagecraft import errors
from imagecraft.models.volume import (
    FileSystem,
    GptType,
    GPTVolume,
    HybridVolume,
    MBRVolume,
)
from imagecraft.pack.bootloader import installer as installer_mod
from imagecraft.pack.bootloader.const import BootMethod
from imagecraft.pack.bootloader.installer import BootloaderInstaller, configure_fstab

_AMD64 = DebianArchitecture.AMD64

ESP_GUID = GptType.EFI_SYSTEM.value
LINUX_DATA_GUID = GptType.LINUX_DATA.value
BIOS_BOOT_GUID = GptType.BIOS_BOOT.value


def _gpt_volume(structure: list[dict]) -> GPTVolume:
    return GPTVolume.model_validate({"schema": "gpt", "structure": structure})


def _mbr_volume(structure: list[dict]) -> MBRVolume:
    return MBRVolume.model_validate({"schema": "mbr", "structure": structure})


def _hybrid_volume(structure: list[dict]) -> HybridVolume:
    return HybridVolume.model_validate({"schema": "mbr,gpt", "structure": structure})


def _hybrid_esp_root_volume() -> HybridVolume:
    return _hybrid_volume(
        [
            {**ESP_ITEM, "type": f"0C,{ESP_GUID}"},
            {**ROOT_ITEM, "type": f"83,{LINUX_DATA_GUID}"},
        ]
    )


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
        root = volume.root_partition
        esp = volume.esp_partition
        assert root is not None
        assert esp is not None
        assert root.name == "rootfs"
        assert esp.name == "efi"

    def test_no_esp_for_mbr(self):
        volume = _mbr_volume(
            [
                {**ROOT_ITEM, "type": "83"},
            ]
        )
        assert volume.esp_partition is None
        root = volume.root_partition
        assert root is not None
        assert root.name == "rootfs"

    def test_hybrid_esp_detected(self):
        """Hybrid items encode the GPT type as '<mbr>,<gpt>'; must still match."""
        esp = _hybrid_esp_root_volume().esp_partition
        assert esp is not None
        assert esp.name == "efi"

    def test_hybrid_lowercase_guid(self):
        volume = _hybrid_volume(
            [
                {**ESP_ITEM, "type": f"0c,{ESP_GUID.lower()}"},
                {**ROOT_ITEM, "type": f"83,{LINUX_DATA_GUID.lower()}"},
            ]
        )
        assert volume.esp_partition is not None

    def test_boot_item_is_none_when_only_esp(self):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        assert volume.boot_partition is None

    def test_boot_item_found_when_distinct_from_esp(self):
        volume = _gpt_volume([ESP_ITEM, BOOT_ITEM, ROOT_ITEM])
        boot = volume.boot_partition
        assert boot is not None
        assert boot.name == "boot"

    def test_boot_item_found_for_mbr(self):
        volume = _mbr_volume(
            [
                {**BOOT_ITEM, "type": "83"},
                {**ROOT_ITEM, "type": "83"},
            ]
        )
        boot = volume.boot_partition
        assert boot is not None
        assert boot.name == "boot"

    def test_bios_boot_partition_is_not_a_boot_partition(self):
        """A raw BIOS Boot partition (core.img embedding area) is not /boot."""
        volume = _gpt_volume([BIOS_BOOT_ITEM, ROOT_ITEM])
        assert volume.boot_partition is None


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
        installer = BootloaderInstaller(volume=_hybrid_esp_root_volume(), arch=_AMD64)
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


class TestFilesystemIds:
    def test_ext_partitions_get_uuids(self):
        volume = _gpt_volume([ESP_ITEM, BOOT_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        assert isinstance(installer.root_uuid, uuid.UUID)
        assert isinstance(installer.boot_uuid, uuid.UUID)

    def test_fat_boot_partition_gets_volume_id(self):
        """FAT /boot partitions get an XXXX-XXXX volume ID that mkfs.fat -i applies."""
        volume = _mbr_volume(
            [
                {**BOOT_ITEM, "type": "0C", "filesystem": "vfat"},
                {**ROOT_ITEM, "type": "83"},
            ]
        )
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        assert re.fullmatch(r"[0-9A-F]{4}-[0-9A-F]{4}", str(installer.boot_uuid))
        assert installer.partition_uuids["boot"] == str(installer.boot_uuid)


class FakeProjectDirs:
    """Minimal ProjectDirs stand-in mapping partition names to directories."""

    def __init__(self, base: Path) -> None:
        self._base = base

    def get_prime_dir(self, partition: str | None = None) -> Path:
        return self._base / (partition or "default")


def _prepare(installer: BootloaderInstaller, tmp_path: Path) -> BootMethod:
    return installer.prepare_rootfs(
        project_dirs=FakeProjectDirs(tmp_path),
        volume_name="pc",
        filesystems={"default": [{"mount": "/", "device": "(volume/pc/rootfs)"}]},
    )


class TestGracefulSkip:
    """Missing GRUB tooling in the rootfs must not crash pack."""

    def test_prepare_rootfs_skips_when_mkconfig_missing(self, tmp_path, mocker):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        mocker.patch.object(
            installer_mod,
            "generate_grub_cfg",
            side_effect=errors.BootloaderToolsMissingError("no grub-mkconfig"),
        )
        boot_method = _prepare(installer, tmp_path)
        assert boot_method == BootMethod.NONE
        # fstab is still written even when GRUB tooling is missing.
        assert (tmp_path / "volume" / "pc" / "rootfs" / "etc" / "fstab").is_file()

    def test_prepare_rootfs_skips_efi_when_modules_missing(self, tmp_path, mocker):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        mocker.patch.object(installer_mod, "generate_grub_cfg")
        mock_efi = mocker.patch.object(installer_mod, "EfiInstaller")
        mock_efi.return_value.install.side_effect = errors.BootloaderToolsMissingError(
            "no modules"
        )
        boot_method = _prepare(installer, tmp_path)
        assert boot_method == BootMethod.NONE

    def test_prepare_rootfs_skips_bios_staging_when_modules_missing(
        self, tmp_path, mocker
    ):
        volume = _mbr_volume([{**ROOT_ITEM, "type": "83"}])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        mocker.patch.object(installer_mod, "generate_grub_cfg")
        mocker.patch.object(
            installer_mod,
            "stage_grub_modules",
            side_effect=errors.BootloaderToolsMissingError("no modules"),
        )
        boot_method = _prepare(installer, tmp_path)
        assert boot_method == BootMethod.NONE

    def test_install_image_boot_code_skips_when_tools_missing(self, tmp_path, mocker):
        volume = _mbr_volume([{**ROOT_ITEM, "type": "83"}])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        mocker.patch.object(installer_mod, "generate_grub_cfg")
        mocker.patch.object(installer_mod, "stage_grub_modules")
        mock_bios = mocker.patch.object(installer_mod, "PCBiosInstaller")
        mock_bios.return_value.install.side_effect = errors.BootloaderToolsMissingError(
            "no grub-bios-setup"
        )
        _prepare(installer, tmp_path)
        installer.install_image_boot_code(image_path=tmp_path / "disk.img")

    def test_install_image_boot_code_noop_for_efi(self, tmp_path, mocker):
        volume = _gpt_volume([ESP_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        mock_install = mocker.patch.object(installer_mod, "PCBiosInstaller")
        installer.install_image_boot_code(image_path=tmp_path / "disk.img")
        mock_install.assert_not_called()


class TestBootFstab:
    @pytest.mark.parametrize("filesystem", ["ext3", "ext4", "fat16", "vfat"])
    @pytest.mark.parametrize("mountpoint", ["/boot", "/boot/"])
    def test_prepare_adds_mapped_boot_entry(
        self, tmp_path, mocker, filesystem, mountpoint
    ):
        volume = _gpt_volume(
            [ESP_ITEM, {**BOOT_ITEM, "filesystem": filesystem}, ROOT_ITEM]
        )
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        mocker.patch.object(installer_mod, "generate_grub_cfg")
        mocker.patch.object(installer_mod, "EfiInstaller")
        filesystems = {
            "default": [
                {"mount": "/", "device": "(volume/pc/rootfs)"},
                {"mount": mountpoint, "device": "(volume/pc/boot)"},
                {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
            ]
        }

        installer.prepare_rootfs(
            project_dirs=FakeProjectDirs(tmp_path),
            volume_name="pc",
            filesystems=filesystems,
        )

        fstab = tmp_path / "volume/pc/rootfs/etc/fstab"
        content = fstab.read_text()
        fs_type = "vfat" if filesystem == "fat16" else filesystem
        assert (
            f"UUID={installer.partition_uuids['boot']} /boot {fs_type} defaults 0 2\n"
            in content
        )
        assert f"UUID={installer.root_uuid} / ext4" in content
        assert "/boot/efi" not in content

    @pytest.mark.parametrize(
        ("mountpoint", "device"),
        [
            ("/srv", "(volume/pc/boot)"),
            ("/boot", "(volume/pc/rootfs)"),
            ("/boot/efi", "(volume/pc/boot)"),
        ],
    )
    def test_does_not_invent_boot_mapping(self, tmp_path, mocker, mountpoint, device):
        volume = _gpt_volume([ESP_ITEM, BOOT_ITEM, ROOT_ITEM])
        installer = BootloaderInstaller(volume=volume, arch=_AMD64)
        mocker.patch.object(installer_mod, "generate_grub_cfg")
        mocker.patch.object(installer_mod, "EfiInstaller")

        installer.prepare_rootfs(
            project_dirs=FakeProjectDirs(tmp_path),
            volume_name="pc",
            filesystems={
                "default": [
                    {"mount": "/", "device": "(volume/pc/rootfs)"},
                    {"mount": mountpoint, "device": device},
                ]
            },
        )

        content = (tmp_path / "volume/pc/rootfs/etc/fstab").read_text()
        assert str(installer.boot_uuid) not in content


class TestConfigureFstab:
    @pytest.mark.parametrize("mountpoint", ["/boot", "/boot/"])
    def test_preserves_existing_boot_entry(self, tmp_path, mountpoint):
        fstab = tmp_path / "etc/fstab"
        fstab.parent.mkdir()
        root = "LABEL=writable / ext4 discard 0 1\n"
        tail = f"\t{mountpoint}\tvfat\tro,umask=0077\t0\t0 # boot\n"
        fstab.write_text(root + "  LABEL=BOOT" + tail)

        configure_fstab(
            tmp_path, "1234-ABCD", mountpoint="/boot", filesystem=FileSystem.VFAT
        )
        configure_fstab(
            tmp_path, "1234-ABCD", mountpoint="/boot", filesystem=FileSystem.VFAT
        )

        assert fstab.read_text() == root + "  UUID=1234-ABCD" + tail

    def test_appends_boot_without_final_newline(self, tmp_path):
        fstab = tmp_path / "etc/fstab"
        fstab.parent.mkdir()
        root = "LABEL=writable / ext4 defaults 0 1"
        fstab.write_text(root)
        boot_uuid = uuid.uuid4()

        configure_fstab(
            tmp_path, boot_uuid, mountpoint="/boot", filesystem=FileSystem.EXT3
        )

        assert fstab.read_text() == (
            root + f"\nUUID={boot_uuid} /boot ext3 defaults 0 2\n"
        )

    def test_creates_fstab(self, tmp_path):
        root_uuid = uuid.uuid4()
        configure_fstab(tmp_path, root_uuid)
        fstab_path = tmp_path / "etc" / "fstab"
        assert fstab_path.is_file()
        assert f"UUID={root_uuid} / ext4" in fstab_path.read_text()

    def test_noop_when_uuid_present(self, tmp_path):
        root_uuid = uuid.uuid4()
        configure_fstab(tmp_path, root_uuid)
        before = (tmp_path / "etc" / "fstab").read_text()
        configure_fstab(tmp_path, root_uuid)
        assert (tmp_path / "etc" / "fstab").read_text() == before

    def test_replaces_existing_root_entry(self, tmp_path):
        """A project-provided LABEL=writable / entry is replaced, not duplicated."""
        etc = tmp_path / "etc"
        etc.mkdir()
        (etc / "fstab").write_text(
            "LABEL=writable\t/\text4\tdiscard,errors=remount-ro\t0\t1\n"
            "LABEL=UEFI\t/boot/efi\tvfat\tumask=0077\t0 1\n"
        )
        root_uuid = uuid.uuid4()
        configure_fstab(tmp_path, root_uuid)
        content = (etc / "fstab").read_text()
        assert "LABEL=writable" not in content
        assert (
            f"UUID={root_uuid}\t/\text4\tdiscard,errors=remount-ro\t0\t1\n" in content
        )
        # The ESP entry is preserved.
        assert "LABEL=UEFI" in content
        # Exactly one root entry.
        assert (
            sum(
                1
                for line in content.splitlines()
                if line.split()[1:2] == ["/"] and not line.startswith("#")
            )
            == 1
        )

    def test_appends_when_no_root_entry(self, tmp_path):
        etc = tmp_path / "etc"
        etc.mkdir()
        (etc / "fstab").write_text("LABEL=UEFI /boot/efi vfat umask=0077 0 1")
        root_uuid = uuid.uuid4()
        configure_fstab(tmp_path, root_uuid)
        content = (etc / "fstab").read_text()
        assert "LABEL=UEFI" in content
        assert f"UUID={root_uuid} / ext4" in content

    def test_ignores_commented_root_entry(self, tmp_path):
        etc = tmp_path / "etc"
        etc.mkdir()
        (etc / "fstab").write_text("# LABEL=old / ext4 defaults 0 1\n")
        root_uuid = uuid.uuid4()
        configure_fstab(tmp_path, root_uuid)
        content = (etc / "fstab").read_text()
        assert "# LABEL=old / ext4 defaults 0 1" in content
        assert f"UUID={root_uuid} / ext4" in content

    @pytest.mark.parametrize(
        "suffix",
        [
            "\t/\text3\tro,discard,x-systemd.device-timeout=30\t1\t2\n",
            " / ext4 defaults 0 0 # keep this comment\n",
            " / ext4 ro 0 1",
        ],
    )
    def test_preserves_root_fields_and_formatting(self, tmp_path, suffix):
        fstab = tmp_path / "etc" / "fstab"
        fstab.parent.mkdir()
        fstab.write_text("  LABEL=writable" + suffix)
        root_uuid = uuid.uuid4()

        configure_fstab(tmp_path, root_uuid)

        assert fstab.read_text() == f"  UUID={root_uuid}" + suffix

    def test_uuid_elsewhere_does_not_skip_root_update(self, tmp_path):
        root_uuid = uuid.uuid4()
        fstab = tmp_path / "etc" / "fstab"
        fstab.parent.mkdir()
        comment = f"# root UUID will be {root_uuid}\n"
        fstab.write_text(comment + "LABEL=writable / ext4 ro 0 1\n")

        configure_fstab(tmp_path, root_uuid)

        assert fstab.read_text() == comment + f"UUID={root_uuid} / ext4 ro 0 1\n"
