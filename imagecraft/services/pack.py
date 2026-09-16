# Copyright 2023-2025 Canonical Ltd.
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

"""Imagecraft Package service."""

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from craft_application import PackageService, models
from craft_cli import emit
from typing_extensions import override

from imagecraft.models import Project, get_partition_name
from imagecraft.pack import Image, diskutil, grubutil
from imagecraft.services.image import ImageService


class ImagecraftPackService(PackageService):
    """Package service subclass for Imagecraft."""

    @override
    def get_artifacts(self) -> dict[str | None, Path]:
        """Get the output image artifact for the current project."""
        project = cast(Project, self._services.get("project").get())
        if len(project.volumes) != 1:
            raise AssertionError("This code can only handle one volume")

        volume_name, _ = next(iter(project.volumes.items()))
        return {None: self.output_dir / f"{volume_name}.img"}

    def _single_volume_name(self) -> str:
        """Return the single supported volume name."""
        project = cast(Project, self._services.get("project").get())
        if len(project.volumes) != 1:
            raise AssertionError("This code can only handle one volume")

        volume_name, _ = next(iter(project.volumes.items()))
        return volume_name

    def _current_pack_fingerprint(self) -> dict[str, Any]:
        """Build a fingerprint of the pack-time inputs the lifecycle can't see.

        Volume layout, target architecture, filesystem-mount configuration, and
        grub-install availability all affect the resulting image, but none of
        them are part inputs, so a change to any of them is invisible to
        craft-parts' lifecycle planning and won't trigger a lifecycle rerun.
        """
        project = cast(Project, self._services.get("project").get())
        volume_name = self._single_volume_name()
        volume = project.volumes[volume_name]
        project_info = self._services.get("lifecycle").project_info

        return {
            "volume": volume.marshal(),
            "arch": project_info.target_arch,
            "filesystem_mount": project_info.default_filesystem_mount.marshal(),
            "grub_install_available": shutil.which("grub-install") is not None,
        }

    @override
    def _app_needs_repack(self, partition: str | None = None) -> bool:
        """Determine whether pack-time inputs changed since the last pack.

        This is only consulted once the framework has already confirmed the
        artifact exists, the lifecycle didn't need to rerun, and no package or
        extra-asset files changed. It only needs to check the Imagecraft-specific
        inputs described in `_current_pack_fingerprint`, and must prefer
        returning True whenever it can't prove the artifact is still valid.
        """
        platform = self._build_info.platform
        state_service = self._services.get("state")

        try:
            stored_fingerprint = state_service.get("pack_inputs", platform)
        except KeyError:
            return True

        return stored_fingerprint != self._current_pack_fingerprint()

    @override
    def write_artifacts_state(self, artifacts: Mapping[str | None, Path]) -> None:
        """Write artifact-oriented packaging state."""
        platform = self._build_info.platform
        state_service = self._services.get("state")
        state_entries = [
            {"name": name, "path": str(path)} for name, path in artifacts.items()
        ]

        state_service.set(
            "artifacts", platform, value=state_entries or None, overwrite=True
        )
        state_service.set(
            "pack_inputs",
            platform,
            value=self._current_pack_fingerprint(),
            overwrite=True,
        )

    @override
    def _pack(self, *, name: str | None = None, path: Path) -> None:
        """Pack the image artifact for the current project."""
        project = cast(Project, self._services.get("project").get())
        volume_name = self._single_volume_name()
        volume = project.volumes[volume_name]

        image_service = cast(ImageService, self._services.get("image"))
        # Both calls are idempotent — the prologue hook will have run them
        # already during the lifecycle, but pack may be called standalone.
        image_service.create_images()
        image_service.attach_images()

        project_dirs = self._services.get("lifecycle").project_info.dirs
        loop_paths = image_service.get_loop_paths()

        try:
            for structure_item in volume.structure:
                partition_name = get_partition_name(volume_name, structure_item)
                emit.progress(f"Preparing partition {partition_name}")
                partition_prime_dir = project_dirs.get_prime_dir(
                    partition=partition_name
                )
                loop_path = Path(loop_paths[f"{volume_name}/{structure_item.name}"])

                diskutil.format_device(
                    device_path=loop_path,
                    fstype=structure_item.filesystem,
                    label=structure_item.filesystem_label,
                    content_dir=partition_prime_dir,
                )

            image_service.verify_images()
        finally:
            image_service.detach_images()

        artifact_path = image_service.finalize_image(volume_name, path)

        filesystem_mount = self._services.get(
            "lifecycle"
        ).project_info.default_filesystem_mount
        arch = self._services.get("lifecycle").project_info.target_arch
        image = Image(volume=volume, disk_path=artifact_path)
        grubutil.setup_grub(
            image=image,
            workdir=project_dirs.work_dir,
            arch=arch,
            filesystem_mount=filesystem_mount,
        )

    @property
    def metadata(self) -> models.BaseMetadata:
        """Get the metadata model for this project."""
        # nop (no metadata file for Imagecraft)
        return models.BaseMetadata()

    @override
    def write_metadata(self, path: Path) -> None:
        """Write the project metadata to metadata.yaml in the given directory.

        :param path: The path to the prime directory.
        """
        # nop (no metadata file for Imagecraft)
