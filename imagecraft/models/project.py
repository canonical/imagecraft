# This file is part of imagecraft.
#
# Copyright 2023-2025 Canonical Ltd.
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

"""Imagecraft project definition.

This module defines a imagecraft.yaml file, exportable to a JSON schema.
"""

import typing
from typing import Annotated, Any, Literal, Self

from craft_application.errors import CraftValidationError
from craft_application.models import CraftBaseModel
from craft_application.models import Platform as BasePlatform
from craft_application.models import Project as BaseProject
from craft_providers import bases
from pydantic import (
    ConfigDict,
    Field,
    model_validator,
)
from typing_extensions import override

from imagecraft.models.volume import (
    StructureItem,
    Volume,
    VolumeName,
)


class Platform(BasePlatform):
    """Imagecraft project platform definition."""

    @model_validator(mode="after")  # pyright: ignore[reportUntypedFunctionDecorator]
    def _validate_platform_set(self) -> Self:
        """Validate the build_on build_for combination."""
        build_on: list[str] | str = self.build_on if self.build_on else []

        # We can only build on 1 arch at the moment
        if len(build_on) > 1:
            raise CraftValidationError(
                str(
                    f"Trying to build an image on {build_on} "
                    "but multiple architectures are not "
                    "currently supported. Please specify only 1 value.",
                ),
            )

        return self


BaseT = Literal["bare"]
BuildBaseT = typing.Annotated[
    Literal["ubuntu@20.04", "ubuntu@22.04", "ubuntu@24.04", "devel"] | None,
    Field(validate_default=True),
]


VolumeDictT = Annotated[dict[VolumeName, Volume], Field(min_length=1, max_length=1)]


class Project(BaseProject):
    """Definition of imagecraft.yaml configuration."""

    base: BaseT  # type: ignore[reportIncompatibleVariableOverride]
    build_base: BuildBaseT  # type: ignore[reportIncompatibleVariableOverride]
    volumes: VolumeDictT

    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )

    @override
    @classmethod
    def _providers_base(cls, base: str) -> bases.BaseAlias | None:
        """Get a BaseAlias from imagecraft's base.

        :param base: The base name.

        :returns: Always None because imagecraft only supports bare bases.
        """
        return None

    def get_partitions(self) -> list[str]:
        """Get a list of partitions based on the project's volumes.

        :returns: A list of partitions formatted as ['default', 'volume/<name>', ...]
        """
        return _get_partitions_from_volumes(self.volumes)


class VolumeProject(CraftBaseModel, extra="ignore"):
    """Project definition containing only volumes data."""

    volumes: VolumeDictT

    def get_partitions(self) -> list[str]:
        """Get a list of partitions based on the project's volumes.

        :returns: A list of partitions formatted as ['default', 'volume/<name>', ...]
        """
        return _get_partitions_from_volumes(self.volumes)


def get_partition_name(volume_name: str, structure: StructureItem) -> str:
    """Get the name of the partition associated to the StructureItem."""
    return f"volume/{volume_name}/{structure.name}"


def _get_partitions_from_volumes(
    volumes_data: dict[str, Any],
) -> list[str]:
    """Get a list of partitions based on the project's volumes.

    :returns: A list of partitions formatted as ['default', 'volume/<name>', ...]
    """
    partitions: list[str] = ["default"]
    for volume_name, volume in volumes_data.items():
        partitions.extend(
            [
                get_partition_name(volume_name, structure)
                for structure in volume.structure
            ]
        )
    return partitions
