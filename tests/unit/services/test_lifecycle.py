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

from pathlib import Path
from unittest.mock import ANY

from craft_parts import (
    LifecycleManager,
)
from imagecraft.models.package_repository import (
    PackageRepositoryApt,
    PocketEnum,
    UsedForEnum,
)


def test_lifecycle_args(
    lifecycle_service,
    mocker,
    monkeypatch,
):
    mock_lifecycle = mocker.patch.object(
        LifecycleManager,
        "__init__",
        return_value=None,
    )

    lifecycle_service.setup()

    mock_lifecycle.assert_called_once_with(
        {"parts": {}},
        application_name="imagecraft",
        arch="amd64",
        cache_dir=Path("cache"),
        work_dir=Path("work"),
        ignore_local_sources=[],
        parallel_build_count=ANY,  # Value will vary when tests run locally or in CI
        project_vars_part_name=None,
        project_vars={"version": "1"},
        track_stage_packages=True,
        partitions=None,
        build_for="amd64",
        platform="amd64",
        base="ubuntu@22.04",
        project_name="default",
        package_repositories_=[
            PackageRepositoryApt(  # pyright: ignore[reportCallIssue]
                type="apt",
                priority=None,
                architectures=None,
                formats=None,
                path=None,
                components=["main", "restricted"],
                suites=None,
                pocket=PocketEnum.PROPOSED,
                series="jammy",
                used_for=UsedForEnum.ALWAYS,
                flavor=None,
            ),
        ],
        series="jammy",
    )
