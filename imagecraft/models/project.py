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

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

import pydantic
from craft_application.models import BuildInfo
from craft_application.models import Project as BaseProject

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


def _alias_generator(s: str) -> str:
    return s.replace("_", "-")

class ProjectValidationError(CraftError):
    """Error validatiing image.yaml."""

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

    keep_enabled: bool = True

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
                _format_pydantic_errors(error.errors()),
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


def _format_pydantic_errors(errors: list[Any], *, file_name: str = "imagecraft.yaml") -> str:
    """Format errors.

    Example 1: Single error.

    Bad iamgecraft.yaml content:
    - field: <some field>
      reason: <some reason>

    Example 2: Multiple errors.

    Bad imagecraft.yaml content:
    - field: <some field>
      reason: <some reason>
    - field: <some field 2>
      reason: <some reason 2>
    """
    combined = [f"Bad {file_name} content:"]
    for error in errors:
        formatted_loc = _format_pydantic_error_location(error["loc"])
        formatted_msg = _format_pydantic_error_message(error["msg"])

        if formatted_msg == "field required":
            field_name, location = _printable_field_location_split(formatted_loc)
            combined.append(
                f"- field {field_name} required in {location} configuration",
            )
        elif formatted_msg == "extra fields not permitted":
            field_name, location = _printable_field_location_split(formatted_loc)
            combined.append(
                f"- extra field {field_name} not permitted in {location} configuration",
            )
        elif formatted_msg == "the list has duplicated items":
            field_name, location = _printable_field_location_split(formatted_loc)
            combined.append(
                f" - duplicate entries in {field_name} not permitted in {location} configuration",
            )
        elif formatted_loc == "__root__":
            combined.append(f"- {formatted_msg}")
        else:
            combined.append(f"- {formatted_msg} (in field {formatted_loc!r})")

    return "\n".join(combined)

def _format_pydantic_error_location(loc: Iterable[str | int]) -> str:
    """Format location."""
    loc_parts: list[str] = []
    for loc_part in loc:
        if isinstance(loc_part, str):
            loc_parts.append(loc_part)
        elif isinstance(loc_part, int): # pyright: ignore[reportUnnecessaryIsInstance]
            # Integer indicates an index. Go
            # back and fix up previous part.
            previous_part = loc_parts.pop()
            previous_part += f"[{loc_part}]"
            loc_parts.append(previous_part)
        else:
            raise TypeError(f"unhandled loc: {loc_part}")

    loc = ".".join(loc_parts)

    # Filter out internal __root__ detail.
    return loc.replace(".__root__", "")


def _format_pydantic_error_message(msg: str) -> str:
    """Format pydantic's error message field."""
    # Replace shorthand "str" with "string".
    return msg.replace("str type expected", "string type expected")

def _printable_field_location_split(location: str) -> tuple[str, str]:
    """Return split field location.

    If top-level, location is returned as unquoted "top-level".
    If not top-level, location is returned as quoted location, e.g.

    (1) field1[idx].foo => 'foo', 'field1[idx]'
    (2) field2 => 'field2', top-level

    :returns: tuple of <field name>, <location> as printable representations.
    """
    loc_split = location.split(".")
    field_name = repr(loc_split.pop())

    if loc_split:
        return field_name, repr(".".join(loc_split))

    return field_name, "top-level"
