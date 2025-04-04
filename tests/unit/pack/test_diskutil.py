# Copyright 2025 Canonical Ltd.
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

from unittest.mock import call

import pytest
from imagecraft.models import FileSystem
from imagecraft.pack import diskutil


@pytest.fixture
def content(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    a_file = content_dir / "a"
    a_file.touch()
    return content_dir


@pytest.fixture
def imagepath(tmp_path):
    imagepath = tmp_path / "image.img"
    imagepath.touch()
    return imagepath


@pytest.fixture
def mke2fs(request, content, imagepath):
    return [
        "mke2fs",
        "-t",
        "ext3",
        "-d",
        f"{request.getfixturevalue('content')}",
        "-L",
        "test",
        f"{request.getfixturevalue('imagepath')}",
    ]


@pytest.fixture
def mkfsfat16(request, content, imagepath):
    return [
        "mkfs.fat",
        "-F",
        "16",
        "-n",
        "test",
        f"{request.getfixturevalue('imagepath')}",
    ]


@pytest.fixture
def mcopy(request, content, imagepath):
    return [
        "bash",
        "-c",
        f"mcopy -n -o -s -i{request.getfixturevalue('imagepath')} {request.getfixturevalue('content')}/* ::",
    ]


@pytest.mark.parametrize(
    ("fstype", "label", "expected"),
    [
        (
            FileSystem.EXT3,
            "test",
            ["mke2fs"],
        ),
        (
            FileSystem.FAT16,
            "test",
            ["mkfsfat16", "mcopy"],
        ),
    ],
)
def test_format_populate_partition(
    mocker, request, content, imagepath, fstype, label, expected
):
    expected_values = [request.getfixturevalue(v) for v in expected]
    create_zero_image = mocker.patch(
        "imagecraft.pack.diskutil.create_zero_image", autospec=True
    )
    mocked_run = mocker.patch(
        "imagecraft.pack.gptutil.subprocess.run",
        autospec=True,
    )
    sector_size = 512
    disk_size = 512000000
    diskutil.format_populate_partition(
        fstype=fstype,
        content_dir=content,
        partitionpath=imagepath,
        disk_size=diskutil.DiskSize(bytesize=disk_size, sector_size=sector_size),
        label=label,
    )

    create_zero_image.assert_called_with(
        imagepath=imagepath,
        disk_size=diskutil.DiskSize(bytesize=disk_size, sector_size=sector_size),
    )

    calls = [call(e, text=True, check=True, stdout=-1) for e in expected_values]
    mocked_run.assert_has_calls(calls)
