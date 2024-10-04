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

import json
import pathlib
import subprocess

from craft_cli import emit
from pydantic import (
    AnyUrl,
    FileUrl,
)

from imagecraft.errors import UbuntuImageError
from imagecraft.image_definition import ImageDefinition


def ubuntu_image_cmds_build_rootfs(  # noqa: PLR0913
    series: str,
    arch: str,
    pocket: str,
    sources: list[str],
    seed_branch: str,
    seeds: list[str],
    components: list[str] | None,
    flavor: str | None,
    mirror: AnyUrl | FileUrl | None,
    seed_pocket: str,
    kernel: str | None = None,
    extra_snaps: list[str] | None = None,
    extra_packages: list[str] | None = None,
    custom_components: list[str] | None = None,
    custom_pocket: str | None = None,
    *,
    debug: bool = False,
) -> list[str]:
    """List commands to ubuntu-image to generate a rootfs."""
    image_def = ImageDefinition(
        series=series,
        revision=1,
        architecture=arch,
        pocket=pocket,
        kernel=kernel,
        components=components,
        flavor=flavor,
        mirror=mirror,
        seed_urls=sources,
        seed_branch=seed_branch,
        seed_names=seeds,
        seed_pocket=seed_pocket,
        extra_snaps=extra_snaps,
        extra_packages=extra_packages,
        custom_components=custom_components,
        custom_pocket=custom_pocket,
    )

    definition_yaml = image_def.dump_yaml()
    image_definition_file = "craft.yaml"
    debug_flag = ""
    if debug:
        debug_flag = "--debug "

    return [
        f"cat << EOF > {image_definition_file}\n{definition_yaml}\nEOF",
        f"ubuntu-image classic {debug_flag}--workdir work -O output/ {image_definition_file}",
        "mv work/root $CRAFT_PART_INSTALL/rootfs",
    ]


def ubuntu_image_pack(
    rootfs_path: str,
    gadget_path: str,
    output_path: str,
    workdir_path: str,
    image_type: str | None = None,
    *,
    debug: bool = False,
) -> None:
    """Pack the primed image contents into an image file."""
    cmd: list[str] = [
        "ubuntu-image",
        "pack",
        "--workdir",
        workdir_path,
        "--gadget-dir",
        gadget_path,
        "--rootfs-dir",
        rootfs_path,
        "-O",
        output_path,
    ]

    if image_type:
        cmd.extend(["--artifact-type", str(image_type)])
    if debug:
        cmd.extend(["--debug"])

    emit.debug(f"Pack command: {cmd}")
    try:
        subprocess.check_call(cmd, universal_newlines=True)
    except subprocess.CalledProcessError as err:
        message = f"Cannot pack image: {err!s}"
        details = f"Error output: {err.stderr.strip()!s}"
        resolution = "Please check the error output for resolution guidance."

        raise UbuntuImageError(
            message=message,
            details=details,
            resolution=resolution,
        ) from err


def list_image_paths(workdir_path: str) -> list[str]:
    """Extract the list of images from a ubuntu-image.json file."""
    p = pathlib.Path(workdir_path) / "ubuntu-image.json"
    f = p.open("r")
    ui_state = json.load(f)

    return list(ui_state["VolumeNames"].values())
