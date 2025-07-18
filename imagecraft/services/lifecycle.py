# This file is part of imagecraft.
#
# Copyright 2023-2025 Canonical Ltd.
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

"""Imagecraft Lifecycle service."""

import hashlib
from pathlib import Path
from typing import cast

from craft_application import LifecycleService
from craft_cli import CraftError
from craft_parts.executor.errors import EnvironmentChangedError
from overrides import override  # type: ignore[reportUnknownVariableType]

from imagecraft import models


class ImagecraftLifecycleService(LifecycleService):
    """Imagecraft-specific lifecycle service."""

    @override
    def setup(self) -> None:
        """Initialize the LifecycleManager with previously-set arguments."""
        # Configure extra args to the LifecycleManager
        project = cast(models.Project, self._services.get("project").get())

        base_layer_name = "bare_base_layer"
        base_layer_dir = self._work_dir / Path(base_layer_name)
        base_layer_dir.mkdir(parents=True, exist_ok=True)
        hasher = hashlib.sha1()  # noqa: S324

        hasher.update(base_layer_name.encode())

        self._manager_kwargs.update(
            project_name=project.name,
            base_layer_dir=base_layer_dir,
            base_layer_hash=hasher.digest(),
            filesystem_mounts=project.filesystems,
        )

        super().setup()

    @override
    def run(self, step_name: str | None, part_names: list[str] | None = None) -> None:
        """Run the lifecycle manager for the parts."""
        try:
            super().run(step_name, part_names)
        except EnvironmentChangedError as err:
            raise CraftError(
                message="Partitions changed.",
                details=str(err),
                resolution="Run imagecraft clean",
            )
