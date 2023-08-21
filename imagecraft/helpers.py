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


def host_deb_arch():
    """Get the Debian architecture of the host system."""
    # Use dpkg --print-architecture to get the host architecture
    # See https://manpages.debian.org/testing/dpkg/dpkg-architecture.1.en.html
    # for more information.
    return subprocess.check_output(
        ["dpkg", "--print-architecture"], universal_newlines=True
    ).strip()
