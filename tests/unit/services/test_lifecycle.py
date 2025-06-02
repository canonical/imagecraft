# This file is part of imagecraft.
#
# Copyright 2022-2025 Canonical Ltd.
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
from craft_platforms import DebianArchitecture
from imagecraft.services.lifecycle import ImagecraftLifecycleService


def test_lifecycle_args(
    lifecycle_service: ImagecraftLifecycleService,
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
        {
            "parts": {
                "my-part": {
                    "plugin": "nil",
                }
            }
        },
        application_name="imagecraft",
        arch=str(DebianArchitecture.from_host()),
        cache_dir=Path("cache"),
        work_dir=Path("work"),
        ignore_local_sources=[],
        parallel_build_count=ANY,  # Value will vary when tests run locally or in CI
        project_vars_part_name=None,
        project_vars={"version": "1.0"},
        track_stage_packages=True,
        partitions=["default", "volume/pc/efi"],
        build_for="amd64",
        platform="amd64",
        project_name="default",
        base_layer_dir=Path("work/bare_base_layer"),
        base_layer_hash=b"i\x8e\x9c\xa4\x12\x1e\xe8\x97\xe4g\x08\xbc\x88\xddjb\x07\x8cp\xec",
        filesystem_mounts={"default": [{"device": "(default)", "mount": "/"}]},
    )
