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
from pathlib import Path

import pytest
from imagecraft import errors
from imagecraft.pack.bootloader.mkconfig import (
    _generate_grub_cfg_in_chroot,
    _GRUB_PROBE_SHIM,
    _fs_internal_path,
    _strip_boot_prefix,
    generate_grub_cfg,
)


class TestStripBootPrefix:
    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            pytest.param(
                "linux /boot/vmlinuz key=/boot/key /boot/argument",
                "linux /vmlinuz key=/boot/key /boot/argument",
                id="linux-kernel-positional-only",
            ),
            pytest.param(
                'linux "/boot/kernel name" key="/boot/key name"',
                'linux "/kernel name" key="/boot/key name"',
                id="linux-kernel-quoted",
            ),
            pytest.param(
                "multiboot --quirk-bad-kludge /boot/kernel config=/boot/config",
                "multiboot --quirk-bad-kludge /kernel config=/boot/config",
                id="multiboot-positional-only",
            ),
            pytest.param(
                "module /boot/module /boot/argument",
                "module /module /boot/argument",
                id="module-positional-only",
            ),
            pytest.param(
                "module2 /boot/module /boot/argument",
                "module2 /module /boot/argument",
                id="module2-positional-only",
            ),
            pytest.param(
                "multiboot2 /boot/kernel /boot/arg",
                "multiboot2 /kernel /boot/arg",
                id="multiboot2-positional-only",
            ),
            pytest.param(
                "devicetree /boot/board.dtb",
                "devicetree /board.dtb",
                id="devicetree-positional-only",
            ),
            pytest.param(
                "initrd /boot/microcode.img '/boot/initrd name'",
                "initrd /microcode.img '/initrd name'",
                id="initrd-multiple-files",
            ),
            pytest.param(
                'loadfont ($root)/boot/font.pf2 "($root)/boot/font two.pf2"',
                'loadfont ($root)/font.pf2 "($root)/font two.pf2"',
                id="loadfont-root-prefixed",
            ),
            pytest.param(
                "initrd /boot/initrd # /boot/comment",
                "initrd /initrd # /boot/comment",
                id="comments-unchanged",
            ),
            pytest.param(
                "initrd /boot/initrd; echo /boot/keep",
                "initrd /initrd; echo /boot/keep",
                id="shell-tail-unchanged",
            ),
            pytest.param(
                "linux /vmlinuz key=/boot/key",
                "linux /vmlinuz key=/boot/key",
                id="keyword-argument-unchanged",
            ),
            pytest.param(
                "echo /boot/keep",
                "echo /boot/keep",
                id="non-kernel-command-unchanged",
            ),
            pytest.param(
                "# linux /boot/keep",
                "# linux /boot/keep",
                id="comment-line-unchanged",
            ),
        ],
    )
    def test_rewrites_only_file_operands(self, tmp_path, mocker, line, expected):
        mocker.patch(
            "imagecraft.pack.bootloader.mkconfig._fs_internal_path",
            return_value="/",
        )
        cfg = tmp_path / "grub.cfg"
        cfg.write_text(f"\t{line}\n")

        _strip_boot_prefix(cfg, tmp_path)

        assert cfg.read_text() == f"\t{expected}\n"

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
        assert "\tinitrd\t/initrd.img-6.8.0" in content
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
    @pytest.mark.parametrize(
        ("path", "mountinfo", "expected"),
        [
            ("/work/boot", "1 0 8:1 / / rw - ext4 /dev/sda1 rw\n", "/work/boot"),
            ("/", "1 0 8:1 / / rw - ext4 /dev/sda1 rw\n", "/"),
            (
                "/work/boot",
                (
                    "1 0 8:1 / / rw - ext4 /dev/sda1 rw\n"
                    "2 1 8:2 / /work rw - ext4 /dev/sda2 rw\n"
                ),
                "/boot",
            ),
            (
                "/workspace/boot",
                (
                    "1 0 8:1 / / rw - ext4 /dev/sda1 rw\n"
                    "2 1 8:2 / /work rw - ext4 /dev/sda2 rw\n"
                ),
                "/workspace/boot",
            ),
        ],
    )
    def test_mountpoint_matching(self, mocker, path, mountinfo, expected):
        mocker.patch.object(Path, "read_text", return_value=mountinfo)
        assert _fs_internal_path(Path(path)) == expected

    def test_returns_absolute_path(self, tmp_path):
        result = _fs_internal_path(tmp_path)
        assert result.startswith("/")

    def test_subdir_of_mount(self, tmp_path):
        # / is always a mount, so the result is the path relative to its fs.
        result = _fs_internal_path(tmp_path / "subdir")
        assert result.startswith("/")


class TestProbeShim:
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

    def test_preserves_existing_placeholders_and_directories(self, tmp_path, mocker):
        root = tmp_path / "chroot"
        fake_device = root / "image"
        fake_boot_device = root / "image-boot"
        fake_device.parent.mkdir(parents=True, exist_ok=True)
        fake_device.write_text("keep root")
        fake_boot_device.write_text("keep boot")
        by_uuid_dir = root / "dev/disk/by-uuid"
        by_uuid_dir.mkdir(parents=True)
        mocker.patch(
            "imagecraft.pack.bootloader.mkconfig._GRUB_DEFAULTS_SNIPPET",
            root / "etc/default/grub.d/60-imagecraft.cfg",
        )
        mocker.patch("imagecraft.pack.bootloader.mkconfig._CHROOT_FAKE_DEVICE", fake_device)
        mocker.patch(
            "imagecraft.pack.bootloader.mkconfig._CHROOT_FAKE_BOOT_DEVICE",
            fake_boot_device,
        )
        real_path = Path

        def fake_path(value):
            if value.startswith("/"):
                return root / value.lstrip("/")
            return real_path(value)

        mocker.patch("imagecraft.pack.bootloader.mkconfig.Path", side_effect=fake_path)
        mocker.patch(
            "imagecraft.pack.bootloader.mkconfig.run_checked",
            return_value=subprocess.CompletedProcess(
                ["grub-mkconfig"], 0, stdout="", stderr=""
            ),
        )

        _generate_grub_cfg_in_chroot(
            grub_defaults="GRUB_DISABLE_OS_PROBER=true\n",
            root_uuid=str(uuid.uuid4()),
            boot_uuid=str(uuid.uuid4()),
        )

        assert fake_device.read_text() == "keep root"
        assert fake_boot_device.read_text() == "keep boot"
        assert by_uuid_dir.is_dir()
