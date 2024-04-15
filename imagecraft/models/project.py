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

from craft_application.errors import CraftValidationError
from craft_application.models import BuildInfo
from craft_application.models import Project as BaseProject
from craft_providers import bases
from pydantic import (
    BaseModel,
    conlist,
    root_validator,  # pyright: ignore[reportUnknownVariableType]
    validator,  # pyright: ignore[reportUnknownVariableType]
)
from pydantic_yaml import YamlModelMixin

from imagecraft.architectures import SUPPORTED_ARCHS

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

    @validator("build_on", "build_for", pre=True, always=True) # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def _apply_vectorise(cls, val: UniqueStrList | None | str) -> UniqueStrList | None | str:
        """Implement a hook to vectorise."""
        if isinstance(val, str):
            val = [val]
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

        # If build_for is provided, then build_on must also be
        if not build_on and build_for:
            raise CraftValidationError(
                "'build_for' expects 'build_on' to also be provided.",
            )

        return values


class Project(ProjectModel):
    """Definition of imagecraft.yaml configuration."""

    series: str
    platforms: dict[str, Platform]

    @validator("platforms", pre=True) # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def preprocess_all_platforms(cls, platforms: dict[str, Any]) -> dict[str, Any]:
        """Convert the simplified form of platform to the full one."""
        for platform_label, platform in platforms.items():
            if platform is None:
                if platform_label not in SUPPORTED_ARCHS:
                    raise CraftValidationError(
                        f"Invalid platform {platform_label}.",
                        details="A platform name must either be a valid architecture name or the "
                        "platform must specify one or more build-on and build-for architectures.",
                    )
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

    @property
    def effective_base(self) -> bases.BaseName:
        """Get the Base name for craft-providers."""
        base = super().effective_base
        name, channel = base.split("@")
        return bases.BaseName(name, channel)

    def get_build_plan(self) -> list[BuildInfo]:
        """Obtain the list of architectures from the project file."""
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
