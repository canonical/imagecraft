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

import yaml
from craft_application import PackageService, models, util
from craft_cli import emit
from typing_extensions import override

from imagecraft.models import Project, get_partition_name
from imagecraft.pack import Image, diskutil, grubutil
from imagecraft.services.image import ImageService


class ImagecraftPackService(PackageService):
    """Package service subclass for Imagecraft."""

    _PACK_INPUTS_STATE_FILE = ".imagecraft-pack-state.yaml"

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

    def _pack_inputs_state_path(self) -> Path:
        """Return the persistent pack-inputs state file path."""
        project_dirs = self._services.get("lifecycle").project_info.dirs
        return project_dirs.work_dir / self._PACK_INPUTS_STATE_FILE

    def _read_persisted_pack_fingerprint(self) -> dict[str, Any] | None:
        """Read the persisted pack-input fingerprint for the current platform."""
        state_path = self._pack_inputs_state_path()
        platform = self._build_info.platform

        if not state_path.is_file():
            return None

        try:
            raw_state = yaml.safe_load(state_path.read_text())
        except (OSError, yaml.YAMLError):
            emit.debug(f"Failed to read pack-input state from {str(state_path)!r}.")
            return None

        if not isinstance(raw_state, dict):
            return None

        fingerprints = raw_state.get("pack_inputs")
        if not isinstance(fingerprints, dict):
            return None

        stored_fingerprint = fingerprints.get(platform)
        return stored_fingerprint if isinstance(stored_fingerprint, dict) else None

    def _write_persisted_pack_fingerprint(self) -> None:
        """Persist the current pack-input fingerprint in the project work tree."""
        state_path = self._pack_inputs_state_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)

        raw_state: dict[str, Any] = {}
        if state_path.is_file():
            try:
                loaded_state = yaml.safe_load(state_path.read_text())
            except (OSError, yaml.YAMLError):
                loaded_state = None
            if isinstance(loaded_state, dict):
                raw_state = loaded_state

        fingerprints = raw_state.get("pack_inputs")
        if not isinstance(fingerprints, dict):
            fingerprints = {}
            raw_state["pack_inputs"] = fingerprints

        fingerprints[self._build_info.platform] = self._current_pack_fingerprint()

        tmp_path = state_path.with_name(
            f"{state_path.name}.{self._build_info.platform}.{id(self)}.tmp"
        )
        tmp_path.write_text(util.dump_yaml(raw_state))
        tmp_path.replace(state_path)

    @override
    def _app_needs_repack(self, partition: str | None = None) -> bool:
        """Determine whether pack-time inputs changed since the last pack.

        This is only consulted once the framework has already confirmed the
        artifact exists, the lifecycle didn't need to rerun, and no package or
        extra-asset files changed. It only needs to check the Imagecraft-specific
        inputs described in `_current_pack_fingerprint`, and must prefer
        returning True whenever it can't prove the artifact is still valid.
        """
        stored_fingerprint = self._read_persisted_pack_fingerprint()
        if stored_fingerprint is None:
            return True

        return stored_fingerprint != self._current_pack_fingerprint()

    @override
    def write_artifacts_state(self, artifacts: Mapping[str | None, Path]) -> None:
        """Write artifact-oriented packaging state."""
        super().write_artifacts_state(artifacts)
        self._write_persisted_pack_fingerprint()

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
