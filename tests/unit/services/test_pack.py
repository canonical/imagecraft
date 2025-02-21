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
from unittest.mock import mock_open, patch


def test_pack(pack_service, default_factory, mocker):
    prime = "prime"
    prime_dir = Path(prime)
    dest_path = Path()

    # Remove once we can organize from overlays into partitions and delete the test data
    # creation in pack.py.
    opener = mock_open()

    def mocked_open(self, *args, **kwargs):
        if self.name == "testo.txt":
            return opener(self, *args, **kwargs)
        print("open", self, args, kwargs)
        return open(*args)  # noqa: PTH123

    with (
        patch("imagecraft.services.pack.diskutil", autospec=True) as diskutil,
        patch("imagecraft.services.pack.gptutil", autospec=True) as gptutil,
        patch.object(Path, "open", mocked_open),
    ):
        pack_service.setup()
        assert pack_service.pack(prime_dir, dest=dest_path) == [Path("pc.img")]

        assert gptutil.create_gpt_layout.called
        assert diskutil.inject_partition_into_image.called
