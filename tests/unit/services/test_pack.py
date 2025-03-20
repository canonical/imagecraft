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

    diskutil = mocker.patch("imagecraft.services.pack.diskutil", autospec=True)
    gptutil = mocker.patch("imagecraft.services.pack.gptutil", autospec=True)

    assert pack_service.pack(prime_dir=prime_dir, dest=dest_path) == [
        dest_path / "pc.img"
    ]

    assert gptutil.create_empty_gpt_image.called
    assert diskutil.inject_partition_into_image.called
