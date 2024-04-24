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


def test_project_package_repositories_invalid():
    def load_package_repositories(data, raises):
        with pytest.raises(raises) as err:
            PackageRepository.unmarshal(data)

        return str(err.value)

    mock_package_repositories = "test-not-a-dict"
    assert "invalid object." in load_package_repositories(
        mock_package_repositories,
        errors.PackageRepositoryValidationError,
    )

    mock_package_repositories = {
        "type": "apt",
        "pocket": "invalid",
    }
    assert "is not a valid enumeration member" in load_package_repositories(
        mock_package_repositories,
        ValidationError,
    )

    mock_package_repositories = {
        "type": "apt",
        "used-for": "test",
    }
    assert "is not a valid enumeration member" in load_package_repositories(
        mock_package_repositories,
        ValidationError,
    )

    ## Test PPA
    mock_package_repositories = {
        "type": "apt",
        "ppa": "test",
        "used-for": "test",
    }
    assert "is not a valid enumeration member" in load_package_repositories(
        mock_package_repositories,
        ValidationError,
    )

    ## Test invalid key-id
    mock_package_repositories = {
        "type": "apt",
        "ppa": "test",
        "key-id": "tooshort",
    }
    assert "ensure this value has at least 40 characters" in load_package_repositories(
        mock_package_repositories,
        ValidationError,
    )

    ## Test invalid auth
    mock_package_repositories = {
        "type": "apt",
        "ppa": "test",
        "auth": "invalid",
    }
    assert "string does not match regex" in load_package_repositories(
        mock_package_repositories,
        ValidationError,
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
        PackageRepositoryApt.unmarshal({"type": "apt", "used-for": "run"}),
    ]
    with pytest.raises(PackageRepositoryValidationError):
        get_main_package_repository(package_repositories)


def test_validate_package_repositories():
    def call_validate_package_repositories(data, raises):
        with pytest.raises(raises) as err:
            validate_package_repositories(data)

        return str(err.value)

    # Test 2 package repositories to build
    mock_package_repositories = [
        PackageRepositoryApt.unmarshal({"type": "apt", "used-for": "build"}),
        PackageRepositoryApt.unmarshal({"type": "apt", "used-for": "build"}),
    ]
    assert (
        "More than one package repository was defined to build the image."
        in call_validate_package_repositories(
            mock_package_repositories,
            PackageRepositoryValidationError,
        )
    )

    # Test no package repository to build
    mock_package_repositories = [
        PackageRepositoryApt.unmarshal({"type": "apt", "used_for": "run"}),
        PackageRepositoryPPA.unmarshal(
            {"type": "apt", "ppa": "test/test", "used-for": "build"},
        ),
    ]
    assert (
        "Missing a package repository to build the image."
        in call_validate_package_repositories(
            mock_package_repositories,
            PackageRepositoryValidationError,
        )
    )
