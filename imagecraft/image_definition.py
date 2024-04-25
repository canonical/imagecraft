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


"""Ubuntu-image image definition model."""

from craft_application.util import dump_yaml
from pydantic import BaseModel, Field


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
    flavor: str | None
    pocket: str
    mirror: str | None
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

    # pylint: disable=too-many-arguments
    def __init__(  # noqa: PLR0913
        self,
        series: str,
        revision: str,
        architecture: str,
        pocket: str,
        kernel: str | None,
        components: list[str],
        flavor: str | None,
        mirror: str | None,
        seed_urls: list[str],
        seed_branch: str,
        seed_names: list[str],
        seed_pocket: str,
        extra_snaps: list[str] | None = None,
        extra_packages: list[str] | None = None,
    ):
        super().__init__(
            name="craft-driver",
            display_name="Craft Driver",
            class_="preinstalled",  # type: ignore[call-arg]
            revision=revision,
            architecture=architecture,
            series=series,
            kernel=kernel,
            rootfs=Rootfs(
                components=components,
                flavor=flavor,
                mirror=mirror,
                pocket=pocket,
                seed=Seed(
                    urls=seed_urls,
                    branch=seed_branch,
                    names=seed_names,
                    pocket=seed_pocket,
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
            self.customization = Customization(
                extra_snaps=extra_snaps_obj,
                extra_packages=extra_packages_obj,
            )

    def dump_yaml(self) -> str | None:
        """Generate a definition yaml file for rootfs creation."""
        return dump_yaml(
            self.dict(
                exclude_unset=True,
                exclude_none=True,
                by_alias=True,
            ),
        )
