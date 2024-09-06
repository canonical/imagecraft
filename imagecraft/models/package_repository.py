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

"""Package repository definitions."""

import enum
import re
from collections.abc import Mapping
from typing import Any

import pydantic
from craft_archives.repo import errors  # type: ignore[import-untyped]
from craft_archives.repo.package_repository import (  # type: ignore[import-untyped]
    KeyIdStr,
    PocketEnum,
)

# pyright: reportMissingTypeStubs=false
from craft_archives.repo.package_repository import (  # type: ignore[import-untyped]
    PackageRepository as BasePackageRepository,
)
from craft_archives.repo.package_repository import (
    PackageRepositoryApt as BasePackageRepositoryApt,
)
from craft_archives.repo.package_repository import (
    PackageRepositoryAptPPA as BasePackageRepositoryAptPPA,
)
from pydantic import (
    AnyUrl,
    ConstrainedStr,
    FileUrl,  # pyright: ignore[reportUnknownVariableType]
)

from imagecraft.models.errors import PackageRepositoryValidationError


class AuthStr(ConstrainedStr):
    """A constrained string for an auth string."""

    regex = re.compile(r".*:.*")


class UsedForEnum(enum.Enum):
    """Enum values that represent how/when the package repository can be used for."""

    BUILD = "build"  # use the package repository only when building the image.
    RUN = "run"  # use the package repository only in the final image.
    ALWAYS = "always"  # use the package repository when building the image and keep it in the final image.


class PackageRepository(BasePackageRepository):  # type:ignore[misc]
    """Imagecraft package repository definition."""

    @classmethod
    def unmarshal(
        cls,
        data: Mapping[str, Any],
    ) -> "PackageRepositoryPPA | PackageRepositoryApt":
        """Create a package repository object from the given data."""
        if not isinstance(data, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise errors.PackageRepositoryValidationError(
                url=str(data),
                brief="invalid object.",
                details="Package repository must be a valid dictionary object.",
                resolution=(
                    "Verify repository configuration and ensure that the "
                    "correct syntax is used."
                ),
            )

        if "ppa" in data:
            return PackageRepositoryPPA.unmarshal(data)

        return PackageRepositoryApt.unmarshal(data)


class PackageRepositoryPPA(BasePackageRepositoryAptPPA):  # type:ignore[misc]
    """Imagecraft PPA repository definition."""

    auth: AuthStr | None
    key_id: KeyIdStr | None = pydantic.Field(
        alias="key-id",
    )  # here until added to craft-archives
    used_for: UsedForEnum = UsedForEnum.ALWAYS

    @classmethod
    def unmarshal(cls, data: Mapping[str, Any]) -> "PackageRepositoryPPA":
        """Create and populate a new ``PackageRepository`` object from dictionary data.

        The unmarshal method validates entries in the input dictionary, populating
        the corresponding fields in the data object.

        :param data: The dictionary data to unmarshal.

        :return: The newly created object.

        :raise TypeError: If data is not a dictionary.
        """
        if not isinstance(data, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("Package repository PPA data is not a dictionary")

        return cls.parse_obj({**data})


class PackageRepositoryApt(BasePackageRepositoryApt):  # type:ignore[misc]
    """Imagecraft APT package repository definition."""

    url: AnyUrl | FileUrl | None  # type: ignore[assignment] # pyright: ignore[reportIncompatibleVariableOverride]
    key_id: KeyIdStr | None = pydantic.Field(  # type: ignore[assignment]
        alias="key-id",
    )
    used_for: UsedForEnum = UsedForEnum.ALWAYS
    pocket: PocketEnum  # type: ignore[assignment] # pyright: ignore[reportIncompatibleVariableOverride]
    flavor: str | None

    @classmethod
    def unmarshal(cls, data: Mapping[str, Any]) -> "PackageRepositoryApt":
        """Create and populate a new ``PackageRepositoryApt`` object from dictionary data.

        The unmarshal method validates entries in the input dictionary, populating
        the corresponding fields in the data object.

        :param data: The dictionary data to unmarshal.

        :return: The newly created object.

        :raise TypeError: If data is not a dictionary.
        """
        if not isinstance(data, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("Package repository data is not a dictionary")

        return cls.parse_obj({**data})


def validate_package_repositories(
    project_repositories: list[PackageRepositoryPPA | PackageRepositoryApt],
) -> None:
    """Validate package repositories list."""
    repo_build_with_found = False
    repo_run_with_found = False

    for repo in project_repositories:
        if is_main_package_repository(repo):
            if repo_build_with_found:
                raise PackageRepositoryValidationError(
                    "More than one APT package repository was defined to build the image.",
                    details="At most one APT package-repository entry can be set to build the image.",
                )
            repo_build_with_found = True
        if is_customization_package_repository(repo):
            if repo_run_with_found:
                raise PackageRepositoryValidationError(
                    "More than one APT package repository was defined to customize the image.",
                    details="At most one APT package-repository entry can be set to customize the image.",
                )
            repo_run_with_found = True

    if not repo_build_with_found:
        raise PackageRepositoryValidationError(
            "Missing a package repository to build the image.",
            details="One APT package-repository entry with used-for set to 'build' or 'always' must be set to build the image.",
        )


def is_main_package_repository(
    repo: PackageRepositoryPPA | PackageRepositoryApt,
) -> bool:
    """Check if the package repository is the 'main' one, used to configure tools to build the image."""
    return isinstance(repo, PackageRepositoryApt) and repo.used_for in {
        UsedForEnum.BUILD,
        UsedForEnum.ALWAYS,
    }


def is_customization_package_repository(
    repo: PackageRepositoryPPA | PackageRepositoryApt,
) -> bool:
    """Check if the package repository is the customization repo, used to configure the image (but not used to build the image)."""
    return isinstance(repo, PackageRepositoryApt) and repo.used_for in {
        UsedForEnum.RUN,
        UsedForEnum.ALWAYS,
    }


def get_main_package_repository(
    project_repositories: list[PackageRepositoryPPA | PackageRepositoryApt],
) -> PackageRepositoryApt:
    """Get the 'main' package repository from a list.

    This function works under the assumption the list was previously validated and will
    raise an exception if no 'main' configuration is found.
    """
    for repo in project_repositories:
        if is_main_package_repository(repo):
            return repo  # type: ignore[return-value] # pyright: ignore[reportReturnType]
            # Due to the previous check we know repo is of type PackageRepositoryApt

    raise PackageRepositoryValidationError(
        "No 'main' package repository defined.",
        details="At least one 'main' package repository must be defined.",
    )


def get_customization_package_repository(
    project_repositories: list[PackageRepositoryPPA | PackageRepositoryApt],
) -> PackageRepositoryApt | None:
    """Get the customization package repository from a list."""
    for repo in project_repositories:
        if is_customization_package_repository(repo):
            return repo  # type: ignore[return-value] # pyright: ignore[reportReturnType]
            # Due to the previous check we know repo is of type PackageRepositoryApt

    return None
