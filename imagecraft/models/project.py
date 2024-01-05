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

"""Imagecraft project definition.

This module defines a imagecraft.yaml file, exportable to a JSON schema.
"""
from typing import TYPE_CHECKING

from craft_application.models import BuildInfo
from craft_application.models import Project as BaseProject
from craft_providers import bases
from pydantic import BaseModel, conlist, validator
from pydantic_yaml import YamlModelMixin

# A workaround for mypy false positives
# see https://github.com/samuelcolvin/pydantic/issues/975#issuecomment-551147305
# fmt: off
if TYPE_CHECKING:
    UniqueStrList = list[str]
else:
    UniqueStrList = conlist(str, unique_items=True, min_items=1)


class ProjectModel(YamlModelMixin, BaseProject):
    """Base model for the imagecraft project class."""

    class Config:
        """Pydantic model configuration."""

        validate_assignment = True
        extra = "forbid"
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = lambda s: s.replace("_", "-")  # noqa: E731 # type: ignore[reportUnknownLambdaType,reportUnknownVariableType,reportUnknownMemberType]


class ElementModel(YamlModelMixin, BaseModel):
    """Base model for project elements (subentries)."""

    class Config:
        """Pydantic model configuration."""

        validate_assignment = True
        extra = "forbid"
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = lambda s: s.replace("_", "-")  # noqa: E731 # type: ignore[reportUnknownLambdaType,reportUnknownVariableType,reportUnknownMemberType]


class Platform(ElementModel):
    """Imagecraft project platform definition."""

    build_on: UniqueStrList | None
    build_for: UniqueStrList | None
    extensions: UniqueStrList = []

    def __hash__(self) -> int:
        return hash("_".join(str(self.build_for) + str(self.extensions)))

    @validator("build_on", "build_for", pre=True, always=True)
    @classmethod
    def _apply_vectorise(cls, val: UniqueStrList | None | str) -> UniqueStrList | None | str:
        """Implement a hook to vectorise."""
        if isinstance(val, str):
            val = [val]
        return val


class Project(ProjectModel):
    """Definition of imagecraft.yaml configuration."""

    platforms: dict[str, Platform]
    series: str

    @property
    def effective_base(self) -> bases.BaseName:
        """Get the Base name for craft-providers."""
        base = super().effective_base
        name, channel = base.split("@")
        return bases.BaseName(name, channel)

    def get_build_plan(self) -> list[BuildInfo]:
        """Obtain the list of architectures and bases from the project file."""
        build_infos: list[BuildInfo] = []
        base = self.effective_base

        for platform_entry, platform in self.platforms.items():
            for build_for in platform.build_for or [platform_entry]:
                build_infos.extend(
                    BuildInfo(
                            platform=platform_entry,
                            build_on=build_on,
                            build_for=build_for,
                            base=base,
                    ) for build_on in platform.build_on or [platform_entry]
                )

        return build_infos
