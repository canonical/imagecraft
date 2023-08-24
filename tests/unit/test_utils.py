# This file is part of imagecraft.
#
# Copyright 2023 Canonical Ltd.
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

import subprocess
import imagecraft.utils

from imagecraft.utils import craft_base_to_ubuntu_series


def test_craft_base_to_ubuntu_series():
    imagecraft.utils.version_to_series_map.clear()
    
    test_cases = {
        "ubuntu-20.04": "focal",
        "ubuntu-22.04": "jammy",
        "ubuntu-22.10": "kinetic",
        "ubuntu-18.04": "bionic",
        "debian-11": None,
        "18.04": None,
    }

    for base, expected_series in test_cases.items():
        assert craft_base_to_ubuntu_series(base) == expected_series


def test_craft_base_to_ubuntu_series_cached(mocker):
    mocker.patch("subprocess.check_output", side_effect=["focal", "20.04"])

    imagecraft.utils.version_to_series_map.clear()
    craft_base_to_ubuntu_series("ubuntu-20.04")
    craft_base_to_ubuntu_series("ubuntu-22.04")

    assert subprocess.check_output.call_count == 2


def test_craft_base_to_ubuntu_series_fail(mocker):
    mocker.patch("subprocess.check_output",
                 side_effect=subprocess.CalledProcessError(1, "error"))

    imagecraft.utils.version_to_series_map.clear()

    assert craft_base_to_ubuntu_series("ubuntu-20.04") == None
