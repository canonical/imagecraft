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
    prime_dir = tmp_path / "prime"
    dest_path = tmp_path / "dest"

    mock_diskutil = mocker.patch("imagecraft.services.pack.diskutil", autospec=True)
    mock_gptutil = mocker.patch("imagecraft.services.pack.gptutil", autospec=True)
    mock_grubutil = mocker.patch("imagecraft.services.pack.grubutil", autospec=True)
    mock_image = mocker.patch("imagecraft.services.pack.Image", autospec=True)
    
    # Mock the lifecycle service to avoid apt backend initialization
    mock_lifecycle = mocker.MagicMock()
    mock_lifecycle.project_info.dirs.get_prime_dir.return_value = prime_dir
    mock_lifecycle.project_info.dirs.work_dir = tmp_path / "work"
    mock_lifecycle.project_info.default_filesystem_mount = {"default": []}
    mock_lifecycle.project_info.target_arch = "amd64"
    
    # Patch the services.get method to return mock_lifecycle for "lifecycle" calls
    original_get = pack_service._services.get
    def mock_get(service_name):
        if service_name == "lifecycle":
            return mock_lifecycle
        return original_get(service_name)
    mocker.patch.object(pack_service._services, "get", side_effect=mock_get)

    assert pack_service.pack(prime_dir=prime_dir, dest=dest_path) == [
        dest_path / "pc.img"
    ]

    assert mock_gptutil.create_empty_gpt_image.called
    assert mock_diskutil.inject_partition_into_image.called
    assert mock_grubutil.setup_grub.called
    assert mock_image.called
