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
from craft_cli import emit

from imagecraft.utils import craft_base_to_ubuntu_series


class UbuntuImageError(Exception):
    """Raised when an error occurs while using ubuntu-image."""
    pass


def generate_partial_def_rootfs(series, arch, sources, seed_branch,
                                seeds, components_list, pocket,
                                kernel=None, extra_snaps=None):
    """Generate a partial definition yaml file for rootfs creation."""
    components = ", ".join(components_list)
    seed_urls = ", ".join(f'"{w}"' for w in sources)
    seed_names = ", ".join(f'"{w}"' for w in seeds)
    kernel_line = f"kernel: {kernel}" if kernel else ""
    customization = ""

    if extra_snaps:
        extra_snaps_list = "\n".join(
            f"    - name: {snap}" for snap in extra_snaps)
        customization = f"""
customization:
  extra-snaps:
{extra_snaps_list}
"""

    definition_yaml = f"""
architecture: {arch}
series: {series}
class: preinstalled
{kernel_line}

rootfs:
  components: [{components}]
  seed:
    urls: [{seed_urls}]
    branch: {seed_branch}
    names: [{seed_names}]
    pocket: {pocket}

{customization}
"""
    return definition_yaml


def generate_legacy_def_rootfs(series, arch, sources, seed_branch,
                               seeds, components_list, pocket,
                               kernel=None, extra_snaps=None):
    """Generate a definition yaml file for rootfs creation before ubuntu-image
       control support."""
    rootfs = generate_partial_def_rootfs(
        series, arch, sources, seed_branch, seeds, components_list, pocket,
        kernel, extra_snaps)
    definition_yaml = f"""
name: craft-driver
display-name: Craft Driver
revision: 1
class: preinstalled
{rootfs}

artifacts:
  manifest:
    name: craft.manifest
"""
    return definition_yaml


def generate_ubuntu_image_calls_rootfs(series, arch, sources, seed_branch,
                                       seeds, components_list, pocket,
                                       kernel=None, extra_snaps=None):
    """Call ubuntu-image to generate a rootfs."""
    definition_yaml = generate_legacy_def_rootfs(
        series, arch, sources, seed_branch, seeds, components_list, pocket,
        kernel, extra_snaps)
    cmds = [
        f"cat << EOF > craft.yaml\n{definition_yaml}\nEOF",
        "ubuntu-image classic --workdir work -O output/ --thru" \
        "=preseed_image craft.yaml",
        "mv work/chroot/* $CRAFT_PART_INSTALL/",
        #  "ubuntu-image control build-rootfs craft.yaml",
    ]
    return cmds


def ubuntu_image_pack(rootfs_path, gadget_path, output_path, image_type=None):
    """Pack the primed image contents into an image file."""
    cmd = ["./ubuntu-image", "pack", "--gadget-dir", gadget_path, "--rootfs-dir", rootfs_path, "-O", output_path]

    if image_type:
        cmd.extend(["--artifact-type", image_type])
    
    emit.debug(f"Pack command: {cmd}")
    try:
        subprocess.check_call(cmd, universal_newlines=True)
    except subprocess.CalledProcessError as err:
        msg = f"Cannot pack snap file: {err!s}"
        if err.stderr:
            msg += f" ({err.stderr.strip()!s})"
        raise UbuntuImageError(msg)