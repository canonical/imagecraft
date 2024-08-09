# Copyright 2023 Canonical Ltd.
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

from imagecraft.services import pack
from imagecraft.services.pack import pathlib, shutil


def test_pack(pack_service, default_factory, mocker):
    mock_inner_ubuntu_image_pack = mocker.patch.object(pack, "ubuntu_image_pack")
    mock_inner_list_image_paths = mocker.patch.object(
        pack,
        "list_image_paths",
        return_value=True,
    )
    mock_inner_list_image_paths.return_value = [
        pathlib.Path("pc.img"),
        pathlib.Path("pc2.img"),
    ]

    mocker.patch.object(pathlib.Path, "mkdir", return_value=True)
    mocker.patch.object(shutil, "rmtree")

    prime = "prime"
    prime_dir = Path(prime)
    dest_path = Path()

    assert pack_service.pack(prime_dir, dest=dest_path) == [
        pathlib.Path("pc.img"),
        pathlib.Path("pc2.img"),
    ]

    # Check that ubuntu_image_pack() was called with the correct
    # parameters.
    mock_inner_ubuntu_image_pack.assert_called_once_with(
        "prime/rootfs/",
        "prime/gadget/",
        str(dest_path),
        "prime/workdir/",
    )
