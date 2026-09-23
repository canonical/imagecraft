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
from typing import cast

import pytest
import yaml
from craft_application import ServiceFactory
from craft_parts import ProjectDirs, ProjectInfo, ProjectVar, ProjectVarInfo
from craft_parts.filesystem_mounts import FilesystemMount, FilesystemMounts
from imagecraft.services.image import ImageService
from imagecraft.services.pack import ImagecraftPackService


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


def test_get_artifacts(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
):
    assert configured_pack_service.get_artifacts() == {
        None: tmp_path / "dest" / "pc.img"
    }


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
    mocker,
):
    """write_artifacts_state also records the pack-input fingerprint on disk."""
    mocker.patch(
        "imagecraft.services.pack.shutil.which", return_value="/sbin/grub-install"
    )
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
    ],
)
def test_app_needs_repack_when_persisted_state_is_corrupt(
    configured_pack_service: ImagecraftPackService,
    bad_contents: str,
):
    """A corrupt or non-dict pack state file conservatively forces a repack."""
    state_path = configured_pack_service._pack_inputs_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(bad_contents)

    assert configured_pack_service._app_needs_repack() is True


def test_app_needs_repack_when_fingerprint_unchanged(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
    mocker,
):
    """No repack is required when the pack-input fingerprint hasn't changed."""
    mocker.patch(
        "imagecraft.services.pack.shutil.which", return_value="/sbin/grub-install"
    )
    artifact_path = tmp_path / "dest" / "pc.img"
    configured_pack_service.write_artifacts_state({None: artifact_path})

    assert configured_pack_service._app_needs_repack() is False


def test_app_needs_repack_reads_persisted_fingerprint_across_service_instances(
    configured_pack_service: ImagecraftPackService,
    default_factory: ServiceFactory,
    tmp_path: Path,
    mocker,
):
    """A fresh pack service can reuse the persisted fingerprint from work state."""
    mocker.patch(
        "imagecraft.services.pack.shutil.which", return_value="/sbin/grub-install"
    )
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


def test_app_needs_repack_when_grub_install_availability_changes(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
    mocker,
):
    """A repack is required when grub-install availability changes.

    This changes GRUB installation behavior without any project file edit or
    lifecycle rerun, so it can only be caught by the fingerprint check.
    """
    mocker.patch(
        "imagecraft.services.pack.shutil.which", return_value="/sbin/grub-install"
    )
    artifact_path = tmp_path / "dest" / "pc.img"
    configured_pack_service.write_artifacts_state({None: artifact_path})

    mocker.patch("imagecraft.services.pack.shutil.which", return_value=None)

    assert configured_pack_service._app_needs_repack() is True


def test_app_needs_repack_when_filesystem_mount_changes(
    configured_pack_service: ImagecraftPackService,
    tmp_path: Path,
    mocker,
    default_factory: ServiceFactory,
):
    """A repack is required when the default filesystem-mount config changes.

    This is consumed only at pack time for GRUB setup, so craft-parts never
    sees it and the lifecycle won't rerun on its own when it changes.
    """
    mocker.patch(
        "imagecraft.services.pack.shutil.which", return_value="/sbin/grub-install"
    )
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
