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

"""Ubuntu-image related helpers."""

import subprocess

from craft_cli import emit

from imagecraft.errors import UbuntuImageError


def generate_legacy_def_rootfs(  # noqa: PLR0913
    series: str,
    arch: str,
    sources: list[str],
    seed_branch: str,
    seeds: list[str],
    components_list: list[str],
    pocket: str,
    kernel: str | None = None,
    extra_snaps: list[str] | None = None,
) -> str:
    """Generate a definition yaml file for rootfs creation."""
    components = ", ".join(components_list)
    seed_urls = ", ".join(f'"{w}"' for w in sources)
    seed_names = ", ".join(f'"{w}"' for w in seeds)
    kernel_line = f"kernel: {kernel}" if kernel else ""
    customization = ""

    if extra_snaps:
        extra_snaps_list = "\n".join(f"    - name: {snap}" for snap in extra_snaps)
        customization = f"""
customization:
  extra-snaps:
{extra_snaps_list}
"""

    return f"""
name: craft-driver
display-name: Craft Driver
revision: 1
class: preinstalled
architecture: {arch}
series: {series}
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


def ubuntu_image_cmds_build_rootfs(  # noqa: PLR0913
    series: str,
    arch: str,
    sources: list[str],
    seed_branch: str,
    seeds: list[str],
    components_list: list[str],
    pocket: str,
    kernel: str | None = None,
    extra_snaps: list[str] | None = None,
) -> list[str]:
    """Call ubuntu-image to generate a rootfs."""
    definition_yaml = generate_legacy_def_rootfs(
        series,
        arch,
        sources,
        seed_branch,
        seeds,
        components_list,
        pocket,
        kernel,
        extra_snaps,
    )
    return [
        f"cat << EOF > craft.yaml\n{definition_yaml}\nEOF",
        "ubuntu-image classic --workdir work -O output/ craft.yaml",
        "mv work/chroot/* $CRAFT_PART_INSTALL/",
        #  "ubuntu-image control build-rootfs craft.yaml",
    ]


def ubuntu_image_pack(
    rootfs_path: str,
    gadget_path: str,
    output_path: str,
    image_type: str | None = None,
) -> None:
    """Pack the primed image contents into an image file."""
    cmd: list[str] = [
        "./ubuntu-image",
        "pack",
        "--gadget-dir",
        gadget_path,
        "--rootfs-dir",
        rootfs_path,
        "-O",
        output_path,
    ]

    if image_type:
        cmd.extend(["--artifact-type", str(image_type)])

    emit.debug(f"Pack command: {cmd}")
    try:
        subprocess.check_call(cmd, universal_newlines=True)
    except subprocess.CalledProcessError as err:
        message = f"Cannot make (pack) image: {err!s}"
        details = f"Error output: {err.stderr.strip()!s}"
        resolution = "Please check the error output for resolution guidance."

        raise UbuntuImageError(
            message=message,
            details=details,
            resolution=resolution,
        ) from err
