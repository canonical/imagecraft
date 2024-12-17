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

import typing
from typing import Any, Literal, Self

from craft_application.errors import CraftValidationError
from craft_application.models import BuildPlanner as BaseBuildPlanner
from craft_application.models import Platform as BasePlatform
from craft_application.models import Project as BaseProject
from craft_providers import bases
from craft_providers.errors import BaseConfigurationError
from pydantic import (
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)
from typing_extensions import override

from .volume import Volume


class Platform(BasePlatform):
    """Imagecraft project platform definition."""

    @model_validator(mode="after")  # pyright: ignore[reportUntypedFunctionDecorator]
    def _validate_platform_set(self) -> Self:
        """Validate the build_on build_for combination."""
        build_on: list[str] = self.build_on if self.build_on else []

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


class BuildPlanner(BaseBuildPlanner):
    """BuildPlanner for Imagecraft projects."""

    platforms: dict[str, Platform]  # type: ignore[assignment]
    base: BaseT  # type: ignore[reportIncompatibleVariableOverride]
    build_base: BuildBaseT = None  # type: ignore[reportIncompatibleVariableOverride]

    @field_validator("build_base")
    @classmethod
    def _validate_build_base(
        cls, value: str | None, info: ValidationInfo
    ) -> str | None:
        """Build-base defaults to the base value if not specified.

        :raises CraftValidationError: If base validation fails.
        """
        if not value:
            base_value = info.data.get("base")
            if base_value == "bare":
                raise ValueError('When "base" is bare, a build-base must be specified.')
            return base_value
        return value

    @field_validator(
        "platforms",
        mode="before",
    )  # pyright: ignore[reportUntypedFunctionDecorator]
    @classmethod
    def _preprocess_all_platforms(cls, platforms: dict[str, Any]) -> dict[str, Any]:
        """Convert the simplified form of platform to the full one."""
        for platform_label, platform in platforms.items():
            if platform is None:
                platforms[platform_label] = {
                    "build_on": platform_label,
                    "build_for": platform_label,
                }

        return platforms


class Project(BuildPlanner, BaseProject):
    """Definition of imagecraft.yaml configuration."""

    platforms: dict[str, Platform] | None = None  # type: ignore[assignment, reportIncompatibleVariableOverride]
    volumes: dict[str, Volume] | None = None

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

        :returns: The BaseAlias for the base or None for bare bases.
        :raises ValueError: If the project's base cannot be determined.
        """
        if base == "bare":
            return None

        if base == "devel":
            return bases.get_base_alias(("ubuntu", "devel"))

        try:
            name, channel = base.split("@")
            return bases.get_base_alias(bases.BaseName(name, channel))
        except (ValueError, BaseConfigurationError) as err:
            raise ValueError(f"Unknown base {base!r}") from err
