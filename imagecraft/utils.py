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


# Note: not a great idea, but quick to avoid having to call distro-info
# multiple times
version_to_series_map = {}


def host_deb_arch():
    """Get the Debian architecture of the host system."""
    # Use dpkg --print-architecture to get the host architecture
    # See https://manpages.debian.org/testing/dpkg/dpkg-architecture.1.en.html
    # for more information.
    return subprocess.check_output(
        ["dpkg", "--print-architecture"], universal_newlines=True
    ).strip()


def craft_base_to_ubuntu_series(base):
    global version_to_series_map

    if not base.startswith("ubuntu-"):
        return None

    if not version_to_series_map:
        # I wonder if there's an easier way than this
        # Execute the distro-info command to get the list of Ubuntu releases
        try:
            ubuntu_codenames = subprocess.check_output(
                ["distro-info", "--all", "-c"], universal_newlines=True
            ).strip().splitlines()
            ubuntu_versions = subprocess.check_output(
                ["distro-info", "--all", "-r"], universal_newlines=True
            ).strip().splitlines()
        except subprocess.CalledProcessError:
            return None
        # Go through the version list and remove the LTS suffix if present
        ubuntu_versions = [v.removesuffix(" LTS") for v in ubuntu_versions]
        # Create a map of version to codename
        version_to_series_map = dict(zip(ubuntu_versions, ubuntu_codenames))

    base_version = base.split("-")[1]
    return version_to_series_map.get(base_version, None)

