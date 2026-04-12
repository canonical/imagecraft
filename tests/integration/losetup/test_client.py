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

"""Integration tests for imagecraft/losetup/__init__.py.

These tests call the real losetup binary and therefore require root.
"""

import pathlib

import pytest

from imagecraft.losetup import _losetup_attach, _losetup_detach


@pytest.mark.requires_root
class TestLosetupAttachDetachIntegration:
    def test_attach_returns_loop_device(self, tmp_path):
        img = tmp_path / "disk.img"
        # Create a 10 MiB sparse file
        img.write_bytes(b"\0" * (10 * 1024 * 1024))

        devices = _losetup_attach(img)

        try:
            assert len(devices) >= 1
            loop_dev = devices[0]
            assert loop_dev.startswith("/dev/loop")
            assert pathlib.Path(loop_dev).exists()
        finally:
            import subprocess

            subprocess.run(["losetup", "--detach", devices[0]], check=False)

    def test_detach_removes_device(self, tmp_path):
        img = tmp_path / "disk.img"
        img.write_bytes(b"\0" * (10 * 1024 * 1024))

        import subprocess

        loop_dev = (
            subprocess.run(
                ["losetup", "--find", "--show", str(img)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )

        try:
            removed = _losetup_detach(loop_dev)
            assert loop_dev in removed
            assert not pathlib.Path(loop_dev).exists()
        except Exception:
            subprocess.run(["losetup", "--detach", loop_dev], check=False)
            raise

    def test_attach_and_detach_roundtrip(self, tmp_path):
        img = tmp_path / "disk.img"
        img.write_bytes(b"\0" * (10 * 1024 * 1024))

        devices = _losetup_attach(img)
        loop_dev = devices[0]
        assert pathlib.Path(loop_dev).exists()

        removed = _losetup_detach(loop_dev)
        assert loop_dev in removed
        assert not pathlib.Path(loop_dev).exists()
