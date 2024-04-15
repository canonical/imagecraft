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

import pytest
from imagecraft.errors import UbuntuImageError
from imagecraft.ubuntu_image import (
    generate_image_def_yaml,
    ubuntu_image_cmds_build_rootfs,
    ubuntu_image_pack,
)


def test_generate_image_def_yaml():
    assert (
        generate_image_def_yaml(
            series="mantic",
            revision="22.04",
            arch="amd64",
            sources=["source1", "source2"],
            seed_branch="mantic",
            seeds=["server", "minimal"],
            components_list=["main", "restricted"],
            pocket="updates",
            kernel="linux-image-generic",
            extra_snaps=["lxd", "snapd"],
            extra_packages=["apt", "dpkg"],
        )
        == """name: craft-driver
display-name: Craft Driver
revision: '22.04'
class: preinstalled
architecture: amd64
series: mantic
kernel: linux-image-generic
rootfs:
  components:
  - main
  - restricted
  seed:
    urls:
    - source1
    - source2
    branch: mantic
    names:
    - server
    - minimal
    pocket: updates
customization:
  extra-snaps:
  - name: lxd
  - name: snapd
  extra-packages:
  - name: apt
  - name: dpkg
"""
    )

    assert (
        generate_image_def_yaml(
            series="mantic",
            revision="22.04",
            arch="amd64",
            sources=["source1", "source2"],
            seed_branch="mantic",
            seeds=["server", "minimal"],
            components_list=["main", "restricted"],
            pocket="updates",
            kernel="linux-image-generic",
            extra_packages=["apt", "dpkg"],
        )
        == """name: craft-driver
display-name: Craft Driver
revision: '22.04'
class: preinstalled
architecture: amd64
series: mantic
kernel: linux-image-generic
rootfs:
  components:
  - main
  - restricted
  seed:
    urls:
    - source1
    - source2
    branch: mantic
    names:
    - server
    - minimal
    pocket: updates
customization:
  extra-packages:
  - name: apt
  - name: dpkg
"""
    )

    assert (
        generate_image_def_yaml(
            series="mantic",
            revision="22.04",
            arch="amd64",
            sources=[],
            seed_branch="mantic",
            seeds=[],
            components_list=[],
            pocket="updates",
            extra_snaps=[],
        )
        == """name: craft-driver
display-name: Craft Driver
revision: '22.04'
class: preinstalled
architecture: amd64
series: mantic
rootfs:
  components: []
  seed:
    urls: []
    branch: mantic
    names: []
    pocket: updates
"""
    )


def test_ubuntu_image_cmds_build_rootfs(mocker):
    mocker.patch(
        "imagecraft.ubuntu_image.generate_image_def_yaml",
        return_value="test",
    )

    assert ubuntu_image_cmds_build_rootfs(
        series="mantic",
        version="22.04",
        arch="amd64",
        sources=["source1", "source2"],
        seed_branch="mantic",
        seeds=["server", "minimal"],
        components_list=["main", "restricted"],
        pocket="updates",
        kernel="linux-image-generic",
        extra_snaps=["lxd", "snapd"],
    ) == [
        "cat << EOF > craft.yaml\ntest\nEOF",
        "ubuntu-image classic --workdir work -O output/ craft.yaml",
        "mv work/chroot/* $CRAFT_PART_INSTALL/",
    ]


def test_ubuntu_image_pack(mocker):
    subprocess_patcher = mocker.patch("imagecraft.ubuntu_image.subprocess.check_call")

    ubuntu_image_pack(
        rootfs_path="rootfs/path/test",
        gadget_path="gadget/test",
        output_path="output/path/test",
        image_type="",
    )

    subprocess_patcher.assert_called_with(
        [
            "ubuntu-image",
            "pack",
            "--gadget-dir",
            "gadget/test",
            "--rootfs-dir",
            "rootfs/path/test",
            "-O",
            "output/path/test",
        ],
        universal_newlines=True,
    )

    ubuntu_image_pack(
        rootfs_path="rootfs/path/test",
        gadget_path="gadget/test",
        output_path="output/path/test",
        image_type="raw",
    )

    subprocess_patcher.assert_called_with(
        [
            "ubuntu-image",
            "pack",
            "--gadget-dir",
            "gadget/test",
            "--rootfs-dir",
            "rootfs/path/test",
            "-O",
            "output/path/test",
            "--artifact-type",
            "raw",
        ],
        universal_newlines=True,
    )

    subprocess_patcher.side_effect = subprocess.CalledProcessError(
        returncode=1,
        cmd="some command",
        stderr="some details",
    )

    with pytest.raises(UbuntuImageError) as raised:
        ubuntu_image_pack(
            rootfs_path="rootfs/path/test",
            gadget_path="gadget/test",
            output_path="output/path/test",
            image_type="raw",
        )

    assert (
        str(raised.value)
        == "Cannot make (pack) image: Command 'some command' returned non-zero exit status 1."
    )
