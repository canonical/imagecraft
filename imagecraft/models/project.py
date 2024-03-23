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

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import pydantic
from craft_application.models import BuildInfo
from craft_application.models import Project as BaseProject
from craft_application.util.error_formatting import format_pydantic_errors

# pyright: reportMissingTypeStubs=false
from craft_archives.repo.package_repository import (  # type: ignore[import-untyped]
    PackageRepositoryApt as BasePackageRepositoryApt,
)
from craft_cli import CraftError
from craft_providers import bases
from pydantic import (
    BaseModel,
    ValidationError,
    conlist,
    validator,  # pyright: ignore[reportUnknownVariableType]
)
from pydantic_yaml import YamlModelMixin

# A workaround for mypy false positives
# see https://github.com/samuelcolvin/pydantic/issues/975#issuecomment-551147305
# fmt: off
if TYPE_CHECKING:
    UniqueStrList = list[str]
else:
    UniqueStrList = conlist(str, unique_items=True, min_items=1)

file_name = "imagecraft.yaml"

def _alias_generator(s: str) -> str:
    return s.replace("_", "-")

class ProjectValidationError(CraftError):
    """Error validating imagecraft.yaml."""

class ProjectModel(YamlModelMixin, BaseProject):
    """Base model for the imagecraft project class."""

    class Config:
        """Pydantic model configuration."""

        validate_assignment = True
        extra = pydantic.Extra.forbid
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = _alias_generator


class ElementModel(YamlModelMixin, BaseModel):
    """Base model for project elements (subentries)."""

    class Config:
        """Pydantic model configuration."""

        validate_assignment = True
        extra = pydantic.Extra.forbid
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = _alias_generator


class Platform(ElementModel):
    """Imagecraft project platform definition."""

    build_on: UniqueStrList | None
    build_for: UniqueStrList | None
    extensions: UniqueStrList = []

    def __hash__(self) -> int:
        return hash("_".join(str(self.build_for) + str(self.extensions)))

    @validator("build_on", "build_for", pre=True, always=True) # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def _apply_vectorise(cls, val: UniqueStrList | None | str) -> UniqueStrList | None | str:
        """Implement a hook to vectorise."""
        if isinstance(val, str):
            val = [val]
        return val

class PackageRepository(BasePackageRepositoryApt): # type:ignore[misc]
    """Imagecraft package repository definition."""

    @classmethod
    def unmarshal(cls, data: Mapping[str, Any]) -> "PackageRepository":
        """Create and populate a new ``PackageRepository`` object from dictionary data.

        The unmarshal method validates entries in the input dictionary, populating
        the corresponding fields in the data object.

        :param data: The dictionary data to unmarshal.

        :return: The newly created object.

        :raise TypeError: If data is not a dictionary.
        """
        if not isinstance(data, dict): # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("Package repository data is not a dictionary")

        if "key-id" not in data:
            data["key-id"] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"

        return cls(**data)


class Project(ProjectModel):
    """Definition of imagecraft.yaml configuration."""

    platforms: dict[str, Platform]
    series: str
    package_repositories: list[dict[str,Any]] | list[PackageRepository] | None

    @validator("package_repositories") # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def _validate_package_repositories(
        cls, project_repositories: list[dict[str, Any]],
    ) -> list[PackageRepository]:
        repositories: list[PackageRepository] = []
        for data in project_repositories:
            if not isinstance(data, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
                raise TypeError("value must be a dictionary but is not")

            repositories.append(PackageRepository.unmarshal(data))

        return repositories


    @classmethod
    def unmarshal(cls, data: dict[str, Any]) -> "Project":
        """Unmarshal object with necessary translations and error handling.

        (1) Perform any necessary translations.

        (2) Standardize error reporting.

        :returns: valid Project.

        :raises CraftError: On failure to unmarshal object.
        """
        try:
            return cls.parse_obj({**data})
        except ValidationError as error:
            raise ProjectValidationError(
                format_pydantic_errors(error.errors(), file_name=file_name),
            ) from error


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
