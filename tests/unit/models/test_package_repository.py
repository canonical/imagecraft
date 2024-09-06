# This file is part of imagecraft.
#
# Copyright (C) 2022 Canonical Ltd
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import pytest
from craft_archives.repo import errors  # type: ignore[import-untyped]
from imagecraft.models import PackageRepository
from imagecraft.models.errors import PackageRepositoryValidationError
from imagecraft.models.package_repository import (
    PackageRepositoryApt,
    PackageRepositoryPPA,
    get_main_package_repository,
    validate_package_repositories,
)
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("error_value", "error_class", "package_repositories"),
    [
        ("invalid object.", errors.PackageRepositoryValidationError, "test-not-a-dict"),
        (
            "is not a valid enumeration member",
            ValidationError,
            {
                "type": "apt",
                "pocket": "invalid",
            },
        ),
        (
            "is not a valid enumeration member",
            ValidationError,
            {
                "type": "apt",
                "ppa": "test",
                "used-for": "test",
            },
        ),
        (
            "ensure this value has at least 40 characters",
            ValidationError,
            {
                "type": "apt",
                "ppa": "test",
                "key-id": "tooshort",
            },
        ),
        (
            "string does not match regex",
            ValidationError,
            {
                "type": "apt",
                "ppa": "test",
                "auth": "invalid",
            },
        ),
    ],
)
def test_project_package_repositories_invalid(
    error_value,
    error_class,
    package_repositories,
):
    def load_package_repositories(data, raises):
        with pytest.raises(raises) as err:
            PackageRepository.unmarshal(data)

        return str(err.value)

    assert error_value in load_package_repositories(
        package_repositories,
        error_class,
    )


def test_project_package_repositories_apt_invalid():
    def load_package_repositories_apt(data, raises):
        with pytest.raises(raises) as err:
            PackageRepositoryApt.unmarshal(data)

        return str(err.value)

    mock_package_repositories = "test-not-a-dict"
    assert (
        "Package repository data is not a dictionary"
        in load_package_repositories_apt(
            mock_package_repositories,
            TypeError,
        )
    )


def test_project_package_repositories_ppa_invalid():
    def load_package_repositories_ppa(data, raises):
        with pytest.raises(raises) as err:
            PackageRepositoryPPA.unmarshal(data)

        return str(err.value)

    mock_package_repositories = "test-not-a-dict"
    assert (
        "Package repository PPA data is not a dictionary"
        in load_package_repositories_ppa(
            mock_package_repositories,
            TypeError,
        )
    )


def test_get_main_package_repository_error():
    package_repositories: list[PackageRepositoryPPA | PackageRepositoryApt] = [
        PackageRepositoryApt.unmarshal(
            {"type": "apt", "used-for": "run", "pocket": "release"},
        ),
    ]
    with pytest.raises(PackageRepositoryValidationError):
        get_main_package_repository(package_repositories)


@pytest.mark.parametrize(
    ("error_value", "error_class", "package_repositories"),
    [
        (
            "More than one APT package repository was defined to build the image.",
            PackageRepositoryValidationError,
            [
                PackageRepositoryApt.unmarshal(
                    {"type": "apt", "used-for": "build", "pocket": "release"},
                ),
                PackageRepositoryApt.unmarshal(
                    {"type": "apt", "used-for": "build", "pocket": "release"},
                ),
            ],
        ),
        (
            "Missing a package repository to build the image.",
            PackageRepositoryValidationError,
            [
                PackageRepositoryApt.unmarshal(
                    {"type": "apt", "used_for": "run", "pocket": "release"},
                ),
                PackageRepositoryPPA.unmarshal(
                    {"type": "apt", "ppa": "test/test", "used-for": "build"},
                ),
            ],
        ),
        (
            "More than one APT package repository was defined to customize the image.",
            PackageRepositoryValidationError,
            [
                PackageRepositoryApt.unmarshal(
                    {"type": "apt", "used-for": "always", "pocket": "release"},
                ),
                PackageRepositoryApt.unmarshal(
                    {"type": "apt", "used-for": "run", "pocket": "release"},
                ),
            ],
        ),
    ],
)
def test_validate_all_package_repositories(
    error_value,
    error_class,
    package_repositories,
):
    def call_validate_package_repositories(data, raises):
        with pytest.raises(raises) as err:
            validate_package_repositories(data)

        return str(err.value)

    assert error_value in call_validate_package_repositories(
        package_repositories,
        error_class,
    )
