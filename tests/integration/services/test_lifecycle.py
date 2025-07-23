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

import pytest
from craft_cli import CraftError
from craft_parts.executor.errors import EnvironmentChangedError
from craft_parts.executor.part_handler import (
    PartHandler,
)
from imagecraft.services.lifecycle import ImagecraftLifecycleService


def test_lifecycle_args(
    lifecycle_service: ImagecraftLifecycleService,
    mocker,
):
    lifecycle_service.setup()

    mocker.patch.object(PartHandler, "run_action", side_effect=EnvironmentChangedError)

    with pytest.raises(CraftError, match="Partitions changed"):
        lifecycle_service.run("pull")
