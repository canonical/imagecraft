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

from typing import Any, Self

from craft_application.errors import CraftValidationError
from craft_application.models import BuildPlanner as BaseBuildPlanner
from craft_application.models import Platform as BasePlatform
from craft_application.models import Project as BaseProject
from pydantic import (
    ConfigDict,
    field_validator,
    model_validator,
)

from imagecraft.architectures import SUPPORTED_ARCHS


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


class BuildPlanner(BaseBuildPlanner):
    """BuildPlanner for Imagecraft projects."""

    platforms: dict[str, Platform]  # type: ignore[assignment]

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

    @field_validator("platforms")  # pyright: ignore[reportUntypedFunctionDecorator]
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


class Project(BuildPlanner, BaseProject):
    """Definition of imagecraft.yaml configuration."""

    platforms: dict[str, Platform] | None = None  # type: ignore[assignment, reportIncompatibleVariableOverride]
    model_config = ConfigDict(
        validate_assignment=True,
        extra="forbid",
        frozen=False,
        populate_by_name=True,
    )
