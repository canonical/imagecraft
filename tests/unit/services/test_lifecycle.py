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
from unittest.mock import ANY, MagicMock

from craft_parts import LifecycleManager, ProjectVar, ProjectVarInfo, callbacks
from craft_parts.infos import ProjectInfo
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
        ignore_local_sources=[".craft"],
        ignore_outdated=[".craft"],
        parallel_build_count=ANY,  # Value will vary when tests run locally or in CI
        project_vars=ProjectVarInfo.unmarshal(
            {
                "version": ProjectVar(value="1.0"),
                "summary": ProjectVar(
                    value="default project", updated=False, part_name=None
                ),
                "description": ProjectVar(
                    value="default project", updated=False, part_name=None
                ),
            }
        ),
        track_stage_packages=True,
        partitions=["volume/pc/rootfs", "volume/pc/efi"],
        build_for="amd64",
        platform="amd64",
        project_name="default",
        base_layer_dir=Path("work/bare_base_layer"),
        base_layer_hash=b"i\x8e\x9c\xa4\x12\x1e\xe8\x97\xe4g\x08\xbc\x88\xddjb\x07\x8cp\xec",
        filesystem_mounts={
            "default": [
                {"device": "(volume/pc/rootfs)", "mount": "/"},
                {"device": "(volume/pc/efi)", "mount": "/boot/efi"},
            ]
        },
    )


def test_lifecycle_setup_registers_prologue(
    lifecycle_service: ImagecraftLifecycleService,
    mocker,
):
    mocker.patch.object(LifecycleManager, "__init__", return_value=None)
    mock_register = mocker.patch.object(callbacks, "register_prologue")

    lifecycle_service.setup()

    mock_register.assert_called_once_with(lifecycle_service._prologue_hook)


def test_lifecycle_prologue_hook(
    lifecycle_service: ImagecraftLifecycleService,
    mocker,
):
    mock_image_service = MagicMock()
    mock_image_service.get_loop_paths.return_value = {
        "pc": "/dev/loop8",
        "pc/efi": "/dev/loop8p1",
        "pc/rootfs": "/dev/loop8p2",
    }
    mocker.patch.object(
        lifecycle_service._services, "get", return_value=mock_image_service
    )

    project_info = MagicMock(spec=ProjectInfo)
    project_info.global_environment = {}

    lifecycle_service._prologue_hook(project_info)

    assert project_info.global_environment == {
        "CRAFT_VOLUME_PC": "/dev/loop8",
        "CRAFT_VOLUME_PC_EFI": "/dev/loop8p1",
        "CRAFT_VOLUME_PC_ROOTFS": "/dev/loop8p2",
    }
    mock_image_service.create_images.assert_called_once()
    mock_image_service.attach_images.assert_called_once()
