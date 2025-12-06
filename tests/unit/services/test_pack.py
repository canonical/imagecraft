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


from craft_application import ServiceFactory
from imagecraft.services.pack import ImagecraftPackService


def test_pack(
    tmp_path,
    enable_features,
    default_factory: ServiceFactory,
    pack_service: ImagecraftPackService,
    mocker,
):
    from craft_parts import ProjectDirs, ProjectInfo

    prime_dir = tmp_path / "prime"
    dest_path = tmp_path / "dest"
    work_dir = tmp_path / "work"

    mock_diskutil = mocker.patch("imagecraft.services.pack.diskutil", autospec=True)
    mock_gptutil = mocker.patch("imagecraft.services.pack.gptutil", autospec=True)
    mock_grubutil = mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mock_image = mocker.patch("imagecraft.services.pack.Image", autospec=True)
    
    # Create a real ProjectInfo object to avoid apt backend initialization
    partitions = ["volume/pc/rootfs", "volume/pc/efi"]
    project_dirs = ProjectDirs(work_dir=work_dir, partitions=partitions)
    project_info = ProjectInfo(
        application_name="imagecraft",
        cache_dir=tmp_path / "cache",
        arch="amd64",
        base="bare",
        parallel_build_count=1,
        project_dirs=project_dirs,
        partitions=partitions,
        filesystem_mounts={"default": []},
    )
    
    # Mock the lifecycle service with real ProjectInfo
    mock_lifecycle = mocker.MagicMock()
    mock_lifecycle.project_info = project_info
    
    # Override get_prime_dir to return our test directory
    mocker.patch.object(project_dirs, "get_prime_dir", return_value=prime_dir)
    
    # Patch the factory to return mock_lifecycle for "lifecycle" calls
    original_get = default_factory.get
    def mock_get(service_name):
        if service_name == "lifecycle":
            return mock_lifecycle
        return original_get(service_name)
    mocker.patch.object(default_factory, "get", side_effect=mock_get)

    assert pack_service.pack(prime_dir=prime_dir, dest=dest_path) == [
        dest_path / "pc.img"
    ]

    assert mock_gptutil.create_empty_gpt_image.called
    assert mock_diskutil.inject_partition_into_image.called
    assert mock_grubutil.setup_grub.called
    assert mock_image.called
