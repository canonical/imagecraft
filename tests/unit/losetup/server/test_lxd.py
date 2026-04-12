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

"""Unit tests for imagecraft/losetup/server/_lxd.py."""

import pathlib

import pytest

from imagecraft.losetup.server._lxd import (
    convert_container_path_to_host_path,
    find_free_loop_slot,
)


# ─── find_free_loop_slot ──────────────────────────────────────────────────────


class TestFindFreeLoopSlot:
    @pytest.mark.parametrize(
        "devices, expected",
        [
            # Empty → slot 0
            ({}, 0),
            # Slot 0 taken (including a partition device) → slot 1
            (
                {
                    "imagecraft-loop0": {"type": "unix-block"},
                    "imagecraft-loop0p1": {"type": "unix-block"},
                },
                1,
            ),
            # Gap at slot 1 → slot 1
            (
                {
                    "imagecraft-loop0": {"type": "unix-block"},
                    "imagecraft-loop2": {"type": "unix-block"},
                },
                1,
            ),
            # Non-imagecraft devices are ignored
            ({"other-device": {"type": "disk"}}, 0),
            # Mixed: imagecraft slot 0, other devices → still slot 1
            (
                {
                    "imagecraft-loop0": {"type": "unix-block"},
                    "eth0": {"type": "nic"},
                },
                1,
            ),
            # Two consecutive slots taken → slot 2
            (
                {
                    "imagecraft-loop0": {},
                    "imagecraft-loop1": {},
                },
                2,
            ),
        ],
    )
    def test_find_free_slot(self, devices, expected):
        assert find_free_loop_slot(devices) == expected


# ─── convert_container_path_to_host_path ──────────────────────────────────────


class TestConvertContainerPathToHostPath:
    def _make_devices(self, *entries):
        """Build an expanded_devices dict from (name, path, source) tuples."""
        return {
            name: {"type": "disk", "path": path, "source": source}
            for name, path, source in entries
        }

    def _mock_lxd_get(self, mocker, devices: dict):
        mocker.patch(
            "imagecraft.losetup.server._lxd.lxd_get",
            return_value={"metadata": {"expanded_devices": devices}},
        )

    def test_simple_prefix_match(self, mocker):
        devices = self._make_devices(
            ("disk-root", "/root/project", "/home/user/project")
        )
        self._mock_lxd_get(mocker, devices)

        result = convert_container_path_to_host_path(
            "myproject", "mycontainer", "/root/project/disk.img"
        )

        assert result == pathlib.Path("/home/user/project/disk.img")

    def test_exact_path_match(self, mocker):
        devices = self._make_devices(
            ("disk-root", "/root/project", "/home/user/project")
        )
        self._mock_lxd_get(mocker, devices)

        result = convert_container_path_to_host_path(
            "myproject", "mycontainer", "/root/project"
        )

        assert result == pathlib.Path("/home/user/project")

    def test_longest_prefix_wins(self, mocker):
        """When two mounts overlap, the longer (more specific) one is chosen."""
        devices = {
            "disk-root": {"type": "disk", "path": "/root", "source": "/host/root"},
            "disk-project": {
                "type": "disk",
                "path": "/root/project",
                "source": "/home/user/project",
            },
        }
        self._mock_lxd_get(mocker, devices)

        result = convert_container_path_to_host_path(
            "myproject", "mycontainer", "/root/project/foo"
        )

        assert result == pathlib.Path("/home/user/project/foo")

    def test_raises_when_no_matching_device(self, mocker):
        devices = self._make_devices(
            ("disk-other", "/other/path", "/host/other")
        )
        self._mock_lxd_get(mocker, devices)

        with pytest.raises(ValueError, match="not under any sourced device"):
            convert_container_path_to_host_path(
                "myproject", "mycontainer", "/root/project/disk.img"
            )

    def test_non_disk_device_is_ignored(self, mocker):
        devices = {
            "eth0": {"type": "nic", "path": "/root/project", "source": "/host/proj"},
            "disk-root": {"type": "disk", "path": "/root", "source": "/host/root"},
        }
        self._mock_lxd_get(mocker, devices)

        result = convert_container_path_to_host_path(
            "myproject", "mycontainer", "/root/project/file"
        )

        # Uses /root mount, not the nic device
        assert result == pathlib.Path("/host/root/project/file")

    def test_disk_without_source_is_ignored(self, mocker):
        devices = {
            "disk-nosource": {"type": "disk", "path": "/root/project"},
            "disk-root": {"type": "disk", "path": "/root", "source": "/host/root"},
        }
        self._mock_lxd_get(mocker, devices)

        result = convert_container_path_to_host_path(
            "myproject", "mycontainer", "/root/project/file"
        )

        # disk-nosource has no "source" so it's ignored; falls back to /root
        assert result == pathlib.Path("/host/root/project/file")

    def test_lxd_get_called_with_correct_path(self, mocker):
        mock_get = mocker.patch(
            "imagecraft.losetup.server._lxd.lxd_get",
            return_value={
                "metadata": {
                    "expanded_devices": {
                        "d": {"type": "disk", "path": "/", "source": "/host"}
                    }
                }
            },
        )

        convert_container_path_to_host_path("proj", "cont", "/file")

        mock_get.assert_called_once_with("/1.0/instances/cont?project=proj")

    def test_normpath_applied_to_container_path(self, mocker):
        """Trailing slashes and dots are normalised before matching."""
        devices = self._make_devices(
            ("disk-root", "/root/project", "/host/project")
        )
        self._mock_lxd_get(mocker, devices)

        result = convert_container_path_to_host_path(
            "p", "c", "/root/project/"
        )

        assert result == pathlib.Path("/host/project")
