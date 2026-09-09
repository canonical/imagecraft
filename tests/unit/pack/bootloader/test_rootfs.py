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
"""Unit tests for rootfs fstab configuration."""

import uuid

from imagecraft.pack.bootloader.rootfs import configure_fstab


class TestConfigureFstab:
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
        assert f"UUID={root_uuid} / ext4" in content
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
