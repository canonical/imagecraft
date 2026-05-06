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

import craft_platforms
from craft_application import LifecycleService
from craft_cli import CraftError
from craft_parts import Action, callbacks
from craft_parts.executor.errors import EnvironmentChangedError
from craft_parts.infos import ProjectInfo
from craft_parts.plugins import Plugin
from craft_parts.plugins.plugins import PluginGroup
from typing_extensions import override

from imagecraft import models, plugins
from imagecraft.services.image import ImageService


class ImagecraftLifecycleService(LifecycleService):
    """Imagecraft-specific lifecycle service."""

    @staticmethod
    @override
    def get_plugin_group(
        build_info: craft_platforms.BuildInfo,
    ) -> dict[str, type[Plugin]] | None:
        return {**PluginGroup.MINIMAL.value, **plugins.get_app_plugins()}  # pyright: ignore[reportUnknownMemberType]

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
        callbacks.register_prologue(self._prologue_hook)

    def _prologue_hook(self, project_info: ProjectInfo) -> None:
        """Create images and export loop device paths as environment variables."""
        image_service = cast(ImageService, self._services.get("image"))
        image_service.create_images()
        image_service.attach_images()

        for key, path in image_service.get_loop_paths().items():
            env_key = f"CRAFT_VOLUME_{key.upper().replace('/', '_').replace('-', '_')}"
            project_info.global_environment[env_key] = path

    @override
    def _exec(self, actions: list[Action]) -> None:
        """Execute actions of the lifecycle."""
        try:
            super()._exec(actions)
        except EnvironmentChangedError as err:
            raise CraftError(
                message="Partitions changed.",
                details=str(err),
                resolution="Run imagecraft clean",
            )
