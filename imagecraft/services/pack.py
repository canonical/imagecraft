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

import contextlib
import os
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from craft_application import PackageService, models, util
from craft_cli import CraftError, emit
from typing_extensions import override

from imagecraft.models import (
    FileSystem,
    ImageMetadata,
    Project,
    Role,
    VolumeMetadata,
    get_partition_name,
)
from imagecraft.models.volume import GptType
from imagecraft.pack import Image, diskutil, grubutil
from imagecraft.services.image import ImageService


class ImagecraftPackService(PackageService):
    """Package service subclass for Imagecraft."""

    _PACK_INPUTS_STATE_FILE = ".imagecraft-pack-state.yaml"
    _METADATA_RELATIVE_PATH = Path(".image") / "metadata.yaml"

    @override
    def get_artifacts(self) -> dict[str | None, Path]:
        """Get the output image artifact for the current project."""
        volume_name = self._single_volume_name()
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
        grub-install availability inside the image all affect the resulting
        image, but none of them are part inputs, so a change to any of them is
        invisible to craft-parts' lifecycle planning and won't trigger a
        lifecycle rerun.
        """
        project = cast(Project, self._services.get("project").get())
        volume_name = self._single_volume_name()
        volume = project.volumes[volume_name]
        project_info = self._services.get("lifecycle").project_info
        rootfs_prime_dir = self._rootfs_prime_dir(volume_name)
        metadata_partition = self._select_metadata_partition()
        metadata_yaml = self._render_image_metadata()

        return {
            "volume": volume.marshal(),
            "arch": project_info.target_arch,
            "filesystem_mount": project_info.default_filesystem_mount.marshal(),
            "grub_install_available": self._image_has_grub_install(rootfs_prime_dir),
            "metadata": {
                "partition": metadata_partition,
                "content": metadata_yaml,
            },
        }

    def _build_image_metadata(self) -> ImageMetadata:
        """Build the metadata payload from project and build state."""
        project = cast(Project, self._services.get("project").get())
        project_info = self._services.get("lifecycle").project_info
        artifact_name, artifact_format = self._metadata_volume_artifact()

        return ImageMetadata(
            name=project.name,
            base=project.base,
            build_base=(
                project.build_base if project.build_base != project.base else None
            ),
            platform=self._build_info.platform,
            architecture=project_info.target_arch,
            title=project.title,
            version=project.version,
            summary=project.summary,
            description=project.description,
            contact=self._normalize_metadata_list(project.contact),
            issues=self._normalize_metadata_list(project.issues),
            source_code=str(project.source_code) if project.source_code else None,
            volumes={artifact_name: VolumeMetadata(format=artifact_format)},
        )

    def _metadata_volume_artifact(self) -> tuple[str, str]:
        """Return the output artifact filename and format for the primary artifact.

        Per specification, ``metadata.yaml`` ``volumes`` are mapped by emitted artifact
        filename, not by the project volume name.
        """
        artifact_path = self.get_artifacts()[None]
        artifact_name = artifact_path.name
        artifact_suffix = artifact_path.suffix.lower()

        if artifact_suffix == ".img":
            artifact_format = "raw"
        else:
            artifact_format = artifact_suffix.removeprefix(".") or "raw"

        return artifact_name, artifact_format

    def _normalize_metadata_list(
        self, values: str | Iterable[object] | None
    ) -> list[str] | None:
        """Normalize project metadata fields that allow either a scalar or a list."""
        if values is None:
            return None

        if isinstance(values, str):
            return [values]

        return [str(value) for value in values] or None

    def _render_image_metadata(self) -> str:
        """Render deterministic metadata YAML."""
        metadata = self._build_image_metadata()
        return yaml.safe_dump(
            metadata.model_dump(by_alias=True, exclude_none=True),
            sort_keys=False,
            allow_unicode=False,
        )

    def _select_metadata_partition(self) -> str:
        """Select the metadata partition using the required priority order."""
        project = cast(Project, self._services.get("project").get())
        volume_name = self._single_volume_name()
        volume = project.volumes[volume_name]

        for structure_item in volume.structure:
            structure_type = getattr(structure_item, "structure_type", None)
            if structure_type == GptType.EFI_SYSTEM:
                return get_partition_name(volume_name, structure_item)

            if structure_type is not None:
                _, _, gpt_type = structure_type.partition(",")
                if gpt_type.upper() == GptType.EFI_SYSTEM.value:
                    return get_partition_name(volume_name, structure_item)

        for structure_item in volume.structure:
            if structure_item.role == Role.SYSTEM_BOOT:
                return get_partition_name(volume_name, structure_item)

        if not volume.structure:
            raise CraftError(
                f"Volume {volume_name} has no partitions; cannot inject image metadata."
            )

        return get_partition_name(volume_name, volume.structure[0])

    def _partition_filesystem(self, partition_name: str) -> FileSystem:
        """Return the filesystem for a named partition in the single supported volume."""
        project = cast(Project, self._services.get("project").get())
        volume_name = self._single_volume_name()
        volume = project.volumes[volume_name]

        for structure_item in volume.structure:
            if get_partition_name(volume_name, structure_item) == partition_name:
                return structure_item.filesystem

        raise AssertionError(f"Unknown partition {partition_name!r}")

    def _metadata_path_supports_permissions(self, partition_name: str) -> bool:
        """Return True when the metadata path is on a filesystem with Unix mode bits."""
        return self._partition_filesystem(partition_name) in {
            FileSystem.EXT3,
            FileSystem.EXT4,
        }

    def _apply_metadata_permissions(
        self, partition_name: str, metadata_path: Path
    ) -> None:
        """Apply permissions where the target filesystem supports them."""
        if not self._metadata_path_supports_permissions(partition_name):
            return

        metadata_path.parent.chmod(0o555)
        metadata_path.chmod(0o444)

    def _prepare_metadata_path_for_cleanup(
        self, partition_name: str, metadata_path: Path
    ) -> None:
        """Restore normal host-side permissions for generated metadata in prime."""
        if not self._metadata_path_supports_permissions(partition_name):
            return

        with contextlib.suppress(OSError):
            metadata_path.parent.chmod(0o755)
        with contextlib.suppress(OSError):
            metadata_path.chmod(0o644)

    def _metadata_file_path(self, partition_name: str, *, stage: bool = False) -> Path:
        """Return the metadata file path in a partition's stage or prime directory."""
        project_dirs = self._services.get("lifecycle").project_info.dirs
        if stage:
            base_dir = project_dirs.get_stage_dir(partition=partition_name)
        else:
            base_dir = project_dirs.get_prime_dir(partition=partition_name)
        return base_dir / self._METADATA_RELATIVE_PATH

    def _metadata_file_matches_content(
        self, metadata_path: Path, *, expected_content: str
    ) -> bool:
        """Return True when a metadata file still matches generated content."""
        try:
            return (
                metadata_path.exists() and metadata_path.read_text() == expected_content
            )
        except OSError:
            return False

    def _assert_no_metadata_conflict(self, partition_name: str) -> None:
        """Reject user-supplied metadata."""
        for metadata_path in (
            self._metadata_file_path(partition_name, stage=True),
            self._metadata_file_path(partition_name),
        ):
            if not metadata_path.exists():
                continue

            raise CraftError(
                f"User-provided metadata file {metadata_path} conflicts with generated image metadata.",
                resolution=(
                    "Remove '.image/metadata.yaml' from the selected partition's "
                    "content and let Imagecraft generate it. If the file was left "
                    "behind by an interrupted pack, run 'imagecraft clean'."
                ),
            )

    def _remove_metadata_file(self, partition_name: str) -> None:
        """Remove a generated metadata file from a partition's prime directory."""
        metadata_path = self._metadata_file_path(partition_name)
        if not metadata_path.exists():
            return

        self._prepare_metadata_path_for_cleanup(
            partition_name=partition_name, metadata_path=metadata_path
        )
        metadata_path.unlink()

        with contextlib.suppress(OSError):
            metadata_path.parent.rmdir()

    def _remove_metadata_file_if_matches(
        self, partition_name: str, *, expected_content: str
    ) -> None:
        """Remove a prime metadata file when it still matches generated content."""
        metadata_path = self._metadata_file_path(partition_name)
        if not self._metadata_file_matches_content(
            metadata_path, expected_content=expected_content
        ):
            return

        self._remove_metadata_file(partition_name)

    def _remove_stale_metadata_files(
        self, partition_name: str, metadata_yaml: str
    ) -> None:
        """Remove metadata files left behind by interrupted generated writes."""
        self._remove_metadata_file_if_matches(
            partition_name, expected_content=metadata_yaml
        )

        stored_fingerprint = self._read_persisted_pack_fingerprint()
        if stored_fingerprint is None:
            return

        metadata = stored_fingerprint.get("metadata")
        if not isinstance(metadata, dict):
            return

        previous_partition = metadata.get("partition")
        previous_content = metadata.get("content")
        if not isinstance(previous_partition, str) or not isinstance(
            previous_content, str
        ):
            return

        self._remove_metadata_file_if_matches(
            previous_partition, expected_content=previous_content
        )

    def _inject_metadata_file(self, partition_name: str, metadata_yaml: str) -> Path:
        """Write the generated metadata into the selected prime directory."""
        metadata_path = self._metadata_file_path(partition_name)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(metadata_yaml)
        self._apply_metadata_permissions(partition_name, metadata_path)
        return metadata_path

    def _rootfs_prime_dir(self, volume_name: str) -> Path | None:
        """Return the prime dir for the image rootfs partition, if any."""
        project = cast(Project, self._services.get("project").get())
        volume = project.volumes[volume_name]

        rootfs_structure = None
        for structure_item in volume.structure:
            if structure_item.role == Role.SYSTEM_DATA:
                rootfs_structure = structure_item
                break

        if rootfs_structure is None:
            return None

        partition_name = get_partition_name(volume_name, rootfs_structure)
        project_dirs = self._services.get("lifecycle").project_info.dirs
        return project_dirs.get_prime_dir(partition=partition_name)

    def _image_has_grub_install(self, rootfs_prime_dir: Path | None) -> bool:
        """Check whether the image rootfs provides grub-install."""
        if rootfs_prime_dir is None:
            return False

        return (rootfs_prime_dir / "usr/sbin/grub-install").is_file()

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
            raw_state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError, UnicodeError):
            emit.debug(f"Failed to read pack-input state from {state_path!r}.")
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
                loaded_state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError, UnicodeError):
                emit.debug(
                    f"Failed to read pack-input state from {state_path!r}, rewriting from scratch."
                )
                loaded_state = None
            if isinstance(loaded_state, dict):
                raw_state = loaded_state

        fingerprints = raw_state.get("pack_inputs")
        if not isinstance(fingerprints, dict):
            fingerprints = {}
            raw_state["pack_inputs"] = fingerprints

        fingerprints[self._build_info.platform] = self._current_pack_fingerprint()

        tmp_path = state_path.with_name(
            f"{state_path.name}.{self._build_info.platform}.{os.getpid()}.tmp"
        )
        try:
            tmp_path.write_text(util.dump_yaml(raw_state), encoding="utf-8")
            tmp_path.replace(state_path)
        except (OSError, TypeError):
            tmp_path.unlink(missing_ok=True)

    def _remove_artifact(self, path: Path) -> None:
        """Remove a finalized artifact that is no longer known-good."""
        with contextlib.suppress(FileNotFoundError):
            path.unlink()

    @override
    def pack_artifacts(self) -> Mapping[str | None, bool]:
        """Pack artifacts and clean eager temp images when packing is skipped."""
        packed = super().pack_artifacts()
        # The lifecycle prologue creates temp images before the repack decision,
        # so a skipped pack would otherwise leave them behind.
        if not all(packed.values()):
            image_service = cast(ImageService, self._services.get("image"))
            image_service.cleanup_temporary_images()
        return packed

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
        platform = self._build_info.platform
        state_service = self._services.get("state")
        state_entries = [
            {"name": name, "path": str(path)} for name, path in artifacts.items()
        ]

        state_service.set(
            "artifacts",
            platform,
            value=cast(Any, state_entries or None),
            overwrite=True,
        )
        self._write_persisted_pack_fingerprint()

    @override
    def _pack(self, *, name: str | None = None, path: Path) -> None:
        """Pack the image artifact for the current project."""
        self._remove_artifact(path)

        project = cast(Project, self._services.get("project").get())
        volume_name = self._single_volume_name()
        volume = project.volumes[volume_name]
        metadata_partition = self._select_metadata_partition()
        metadata_yaml = self._render_image_metadata()

        self._remove_stale_metadata_files(metadata_partition, metadata_yaml)
        self._assert_no_metadata_conflict(metadata_partition)
        try:
            # Inside the try so a partially written file is also cleaned up;
            # the conflict check above guarantees the path was ours to use.
            self._inject_metadata_file(metadata_partition, metadata_yaml)

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

            artifact_path: Path | None = None
            try:
                artifact_path = image_service.finalize_images(path.parent)[volume_name]

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
            except Exception:
                if artifact_path is not None:
                    self._remove_artifact(artifact_path)
                raise
        finally:
            # The metadata only needs to exist while partitions are populated;
            # don't leave it in prime after the pack, even when interrupted.
            # A cleanup failure must not mask the original pack error.
            try:
                self._remove_metadata_file(metadata_partition)
            except OSError as err:
                emit.debug(f"Failed to remove generated image metadata: {err}")

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
