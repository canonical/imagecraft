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

"""Imagecraft Lifecycle service."""

import hashlib
from pathlib import Path
from typing import cast

from craft_application import LifecycleService
from overrides import override  # type: ignore[reportUnknownVariableType]

from imagecraft.models.project import Project


class ImagecraftLifecycleService(LifecycleService):
    """Imagecraft-specific lifecycle service."""

    @override
    def setup(self) -> None:
        """Initialize the LifecycleManager with previously-set arguments."""
        # Configure extra args to the LifecycleManager
        project = cast(Project, self._project)

        hasher = hashlib.sha1()  # noqa: S324
        path = "./overlay/"

        hasher.update(path.encode())

        self._manager_kwargs.update(
            base=project.base,
            project_name=project.name,
            base_layer_dir=Path(path),
            base_layer_hash=hasher.digest(),
        )

        super().setup()
