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

from craft_application.util import dump_yaml
from craft_cli import emit
from pydantic import BaseModel, Field

from imagecraft.errors import UbuntuImageError


def _alias_generator(s: str) -> str:
    return s.replace("_", "-")


class Snap(BaseModel):
    """Pydantic model for the Snap object in an ImageDefinition."""

    name: str | None


class Package(BaseModel):
    """Pydantic model for the Package object in an ImageDefinition."""

    name: str | None


class Customization(BaseModel):
    """Pydantic model for the Customization object in an ImageDefinition."""

    extra_snaps: list[Snap] | None
    extra_packages: list[Package] | None

    class Config:
        """Pydantic model configuration."""

        validate_assignment = True
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = _alias_generator


class Seed(BaseModel):
    """Pydantic model for the Seed object in an ImageDefinition."""

    urls: list[str]
    branch: str
    names: list[str]
    pocket: str

    class Config:
        """Pydantic model configuration."""

        validate_assignment = True
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = _alias_generator


class Rootfs(BaseModel):
    """Pydantic model for the Rootfs object in an ImageDefinition."""

    components: list[str]
    seed: Seed

    class Config:
        """Pydantic model configuration."""

        validate_assignment = True
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = _alias_generator


class ImageDefinition(BaseModel):
    """Pydantic model for the ImageDefinition."""

    name: str
    display_name: str
    revision: str
    class_: str = Field(alias="class")
    architecture: str
    series: str
    kernel: str | None
    rootfs: Rootfs
    customization: Customization | None = None

    class Config:
        """Pydantic model configuration."""

        validate_assignment = True
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = _alias_generator


def generate_image_def_yaml(  # noqa: PLR0913
    series: str,
    revision: str,
    arch: str,
    sources: list[str],
    seed_branch: str,
    seeds: list[str],
    components_list: list[str],
    pocket: str,
    kernel: str | None = None,
    extra_snaps: list[str] | None = None,
    extra_packages: list[str] | None = None,
) -> str:
    """Generate a definition yaml file for rootfs creation."""
    image_definition = ImageDefinition(
        name="craft-driver",
        display_name="Craft Driver",
        class_="preinstalled",  # type: ignore[call-arg]
        revision=revision,
        architecture=arch,
        series=series,
        kernel=kernel,
        rootfs=Rootfs(
            components=components_list,
            seed=Seed(
                urls=sources,
                branch=seed_branch,
                names=seeds,
                pocket=pocket,
            ),
        ),
    )

    extra_snaps_obj = None
    extra_packages_obj = None

    if extra_snaps:
        extra_snaps_obj = [Snap(name=s) for s in extra_snaps]

    if extra_packages:
        extra_packages_obj = [Package(name=p) for p in extra_packages]

    if extra_snaps or extra_packages:
        image_definition.customization = Customization(
            extra_snaps=extra_snaps_obj,
            extra_packages=extra_packages_obj,
        )

    return dump_yaml(
        image_definition.dict(
            exclude_unset=True,
            exclude_none=True,
            by_alias=True,
        ),
    )


def ubuntu_image_cmds_build_rootfs(  # noqa: PLR0913
    series: str,
    version: str,
    arch: str,
    sources: list[str],
    seed_branch: str,
    seeds: list[str],
    components_list: list[str],
    pocket: str,
    kernel: str | None = None,
    extra_snaps: list[str] | None = None,
    extra_packages: list[str] | None = None,
) -> list[str]:
    """List commands to ubuntu-image to generate a rootfs."""
    definition_yaml = generate_image_def_yaml(
        series,
        version,
        arch,
        sources,
        seed_branch,
        seeds,
        components_list,
        pocket,
        kernel,
        extra_snaps,
        extra_packages,
    )
    image_definition_file = "craft.yaml"

    return [
        f"cat << EOF > {image_definition_file}\n{definition_yaml}\nEOF",
        f"ubuntu-image classic --workdir work -O output/ {image_definition_file}",
        "mv work/chroot/* $CRAFT_PART_INSTALL/",
    ]


def ubuntu_image_pack(
    rootfs_path: str,
    gadget_path: str,
    output_path: str,
    image_type: str | None = None,
) -> None:
    """Pack the primed image contents into an image file."""
    cmd: list[str] = [
        "ubuntu-image",
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
