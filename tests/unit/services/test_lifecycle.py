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

from craft_application import util
from craft_parts import (
    LifecycleManager,
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
        arch="x86_64",
        cache_dir=Path("cache"),
        work_dir=Path("work"),
        ignore_local_sources=[],
        platform="amd64",
        base="ubuntu@22.04",
        project_name="default",
        project_vars={"version": "1.0"},
        package_repositories=None,
    )


def test_lifecycle_args_no_platform(
    lifecycle_service_no_platform,
    mocker,
    monkeypatch,
):
    mock_lifecycle = mocker.patch.object(
        LifecycleManager,
        "__init__",
        return_value=None,
    )

    lifecycle_service_no_platform.setup()

    mock_lifecycle.assert_called_once_with(
        {"parts": {}},
        application_name="imagecraft",
        arch="x86_64",
        cache_dir=Path("cache"),
        work_dir=Path("work"),
        ignore_local_sources=[],
        platform=None,
        base="ubuntu@22.04",
        project_name="default",
        project_vars={"version": "1.0"},
        package_repositories=None,
    )

    assert lifecycle_service_no_platform._platform == util.get_host_architecture()
