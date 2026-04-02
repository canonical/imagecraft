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

from unittest.mock import ANY, call

import pytest
from craft_cli import CraftError
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
def device(tmp_path):
    """A pre-existing block device (simulated as a file)."""
    device_path = tmp_path / "loop0p1"
    device_path.touch()
    return device_path


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
        content,
        "-L",
        "test",
        imagepath,
    ]


@pytest.fixture
def mke2fs_device(request, content, device):
    return [
        "mke2fs",
        "-t",
        "ext3",
        "-d",
        content,
        "-L",
        "test",
        device,
    ]


@pytest.fixture
def mkfsfat16(request, content, imagepath):
    return [
        "mkfs.fat",
        "-F",
        "16",
        "-n",
        "test",
        imagepath,
    ]


@pytest.fixture
def mkfsfat16_device(request, content, device):
    return [
        "mkfs.fat",
        "-F",
        "16",
        "-n",
        "test",
        device,
    ]


@pytest.fixture
def mcopy(request, content, imagepath):
    return [
        "bash",
        "-c",
        f"mcopy -n -o -s -i{str(imagepath)} {str(content)}/* ::",
    ]


@pytest.fixture
def mcopy_device(request, content, device):
    return [
        "bash",
        "-c",
        f"mcopy -n -o -s -i{str(device)} {str(content)}/* ::",
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
        "imagecraft.pack.diskutil.run",
        autospec=True,
    )
    diskutil.format_populate_partition(
        fstype=fstype,
        content_dir=content,
        partitionpath=imagepath,
        label=label,
    )

    create_zero_image.assert_not_called()

    calls = [call(e[0], *e[1:], stdout=ANY, stderr=ANY) for e in expected_values]
    mocked_run.assert_has_calls(calls)


# ── format_device ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("fstype", "label", "expected_fixtures"),
    [
        (FileSystem.EXT3, "test", ["mke2fs_device"]),
        (FileSystem.FAT16, "test", ["mkfsfat16_device", "mcopy_device"]),
    ],
)
def test_format_device(
    mocker, request, content, device, fstype, label, expected_fixtures
):
    """format_device formats a pre-existing device without creating it."""
    create_zero_image = mocker.patch(
        "imagecraft.pack.diskutil.create_zero_image", autospec=True
    )
    mocked_run = mocker.patch(
        "imagecraft.pack.diskutil.run",
        autospec=True,
    )

    diskutil.format_device(
        device_path=device,
        fstype=fstype,
        label=label,
        content_dir=content,
    )

    create_zero_image.assert_not_called()
    expected_calls = [
        call(f[0], *f[1:], stdout=ANY, stderr=ANY)
        for f in [request.getfixturevalue(f) for f in expected_fixtures]
    ]
    mocked_run.assert_has_calls(expected_calls)


def test_format_device_missing_device(tmp_path):
    """format_device raises CraftError when the device does not exist."""
    missing = tmp_path / "nonexistent"
    with pytest.raises(CraftError, match="does not exist"):
        diskutil.format_device(
            device_path=missing,
            fstype=FileSystem.EXT4,
        )


def test_format_device_no_content_dir(mocker, device):
    """format_device with no content_dir omits -d from mke2fs."""
    mocked_run = mocker.patch(
        "imagecraft.pack.diskutil.run",
        autospec=True,
    )

    diskutil.format_device(
        device_path=device,
        fstype=FileSystem.EXT4,
        label="boot",
    )

    args = mocked_run.call_args[0]
    assert "-d" not in args


def test_format_device_fat_no_content(mocker, device):
    """format_device for FAT with empty content_dir skips mcopy."""
    mocked_run = mocker.patch(
        "imagecraft.pack.diskutil.run",
        autospec=True,
    )
    empty_content = device.parent / "empty"
    empty_content.mkdir()

    diskutil.format_device(
        device_path=device,
        fstype=FileSystem.FAT16,
        content_dir=empty_content,
    )

    assert mocked_run.call_count == 1
    assert mocked_run.call_args[0][0] == "mkfs.fat"
