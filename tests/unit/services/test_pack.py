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

from pathlib import Path
from typing import Any, cast

import pytest
import yaml
from craft_application import ServiceFactory
from craft_cli import CraftError
from craft_parts import ProjectDirs, ProjectInfo, ProjectVar, ProjectVarInfo
from craft_parts.filesystem_mounts import FilesystemMount, FilesystemMounts
from imagecraft.errors import GRUBInstallError
from imagecraft.models import Project
from imagecraft.models.volume import (
    GPTStructureItem,
    GptType,
    HybridStructureItem,
    Role,
)
from imagecraft.services.image import ImageService
from imagecraft.services.pack import ImagecraftPackService
from pydantic import AnyUrl, TypeAdapter


@pytest.fixture(autouse=True)
def isolated_state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Give each test its own state directory.

    The state service otherwise defaults to a directory keyed by the test
    process's PID, so state written by one test would otherwise leak into
    every other test run in the same pytest session.
    """
    monkeypatch.setenv("CRAFT_STATE_DIR", str(tmp_path / "craft-state"))


@pytest.fixture
def mock_image_service(default_factory: ServiceFactory, tmp_path):
    """ImageService with losetup operations mocked out."""
    svc = cast(ImageService, default_factory.get("image"))
    svc._images = {"pc": tmp_path / ".pc.img.tmp"}
    svc._loop_devices = {"pc": "/dev/loop8"}
    svc._atexit_registered = True
    yield svc
    svc._loop_devices.clear()


@pytest.fixture
def mock_lifecycle(default_factory: ServiceFactory, mocker):
    project_service = default_factory.get("project")
    project_dirs = ProjectDirs(
        work_dir=Path("work"), partitions=project_service.partitions
    )

    project_info = ProjectInfo(
        application_name="imagecraft",
        cache_dir=Path("cache"),
        arch="amd64",
        parallel_build_count=1,
        project_name="default",
        project_dirs=project_dirs,
        project_vars=ProjectVarInfo.unmarshal(
            {
                "version": ProjectVar(value="1.0").marshal(),
                "summary": ProjectVar(value="default project").marshal(),
                "description": ProjectVar(value="default project").marshal(),
            }
        ),
        partitions=project_service.partitions,
        filesystem_mounts=FilesystemMounts.unmarshal(
            {
                "default": FilesystemMount.unmarshal(
                    [
                        {"mount": "/", "device": "(volume/pc/rootfs)"},
                        {"mount": "/boot/efi", "device": "(volume/pc/efi)"},
                    ]
                )
            }
        ),
    )
    lifecycle = mocker.Mock()
    lifecycle.project_info = project_info
    lifecycle.requires_repack = False
    lifecycle.prime_dir = project_dirs.prime_dir

    original_get = default_factory.get

    def get_service(name: str):
        if name == "lifecycle":
            return lifecycle
        return original_get(name)

    mocker.patch.object(default_factory, "get", side_effect=get_service)
    return lifecycle


@pytest.fixture
def configured_pack_service(
    pack_service: ImagecraftPackService,
    default_factory: ServiceFactory,
    tmp_path: Path,
    enable_features,
    mock_lifecycle,
) -> ImagecraftPackService:
    pack_service.set_output_dir(tmp_path / "dest")
    default_factory.get("project").get()
    pack_service.update_project()
    return pack_service


@pytest.fixture
def rootfs_prime_dir(configured_pack_service: ImagecraftPackService) -> Path:
    volume_name = configured_pack_service._single_volume_name()
    prime_dir = configured_pack_service._rootfs_prime_dir(volume_name)
    assert prime_dir is not None
    prime_dir.mkdir(parents=True, exist_ok=True)
    return prime_dir


def _metadata_path(
    configured_pack_service: ImagecraftPackService,
    partition_name: str,
    *,
    stage: bool = False,
) -> Path:
    project_dirs = configured_pack_service._services.get("lifecycle").project_info.dirs
    if stage:
        base_dir = project_dirs.get_stage_dir(partition=partition_name)
    else:
        base_dir = project_dirs.get_prime_dir(partition=partition_name)
    return base_dir / configured_pack_service._METADATA_RELATIVE_PATH


def _mock_pack_dependencies(
    mock_image_service: ImageService, artifact_path: Path, mocker
) -> Any:
    """Mock image and disk operations for a successful pack; return diskutil."""
    mocker.patch.object(mock_image_service, "create_images")
    mocker.patch.object(mock_image_service, "attach_images")
    mocker.patch.object(mock_image_service, "verify_images")
    mocker.patch.object(mock_image_service, "detach_images")
    mocker.patch.object(
        mock_image_service,
        "finalize_images",
        return_value={"pc": artifact_path},
    )
    mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mocker.patch("imagecraft.services.pack.Image", autospec=True)
    return mocker.patch("imagecraft.services.pack.diskutil", autospec=True)


def test_get_artifacts(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
):
    assert configured_pack_service.get_artifacts() == {
        None: tmp_path / "dest" / "pc.img"
    }


def test_render_image_metadata(
    configured_pack_service: ImagecraftPackService,
):
    metadata = yaml.safe_load(configured_pack_service._render_image_metadata())

    assert metadata == {
        "name": "default",
        "base": "bare",
        "build-base": "devel",
        "platform": configured_pack_service._build_info.platform,
        "architecture": "amd64",
        "version": "1.0",
        "summary": "default project",
        "description": "default project",
        "volumes": {"pc.img": {"format": "raw"}},
    }
    assert "title" not in metadata
    assert "contact" not in metadata
    assert "issues" not in metadata
    assert "source-code" not in metadata


def test_render_image_metadata_omits_build_base_matching_base(
    configured_pack_service: ImagecraftPackService,
):
    """ST181 only requires build-base when it differs from base."""
    project = cast(Project, configured_pack_service._services.get("project").get())
    # Bypass validation: no currently valid project has matching bases.
    object.__setattr__(project, "build_base", project.base)

    metadata = yaml.safe_load(configured_pack_service._render_image_metadata())

    assert metadata["base"] == "bare"
    assert "build-base" not in metadata


def test_render_image_metadata_uses_artifact_extension_for_volume_format(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
    mocker,
):
    configured_pack_service.set_output_dir(tmp_path / "dest")
    mocker.patch.object(
        configured_pack_service,
        "get_artifacts",
        return_value={None: tmp_path / "dest" / "pc.vhd"},
    )

    metadata = yaml.safe_load(configured_pack_service._render_image_metadata())

    assert metadata["volumes"] == {"pc.vhd": {"format": "vhd"}}


def test_metadata_volume_artifact_uses_output_filename_key(
    configured_pack_service: ImagecraftPackService,
):
    artifact_name, artifact_format = configured_pack_service._metadata_volume_artifact()

    assert artifact_name == "pc.img"
    assert artifact_format == "raw"


def test_render_image_metadata_normalizes_scalar_project_metadata(
    configured_pack_service: ImagecraftPackService,
):
    project = configured_pack_service._services.get("project").get()
    project.contact = "dev@example.com"
    project.issues = "https://example.com/issues"
    project.source_code = TypeAdapter(AnyUrl).validate_python(
        "https://github.com/canonical/imagecraft"
    )

    metadata = yaml.safe_load(configured_pack_service._render_image_metadata())

    assert metadata["contact"] == ["dev@example.com"]
    assert metadata["issues"] == ["https://example.com/issues"]
    assert metadata["source-code"] == "https://github.com/canonical/imagecraft"


def test_select_metadata_partition_prefers_efi(
    configured_pack_service: ImagecraftPackService,
):
    project = cast(Project, configured_pack_service._services.get("project").get())
    volume = cast(object, project.volumes["pc"])
    object.__setattr__(
        volume,
        "structure",
        [
            GPTStructureItem(
                name="data",
                structure_type=GptType.LINUX_DATA,
                role=Role.SYSTEM_DATA,
                size="1G",
                filesystem="ext4",
            ),
            GPTStructureItem(
                name="efi",
                structure_type=GptType.EFI_SYSTEM,
                role=Role.SYSTEM_DATA,
                size="256M",
                filesystem="vfat",
            ),
            GPTStructureItem(
                name="boot",
                structure_type=GptType.WINDOWS_BASIC,
                role=Role.SYSTEM_BOOT,
                size="512M",
                filesystem="vfat",
            ),
        ],
    )
    assert configured_pack_service._select_metadata_partition() == "volume/pc/efi"


def test_select_metadata_partition_prefers_hybrid_efi_type(
    configured_pack_service: ImagecraftPackService,
):
    project = cast(Project, configured_pack_service._services.get("project").get())
    volume = cast(object, project.volumes["pc"])
    object.__setattr__(
        volume,
        "structure",
        [
            HybridStructureItem(
                name="seed",
                structure_type="0C,C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
                role=Role.SYSTEM_SEED,
                size="256M",
                filesystem="vfat",
            ),
            HybridStructureItem(
                name="rootfs",
                structure_type="83,0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                role=Role.SYSTEM_DATA,
                size="1G",
                filesystem="ext4",
            ),
        ],
    )

    assert configured_pack_service._select_metadata_partition() == "volume/pc/seed"


def test_select_metadata_partition_falls_back_to_system_boot(
    configured_pack_service: ImagecraftPackService,
):
    project = cast(Project, configured_pack_service._services.get("project").get())
    volume = cast(object, project.volumes["pc"])
    object.__setattr__(
        volume,
        "structure",
        [
            GPTStructureItem(
                name="data",
                structure_type=GptType.LINUX_DATA,
                role=Role.SYSTEM_DATA,
                size="1G",
                filesystem="ext4",
            ),
            GPTStructureItem(
                name="boot",
                structure_type=GptType.WINDOWS_BASIC,
                role=Role.SYSTEM_BOOT,
                size="512M",
                filesystem="vfat",
            ),
        ],
    )
    assert configured_pack_service._select_metadata_partition() == "volume/pc/boot"


def test_select_metadata_partition_falls_back_to_first_partition(
    configured_pack_service: ImagecraftPackService,
):
    project = cast(Project, configured_pack_service._services.get("project").get())
    volume = cast(object, project.volumes["pc"])
    object.__setattr__(
        volume,
        "structure",
        [
            GPTStructureItem(
                name="first",
                structure_type=GptType.LINUX_DATA,
                role=Role.SYSTEM_DATA,
                size="1G",
                filesystem="ext4",
            ),
            GPTStructureItem(
                name="second",
                structure_type=GptType.LINUX_DATA,
                role=Role.SYSTEM_DATA,
                size="1G",
                filesystem="ext4",
            ),
        ],
    )
    assert configured_pack_service._select_metadata_partition() == "volume/pc/first"


def test_select_metadata_partition_raises_error_when_no_partitions(
    configured_pack_service: ImagecraftPackService,
):
    project = cast(Project, configured_pack_service._services.get("project").get())
    # Bypass Pydantic validation to simulate an empty structure
    object.__setattr__(project.volumes["pc"], "structure", [])

    with pytest.raises(
        CraftError, match="has no partitions; cannot inject image metadata"
    ):
        configured_pack_service._select_metadata_partition()


def test_assert_no_metadata_conflict_rejects_user_file(
    configured_pack_service: ImagecraftPackService,
):
    metadata_path = _metadata_path(configured_pack_service, "volume/pc/efi", stage=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text("name: custom\n")

    with pytest.raises(CraftError, match="conflicts with generated image metadata"):
        configured_pack_service._assert_no_metadata_conflict("volume/pc/efi")


def test_assert_no_metadata_conflict_rejects_prime_file(
    configured_pack_service: ImagecraftPackService,
):
    """Metadata created in prime (e.g. by override-prime) is a user conflict."""
    metadata_path = _metadata_path(configured_pack_service, "volume/pc/efi")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text("name: stale\n")

    with pytest.raises(CraftError, match="conflicts with generated image metadata"):
        configured_pack_service._assert_no_metadata_conflict("volume/pc/efi")


def test_remove_stale_metadata_files_removes_matching_current_metadata(
    configured_pack_service: ImagecraftPackService,
):
    metadata_path = _metadata_path(configured_pack_service, "volume/pc/efi")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_yaml = configured_pack_service._render_image_metadata()
    metadata_path.write_text(metadata_yaml)

    configured_pack_service._remove_stale_metadata_files("volume/pc/efi", metadata_yaml)

    assert metadata_path.exists() is False


def test_remove_stale_metadata_files_removes_matching_persisted_metadata(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
):
    artifact_path = tmp_path / "dest" / "pc.img"
    configured_pack_service.write_artifacts_state({None: artifact_path})

    metadata_path = _metadata_path(configured_pack_service, "volume/pc/efi")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(configured_pack_service._render_image_metadata())

    project = cast(Project, configured_pack_service._services.get("project").get())
    structure = cast(list[GPTStructureItem], project.volumes["pc"].structure)
    object.__setattr__(structure[0], "structure_type", GptType.WINDOWS_BASIC)
    object.__setattr__(structure[0], "role", Role.SYSTEM_DATA)
    object.__setattr__(structure[1], "role", Role.SYSTEM_BOOT)
    new_metadata_partition = configured_pack_service._select_metadata_partition()
    new_metadata_yaml = configured_pack_service._render_image_metadata()

    configured_pack_service._remove_stale_metadata_files(
        new_metadata_partition, new_metadata_yaml
    )

    assert metadata_path.exists() is False


def test_remove_stale_metadata_files_preserves_prime_only_user_metadata(
    configured_pack_service: ImagecraftPackService,
):
    metadata_path = _metadata_path(configured_pack_service, "volume/pc/efi")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text("name: custom\n")

    configured_pack_service._remove_stale_metadata_files(
        "volume/pc/efi", configured_pack_service._render_image_metadata()
    )

    assert metadata_path.read_text() == "name: custom\n"


def test_inject_metadata_file_sets_read_only_permissions_on_ext_filesystems(
    configured_pack_service: ImagecraftPackService,
):
    project = cast(Project, configured_pack_service._services.get("project").get())
    volume = cast(object, project.volumes["pc"])
    object.__setattr__(
        volume,
        "structure",
        [
            GPTStructureItem(
                name="rootfs",
                structure_type=GptType.LINUX_DATA,
                role=Role.SYSTEM_DATA,
                size="1G",
                filesystem="ext4",
            )
        ],
    )

    metadata_path = configured_pack_service._inject_metadata_file(
        "volume/pc/rootfs", configured_pack_service._render_image_metadata()
    )

    assert metadata_path.parent.stat().st_mode & 0o777 == 0o555
    assert metadata_path.stat().st_mode & 0o777 == 0o444


def test_inject_metadata_file_leaves_default_permissions_on_fat_filesystems(
    configured_pack_service: ImagecraftPackService,
):
    metadata_path = configured_pack_service._inject_metadata_file(
        "volume/pc/efi", configured_pack_service._render_image_metadata()
    )

    assert metadata_path.parent.stat().st_mode & 0o777 != 0o555
    assert metadata_path.stat().st_mode & 0o777 != 0o444


def test_pack_artifacts_removes_read_only_metadata_after_success(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    project = cast(Project, configured_pack_service._services.get("project").get())
    volume = cast(object, project.volumes["pc"])
    object.__setattr__(
        volume,
        "structure",
        [
            GPTStructureItem(
                name="rootfs",
                structure_type=GptType.LINUX_DATA,
                role=Role.SYSTEM_DATA,
                size="1G",
                filesystem="ext4",
            )
        ],
    )

    artifact_path = tmp_path / "dest" / "pc.img"
    _mock_pack_dependencies(mock_image_service, artifact_path, mocker)

    configured_pack_service.pack_artifacts()

    metadata_path = _metadata_path(configured_pack_service, "volume/pc/rootfs")
    assert metadata_path.exists() is False
    assert metadata_path.parent.exists() is False


def test_pack_artifacts_writes_metadata_before_partition_population(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    artifact_path = tmp_path / "dest" / "pc.img"
    mock_diskutil = _mock_pack_dependencies(mock_image_service, artifact_path, mocker)
    metadata_path = _metadata_path(configured_pack_service, "volume/pc/efi")
    populated: dict[Path, str] = {}

    def format_device(*, content_dir: Path, **kwargs: Any) -> None:
        if metadata_path.is_relative_to(content_dir):
            populated[content_dir] = metadata_path.read_text()

    mock_diskutil.format_device.side_effect = format_device

    configured_pack_service.pack_artifacts()

    assert populated == {
        metadata_path.parent.parent: configured_pack_service._render_image_metadata()
    }
    # The generated file is only needed while partitions are populated.
    assert metadata_path.exists() is False


def test_pack_artifacts_replaces_stale_prime_metadata(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    """Metadata left in prime by an interrupted pack doesn't block packing."""
    artifact_path = tmp_path / "dest" / "pc.img"
    _mock_pack_dependencies(mock_image_service, artifact_path, mocker)
    stale_path = _metadata_path(configured_pack_service, "volume/pc/efi")
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text(configured_pack_service._render_image_metadata())

    assert configured_pack_service.pack_artifacts() == {None: True}

    assert stale_path.exists() is False


