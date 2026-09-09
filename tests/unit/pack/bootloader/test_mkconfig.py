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
"""Unit tests for grub.cfg post-processing and the grub-probe shim."""

import subprocess
import uuid

import pytest
from imagecraft import errors
from imagecraft.pack.bootloader.mkconfig import (
    _GRUB_PROBE_SHIM,
    _fs_internal_path,
    _strip_boot_prefix,
    generate_grub_cfg,
)


class TestStripBootPrefix:
    def test_strips_boot_prefix(self, tmp_path):
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir()
        cfg = tmp_path / "grub.cfg"
        cfg.write_text(
            "menuentry 'GNU/Linux' {\n"
            "\tlinux\t/boot/vmlinuz-6.8.0 root=UUID=abc ro\n"
            "\tinitrd\t/boot/initrd.img-6.8.0\n"
            "}\n"
        )
        _strip_boot_prefix(cfg, boot_dir)
        content = cfg.read_text()
        assert "\tlinux\t/vmlinuz-6.8.0 " in content
        assert "\tinitrd\t/boot/initrd.img-6.8.0".replace("/boot/", "/") in content
        assert "/boot/vmlinuz" not in content

    def test_strips_fs_internal_prefix(self, tmp_path):
        """grub-mkrelpath may emit the boot prime dir's host-fs-internal path."""
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir()
        internal = _fs_internal_path(boot_dir).rstrip("/")
        cfg = tmp_path / "grub.cfg"
        cfg.write_text(f"\tlinux\t{internal}/vmlinuz-6.8.0 root=UUID=abc ro\n")
        _strip_boot_prefix(cfg, boot_dir)
        assert cfg.read_text() == "\tlinux\t/vmlinuz-6.8.0 root=UUID=abc ro\n"

    def test_idempotent(self, tmp_path):
        boot_dir = tmp_path / "boot"
        boot_dir.mkdir()
        cfg = tmp_path / "grub.cfg"
        cfg.write_text("\tlinux\t/vmlinuz-6.8.0 root=UUID=abc ro\n")
        _strip_boot_prefix(cfg, boot_dir)
        assert cfg.read_text() == "\tlinux\t/vmlinuz-6.8.0 root=UUID=abc ro\n"


class TestFsInternalPath:
    def test_returns_absolute_path(self, tmp_path):
        result = _fs_internal_path(tmp_path)
        assert result.startswith("/")

    def test_subdir_of_mount(self, tmp_path):
        # / is always a mount, so the result is the path relative to its fs.
        result = _fs_internal_path(tmp_path / "subdir")
        assert result.startswith("/")


class TestProbeShim:
    def test_shim_substitution(self):
        root_uuid = uuid.uuid4()
        boot_uuid = uuid.uuid4()
        content = _GRUB_PROBE_SHIM % {
            "shim_log": "/tmp/shim.log",
            "root_device": "/image",
            "boot_device": "/image-boot",
            "root_uuid": str(root_uuid),
            "boot_uuid": str(boot_uuid),
            "partmap": "gpt",
        }
        assert str(root_uuid) in content
        assert str(boot_uuid) in content
        assert "%(" not in content

    def test_shim_answers(self, tmp_path):
        """The generated shim produces the expected answers when executed."""
        root_uuid = uuid.uuid4()
        boot_uuid = uuid.uuid4()
        shim = tmp_path / "grub-probe"
        shim.write_text(
            _GRUB_PROBE_SHIM
            % {
                "shim_log": str(tmp_path / "shim.log"),
                "root_device": "/image",
                "boot_device": "/image-boot",
                "root_uuid": str(root_uuid),
                "boot_uuid": str(boot_uuid),
                "partmap": "msdos",
            }
        )
        shim.chmod(0o755)

        def probe(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                [str(shim), *args], capture_output=True, text=True, check=False
            )

        # Device resolution distinguishes / from /boot.
        assert probe("--target=device", "/").stdout.strip() == "/image"
        assert probe("--target=device", "/boot").stdout.strip() == "/image-boot"
        # fs_uuid is keyed by device.
        assert probe("--device", "/image", "--target=fs_uuid").stdout.strip() == str(
            root_uuid
        )
        assert probe(
            "--device", "/image-boot", "--target=fs_uuid"
        ).stdout.strip() == str(boot_uuid)
        assert probe("-t", "fs", "/boot/vmlinuz").stdout.strip() == "ext2"
        assert probe("--device", "/image", "--target=partmap").stdout.strip() == "msdos"
        # Empty answers succeed (callers rely on this under set -e).
        empty = probe("--device", "/image", "--target=abstraction")
        assert empty.returncode == 0
        assert empty.stdout == ""


class TestGenerateGrubCfg:
    def test_missing_mkconfig_raises_tools_missing(self, tmp_path):
        with pytest.raises(errors.BootloaderToolsMissingError):
            generate_grub_cfg(tmp_path, uuid.uuid4())
