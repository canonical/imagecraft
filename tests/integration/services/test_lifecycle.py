# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2025 Canonical Ltd.
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
import os
import pathlib
import re
from typing import cast

import pytest
from craft_application import ServiceFactory
from craft_cli import CraftError
from craft_parts.executor.errors import EnvironmentChangedError
from craft_parts.executor.part_handler import (
    PartHandler,
)
from imagecraft.services.image import ImageService
from imagecraft.services.lifecycle import ImagecraftLifecycleService

requires_root = pytest.mark.skipif(os.getuid() != 0, reason="requires root privileges")


@requires_root
def test_lifecycle_args(
    lifecycle_service: ImagecraftLifecycleService,
    mocker,
):
    lifecycle_service.setup()

    mocker.patch.object(PartHandler, "run_action", side_effect=EnvironmentChangedError)

    with pytest.raises(CraftError, match="Partitions changed"):
        lifecycle_service.run("pull")


@requires_root
def test_lifecycle_prologue_hook(
    lifecycle_service: ImagecraftLifecycleService, default_factory: ServiceFactory
):
    lifecycle_service.setup()

    # The project_info is what craft-parts passes to the prologue hook
    # We can get it from the manager after setup()
    project_info = lifecycle_service._lcm._project_info

    try:
        # Trigger the prologue hook manually for verification
        lifecycle_service._prologue_hook(project_info)

        # Verify environment variables
        # default_project_yaml has volume 'pc' with structures 'efi' and 'rootfs'
        assert "CRAFT_VOLUME_PC" in project_info.global_environment
        assert "CRAFT_VOLUME_PC_EFI" in project_info.global_environment
        assert "CRAFT_VOLUME_PC_ROOTFS" in project_info.global_environment

        volume_path = project_info.global_environment["CRAFT_VOLUME_PC"]
        efi_path = project_info.global_environment["CRAFT_VOLUME_PC_EFI"]
        rootfs_path = project_info.global_environment["CRAFT_VOLUME_PC_ROOTFS"]

        assert pathlib.Path(volume_path).exists()
        assert re.match("^/dev/loop[0-9]+$", volume_path)
        assert pathlib.Path(efi_path).exists()
        assert re.match("^/dev/loop[0-9]+p1$", efi_path)
        assert pathlib.Path(rootfs_path).exists()
        assert re.match("^/dev/loop[0-9]+p2$", rootfs_path)

    finally:
        cast(ImageService, default_factory.get("image")).detach_images()