def test_pack_artifacts_rejects_staged_metadata(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    artifact_path = tmp_path / "dest" / "pc.img"
    mock_diskutil = _mock_pack_dependencies(mock_image_service, artifact_path, mocker)
    staged_path = _metadata_path(configured_pack_service, "volume/pc/efi", stage=True)
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    staged_path.write_text("name: custom\n")

    with pytest.raises(CraftError, match="conflicts with generated image metadata"):
        configured_pack_service.pack_artifacts()

    mock_diskutil.format_device.assert_not_called()
    assert staged_path.exists()


def test_pack_artifacts_cleans_metadata_when_injection_fails(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    artifact_path = tmp_path / "dest" / "pc.img"
    _mock_pack_dependencies(mock_image_service, artifact_path, mocker)
    mocker.patch.object(
        configured_pack_service,
        "_apply_metadata_permissions",
        side_effect=OSError("chmod failed"),
    )

    with pytest.raises(OSError, match="chmod failed"):
        configured_pack_service.pack_artifacts()

    assert _metadata_path(configured_pack_service, "volume/pc/efi").exists() is False


def test_pack_artifacts_keeps_original_error_when_cleanup_fails(
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    mocker.patch.object(
        mock_image_service, "create_images", side_effect=RuntimeError("boom")
    )
    mocker.patch.object(
        configured_pack_service,
        "_remove_metadata_file",
        side_effect=OSError("unlink failed"),
    )

    with pytest.raises(RuntimeError, match="boom"):
        configured_pack_service.pack_artifacts()


def test_pack_artifacts_rejects_prime_only_metadata(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    artifact_path = tmp_path / "dest" / "pc.img"
    mock_diskutil = _mock_pack_dependencies(mock_image_service, artifact_path, mocker)
    prime_path = _metadata_path(configured_pack_service, "volume/pc/efi")
    prime_path.parent.mkdir(parents=True, exist_ok=True)
    prime_path.write_text("name: custom\n")

    with pytest.raises(CraftError, match="conflicts with generated image metadata"):
        configured_pack_service.pack_artifacts()

    mock_diskutil.format_device.assert_not_called()
    assert prime_path.read_text() == "name: custom\n"


def test_app_needs_repack_when_metadata_content_changes(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
    rootfs_prime_dir: Path,
):
    (rootfs_prime_dir / "usr/sbin").mkdir(parents=True)
    (rootfs_prime_dir / "usr/sbin/grub-install").write_text("")
    artifact_path = tmp_path / "dest" / "pc.img"
    configured_pack_service.write_artifacts_state({None: artifact_path})

    project = configured_pack_service._services.get("project").get()
    project.summary = "updated summary"

    assert configured_pack_service._app_needs_repack() is True


def test_app_needs_repack_when_metadata_placement_changes(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
    rootfs_prime_dir: Path,
):
    (rootfs_prime_dir / "usr/sbin").mkdir(parents=True)
    (rootfs_prime_dir / "usr/sbin/grub-install").write_text("")
    artifact_path = tmp_path / "dest" / "pc.img"
    configured_pack_service.write_artifacts_state({None: artifact_path})

    project = cast(Project, configured_pack_service._services.get("project").get())
    structure = cast(list[GPTStructureItem], project.volumes["pc"].structure)
    object.__setattr__(structure[0], "structure_type", GptType.WINDOWS_BASIC)
    object.__setattr__(structure[0], "role", Role.SYSTEM_DATA)
    object.__setattr__(structure[1], "role", Role.SYSTEM_BOOT)

    assert configured_pack_service._app_needs_repack() is True


def test_pack_artifacts(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    artifact_path = tmp_path / "dest" / "pc.img"
    artifact_dir = artifact_path.parent

    mocker.patch.object(mock_image_service, "create_images")
    mocker.patch.object(mock_image_service, "attach_images")
    mock_verify = mocker.patch.object(mock_image_service, "verify_images")
    mock_detach = mocker.patch.object(mock_image_service, "detach_images")
    mock_finalize = mocker.patch.object(
        mock_image_service,
        "finalize_images",
        return_value={"pc": artifact_path},
    )
    mock_diskutil = mocker.patch("imagecraft.services.pack.diskutil", autospec=True)
    mock_grubutil = mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mock_image_cls = mocker.patch("imagecraft.services.pack.Image", autospec=True)

    result = configured_pack_service.pack_artifacts()

    assert result == {None: True}
    assert mock_diskutil.format_device.call_count == 2
    mock_verify.assert_called_once()
    mock_detach.assert_called_once()
    mock_finalize.assert_called_once_with(artifact_dir)
    mock_grubutil.setup_grub.assert_called_once()
    mock_image_cls.assert_called_once()
    mock_diskutil.create_zero_image.assert_not_called()
    mock_diskutil.inject_partition_into_image.assert_not_called()
    mock_diskutil.format_populate_partition.assert_not_called()


def test_pack_artifacts_detaches_on_error(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    mocker.patch.object(mock_image_service, "create_images")
    mocker.patch.object(mock_image_service, "attach_images")
    mock_detach = mocker.patch.object(mock_image_service, "detach_images")
    mocker.patch.object(mock_image_service, "verify_images")
    mocker.patch.object(mock_image_service, "finalize_images")
    mocker.patch(
        "imagecraft.services.pack.diskutil.format_device",
        side_effect=RuntimeError("disk full"),
    )
    mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mocker.patch("imagecraft.services.pack.Image", autospec=True)

    with pytest.raises(RuntimeError, match="disk full"):
        configured_pack_service.pack_artifacts()

    mock_detach.assert_called_once()


def test_pack_artifacts_cleans_generated_metadata_on_error(
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    metadata_path = _metadata_path(configured_pack_service, "volume/pc/efi")

    mocker.patch.object(mock_image_service, "create_images")
    mocker.patch.object(mock_image_service, "attach_images")
    mocker.patch.object(mock_image_service, "detach_images")
    mocker.patch.object(mock_image_service, "verify_images")
    mocker.patch.object(
        mock_image_service,
        "finalize_images",
        side_effect=RuntimeError("finalize failed"),
    )
    mocker.patch("imagecraft.services.pack.diskutil", autospec=True)
    mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mocker.patch("imagecraft.services.pack.Image", autospec=True)

    with pytest.raises(RuntimeError, match="finalize failed"):
        configured_pack_service.pack_artifacts()

    assert metadata_path.exists() is False


def test_pack_artifacts_removes_stale_artifact_before_repacking(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    artifact_path = tmp_path / "dest" / "pc.img"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("stale image")

    mocker.patch.object(mock_image_service, "create_images")
    mocker.patch.object(mock_image_service, "attach_images")
    mocker.patch.object(mock_image_service, "verify_images")
    mocker.patch.object(mock_image_service, "detach_images")

    def finalize_images(dest: Path) -> dict[str, Path]:
        assert artifact_path.exists() is False
        artifact_path.write_text("fresh image")
        return {"pc": artifact_path}

    mock_finalize = mocker.patch.object(
        mock_image_service,
        "finalize_images",
        side_effect=finalize_images,
    )
    mocker.patch("imagecraft.services.pack.diskutil", autospec=True)
    mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mocker.patch("imagecraft.services.pack.Image", autospec=True)

    configured_pack_service.pack_artifacts()

    mock_finalize.assert_called_once_with(artifact_path.parent)
    assert artifact_path.read_text() == "fresh image"


def test_pack_artifacts_removes_finalized_artifact_on_failure(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    mocker,
):
    artifact_path = tmp_path / "dest" / "pc.img"

    mocker.patch.object(mock_image_service, "create_images")
    mocker.patch.object(mock_image_service, "attach_images")
    mocker.patch.object(mock_image_service, "verify_images")
    mocker.patch.object(mock_image_service, "detach_images")

    def finalize_images(dest: Path) -> dict[str, Path]:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text("partially finalized image")
        return {"pc": artifact_path}

    mocker.patch.object(
        mock_image_service,
        "finalize_images",
        side_effect=finalize_images,
    )
    mocker.patch("imagecraft.services.pack.diskutil", autospec=True)
    mocker.patch(
        "imagecraft.services.pack.grubutil.setup_grub",
        side_effect=GRUBInstallError("grub failed"),
    )
    mocker.patch("imagecraft.services.pack.Image", autospec=True)

    with pytest.raises(GRUBInstallError, match="grub failed"):
        configured_pack_service.pack_artifacts()

    assert artifact_path.exists() is False


def test_pack_artifacts_cleans_temp_images_when_skip_repack(
    tmp_path: Path,
    configured_pack_service: ImagecraftPackService,
    mock_image_service: ImageService,
    rootfs_prime_dir: Path,
    mocker,
):
    """A skipped pack should clean up temp images created during lifecycle setup."""
    (rootfs_prime_dir / "usr/sbin").mkdir(parents=True)
    (rootfs_prime_dir / "usr/sbin/grub-install").write_text("")
    artifact_path = tmp_path / "dest" / "pc.img"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text("packed image")
    configured_pack_service.write_artifacts_state({None: artifact_path})
    temp_image_path = tmp_path / ".pc.img.tmp"
    temp_image_path.write_text("temp image")
    mock_image_service._images = {"pc": temp_image_path}
    mocker.patch("imagecraft.services.image.run")

    cleanup = mocker.spy(mock_image_service, "cleanup_temporary_images")
    pack = mocker.patch.object(configured_pack_service, "_pack")

    result = configured_pack_service.pack_artifacts()

    assert result == {None: False}
    cleanup.assert_called_once_with()
    pack.assert_not_called()
    assert temp_image_path.exists() is False


def test_write_artifacts_state_overwrites_existing_value(
    configured_pack_service: ImagecraftPackService,
    default_factory: ServiceFactory,
    tmp_path: Path,
):
    artifact_path = tmp_path / "dest" / "pc.img"
    state_service = default_factory.get("state")
    platform = configured_pack_service._build_info.platform

    configured_pack_service.write_artifacts_state({None: artifact_path})
    configured_pack_service.write_artifacts_state({None: artifact_path})

    assert state_service.get("artifacts", platform) == [
        {"name": None, "path": str(artifact_path)}
    ]


def test_write_artifacts_state_persists_pack_fingerprint(
    configured_pack_service: ImagecraftPackService,
    default_factory: ServiceFactory,
    tmp_path: Path,
    rootfs_prime_dir: Path,
):
    """write_artifacts_state also records the pack-input fingerprint on disk."""
    (rootfs_prime_dir / "usr/sbin").mkdir(parents=True)
    (rootfs_prime_dir / "usr/sbin/grub-install").write_text("")
    artifact_path = tmp_path / "dest" / "pc.img"
    platform = configured_pack_service._build_info.platform

    configured_pack_service.write_artifacts_state({None: artifact_path})

    persisted_state = yaml.safe_load(
        configured_pack_service._pack_inputs_state_path().read_text()
    )
    assert (
        persisted_state["pack_inputs"][platform]
        == configured_pack_service._current_pack_fingerprint()
    )


def test_app_needs_repack_when_no_fingerprint_stored(
    configured_pack_service: ImagecraftPackService,
):
    """A repack is required when there is no stored fingerprint to compare against."""
    assert configured_pack_service._app_needs_repack() is True


@pytest.mark.parametrize(
    "bad_contents",
    [
        pytest.param("not-yaml: [", id="invalid-yaml"),
        pytest.param("42", id="non-dict-root"),
        pytest.param("pack_inputs: 42", id="non-dict-pack-inputs"),
        pytest.param(b"\xff\xfe\xfd", id="invalid-utf8"),
    ],
)
def test_app_needs_repack_when_persisted_state_is_corrupt(
    configured_pack_service: ImagecraftPackService,
    bad_contents: str | bytes,
):
    """A corrupt or non-dict pack state file conservatively forces a repack."""
    state_path = configured_pack_service._pack_inputs_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(bad_contents, bytes):
        state_path.write_bytes(bad_contents)
    else:
        state_path.write_text(bad_contents)

    assert configured_pack_service._app_needs_repack() is True


def test_app_needs_repack_when_fingerprint_unchanged(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
    rootfs_prime_dir: Path,
):
    """No repack is required when the pack-input fingerprint hasn't changed."""
    (rootfs_prime_dir / "usr/sbin").mkdir(parents=True)
    (rootfs_prime_dir / "usr/sbin/grub-install").write_text("")
    artifact_path = tmp_path / "dest" / "pc.img"
    configured_pack_service.write_artifacts_state({None: artifact_path})

    assert configured_pack_service._app_needs_repack() is False


def test_app_needs_repack_reads_persisted_fingerprint_across_service_instances(
    configured_pack_service: ImagecraftPackService,
    default_factory: ServiceFactory,
    tmp_path: Path,
    rootfs_prime_dir: Path,
):
    """A fresh pack service can reuse the persisted fingerprint from work state."""
    (rootfs_prime_dir / "usr/sbin").mkdir(parents=True)
    (rootfs_prime_dir / "usr/sbin/grub-install").write_text("")
    artifact_path = tmp_path / "dest" / "pc.img"
    configured_pack_service.write_artifacts_state({None: artifact_path})

    fresh_pack_service = ImagecraftPackService(
        app=default_factory.app,
        services=default_factory,
    )
    fresh_pack_service.set_output_dir(tmp_path / "dest")
    default_factory.get("project").get()
    fresh_pack_service.update_project()

    assert fresh_pack_service._app_needs_repack() is False


def test_app_needs_repack_when_image_grub_install_availability_changes(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
    rootfs_prime_dir: Path,
):
    """A repack is required when image grub-install availability changes.

    This changes GRUB installation behavior without any project file edit or
    lifecycle rerun, so it can only be caught by the fingerprint check.
    """
    (rootfs_prime_dir / "usr/sbin").mkdir(parents=True)
    grub_install_path = rootfs_prime_dir / "usr/sbin/grub-install"
    grub_install_path.write_text("")
    artifact_path = tmp_path / "dest" / "pc.img"
    configured_pack_service.write_artifacts_state({None: artifact_path})

    grub_install_path.unlink()

    assert configured_pack_service._app_needs_repack() is True


def test_app_needs_repack_when_filesystem_mount_changes(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
    rootfs_prime_dir: Path,
    default_factory: ServiceFactory,
):
    """A repack is required when the default filesystem-mount config changes.

    This is consumed only at pack time for GRUB setup, so craft-parts never
    sees it and the lifecycle won't rerun on its own when it changes.
    """
    (rootfs_prime_dir / "usr/sbin").mkdir(parents=True)
    (rootfs_prime_dir / "usr/sbin/grub-install").write_text("")
    artifact_path = tmp_path / "dest" / "pc.img"
    configured_pack_service.write_artifacts_state({None: artifact_path})

    project_info = default_factory.get("lifecycle").project_info
    project_info._filesystem_mounts = FilesystemMounts.unmarshal(
        {
            "default": [
                {"mount": "/", "device": "(volume/pc/rootfs)"},
                {"mount": "/boot/", "device": "(volume/pc/efi)"},
            ]
        }
    )

    assert configured_pack_service._app_needs_repack() is True
