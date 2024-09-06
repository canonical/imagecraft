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

import craft_application
import pydantic
from craft_application.errors import CraftValidationError
from craft_application.models import BuildPlanner as BaseBuildPlanner
from craft_application.models import Project as BaseProject
from craft_application.util.error_formatting import format_pydantic_errors
from pydantic import (
    ValidationError,
    conlist,
    root_validator,  # pyright: ignore[reportUnknownVariableType]
    validator,  # pyright: ignore[reportUnknownVariableType]
)
from pydantic_yaml import YamlModelMixin

from imagecraft.architectures import SUPPORTED_ARCHS
from imagecraft.models.errors import ProjectValidationError
from imagecraft.models.package_repository import (
    PackageRepository,
    PackageRepositoryApt,
    PackageRepositoryPPA,
    validate_package_repositories,
)

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

class Platform(craft_application.models.Platform):
    """Imagecraft project platform definition."""

    class Config:
        """Pydantic model configuration."""

        validate_assignment = True
        extra = pydantic.Extra.forbid
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = _alias_generator

    build_on: UniqueStrList | None
    build_for: UniqueStrList | None


    @validator("build_on", "build_for", pre=True, always=True) # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def _apply_vectorise(cls, val: UniqueStrList | None | str) -> UniqueStrList | None | str:
        """Implement a hook to vectorise."""
        if isinstance(val, str):
            val = [val]
        return val

    @validator("build_for", pre=True, always=True) # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def _preprocess_build_for(cls, val: UniqueStrList | None | str, values: dict[str, Any]) -> UniqueStrList | None | str:
        build_on = values.get("build_on")
        if not val or len(val) == 0:
            return build_on
        return val

    @root_validator(skip_on_failure=True) # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def _validate_platform_set(cls, values: Mapping[str, Any]) -> Mapping[str, Any]:
        """Validate the build_on build_for combination."""
        build_for: list[str] = values["build_for"] if values.get("build_for") else []
        build_on: list[str] = values["build_on"] if values.get("build_on") else []

        # We can only build for 1 arch at the moment
        if len(build_for) > 1:
            raise CraftValidationError(
                str(
                    f"Trying to build an image for {build_for} "
                    "but multiple target architectures are not "
                    "currently supported. Please specify only 1 value.",
                ),
            )

        # We can only build on 1 arch at the moment
        if len(build_on) > 1:
            raise CraftValidationError(
                str(
                    f"Trying to build an image on {build_on} "
                    "but multiple architectures are not "
                    "currently supported. Please specify only 1 value.",
                ),
            )

        return values

class BuildPlanner(BaseBuildPlanner):
    """BuildPlanner for Imagecraft projects."""

    platforms: dict[str, Platform]  # type: ignore[assignment]
    base: str | None
    build_base: str | None

    @validator("platforms", pre=True) # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def _preprocess_all_platforms(cls, platforms: dict[str, Any]) -> dict[str, Any]:
        """Convert the simplified form of platform to the full one."""
        for platform_label, platform in platforms.items():
            if platform is None:
                platforms[platform_label] = {"build_on":platform_label, "build_for": platform_label}

        return platforms

    @validator("platforms") # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def _validate_all_platforms(cls, platforms: dict[str, Any]) -> dict[str, Platform]:
        """Make sure all provided platforms are tangible and sane."""
        for platform_label, platform in platforms.items():
            error_prefix = f"Error for platform entry '{platform_label}'"

            # build_on and build_for are validated
            # let's also validate the platform label
            # If the label maps to a valid architecture and
            # `build-for` is present, then both need to have the same value,
            # otherwise the project is invalid.
            if platform.build_for:
                build_target = platform.build_for[0]
                if platform_label in SUPPORTED_ARCHS and platform_label != build_target:
                    raise CraftValidationError(
                        str(
                            f"{error_prefix}: if 'build_for' is provided and the "
                            "platform entry label corresponds to a valid architecture, then "
                            f"both values must match. {platform_label} != {build_target}",
                        ),
                    )
            else:
                build_target = platform_label

            build_on_one_of = (
                platform.build_on if platform.build_on else [platform_label]
            )
            # Both build and target architectures must be supported
            if not any(b_o in SUPPORTED_ARCHS for b_o in build_on_one_of):
                raise CraftValidationError(
                    str(
                        f"{error_prefix}: trying to build image in one of "
                        f"{build_on_one_of}, but none of these build architectures is supported. "
                        f"Supported architectures: {SUPPORTED_ARCHS}",
                    ),
                )

            if build_target not in SUPPORTED_ARCHS:
                raise CraftValidationError(
                    str(
                        f"{error_prefix}: trying to build image for target "
                        f"architecture {build_target}, which is not supported. "
                        f"Supported architectures: {SUPPORTED_ARCHS}",
                    ),
                )

            platforms[platform_label] = platform

        return platforms

class Project(YamlModelMixin, BuildPlanner, BaseProject):
    """Definition of imagecraft.yaml configuration."""

    series: str
    package_repositories_: list[dict[str,Any]] | list[PackageRepositoryPPA | PackageRepositoryApt] | None = pydantic.Field(alias="package-repositories") # type: ignore[assignment]
    # Override package_repositories alias from BaseProject to prevent pydantic trying to parse
    # the received package-repositories in it.
    package_repositories: list[dict[str, Any]] | None = pydantic.Field(alias="unused")
    platforms: dict[str, Platform]  # type: ignore[assignment]

    class Config:
        """Pydantic model configuration."""

        validate_assignment = True
        extra = pydantic.Extra.forbid
        allow_mutation = True
        allow_population_by_field_name = True
        alias_generator = _alias_generator

    @validator("package_repositories_") # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def _validate_all_package_repositories(
        cls, project_repositories: list[dict[str, Any]],
    ) -> list[PackageRepositoryPPA | PackageRepositoryApt]:
        repositories: list[PackageRepositoryPPA | PackageRepositoryApt] = []
        repositories = [ PackageRepository.unmarshal(data) for data in project_repositories ]

        validate_package_repositories(repositories)
        return repositories

    @pydantic.validator(  # pyright: ignore[reportUnknownMemberType,reportUntypedFunctionDecorator]
        "package_repositories_", each_item=True,
    )
    def _validate_package_repositories(
        cls, repository: dict[str, Any],
    ) -> dict[str, Any]:
        # Override _validate_package_repositories defined in craft-application
        # Do nothing because at this point the package-repositories are not dicts anymore
        # but PackageRepository* objects and so _validate_package_repositories fails.
        return repository


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
