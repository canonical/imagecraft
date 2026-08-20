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

from subprocess import CompletedProcess
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


def test_format_populate_partition_ext_with_offset(mocker, content, imagepath):
    """An ext partition with geometry is written in place at its offset."""
    mocked_run = mocker.patch("imagecraft.pack.diskutil.run", autospec=True)
    geometry = diskutil.PartitionGeometry(
        sector_offset=2048, sector_count=32768, sector_size=512
    )

    diskutil.format_populate_partition(
        fstype=FileSystem.EXT4,
        content_dir=content,
        partitionpath=imagepath,
        label="test",
        geometry=geometry,
    )

    args = mocked_run.call_args_list[0].args
    assert args[0] == "mke2fs"
    # offset is in bytes; size is the partition size in KiB.
    assert "-E" in args
    assert f"offset={2048 * 512}" in args
    assert f"{32768 * 512 // 1024}k" == args[-1]


def test_format_populate_partition_fat_with_offset(mocker, content, imagepath):
    """A FAT partition with geometry passes --offset to mkfs.fat and @@ to mcopy."""
    mocked_run = mocker.patch("imagecraft.pack.diskutil.run", autospec=True)
    geometry = diskutil.PartitionGeometry(
        sector_offset=2048, sector_count=32768, sector_size=512
    )

    diskutil.format_populate_partition(
        fstype=FileSystem.FAT16,
        content_dir=content,
        partitionpath=imagepath,
        label="test",
        geometry=geometry,
    )

    mkfs_args = mocked_run.call_args_list[0].args
    assert mkfs_args[0] == "mkfs.fat"
    # mkfs.fat --offset is in sectors; block-count is in KiB.
    assert "--offset" in mkfs_args
    assert str(2048) in mkfs_args
    assert str(32768 * 512 // 1024) == mkfs_args[-1]

    # mcopy targets the image at the partition's byte offset.
    mcopy_args = mocked_run.call_args_list[1].args
    assert mcopy_args[0] == "bash"
    assert f"-i{imagepath}@@{2048 * 512}" in mcopy_args[2]


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


# ── get_partition_geometry ───────────────────────────────────────────────────


_GPT_SFDISK_JSON = """
{
   "partitiontable": {
      "label": "gpt",
      "device": "%(image)s",
      "unit": "sectors",
      "sectorsize": 512,
      "partitions": [
         {
            "node": "%(image)s1",
            "start": 2048,
            "size": 524288,
            "type": "C12A7328-F81F-11D2-BA4B-00A0C93EC93B",
            "name": "efi"
         },
         {
            "node": "%(image)s2",
            "start": 526336,
            "size": 12582912,
            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
            "name": "rootfs"
         }
      ]
   }
}
"""

_MBR_SFDISK_JSON = """
{
   "partitiontable": {
      "label": "dos",
      "device": "%(image)s",
      "unit": "sectors",
      "sectorsize": 512,
      "partitions": [
         {"node": "%(image)s1", "start": 2048, "size": 524288, "type": "0c", "bootable": true},
         {"node": "%(image)s2", "start": 526336, "size": 10485760, "type": "83"}
      ]
   }
}
"""


@pytest.mark.parametrize(
    ("template", "image_name"),
    [
        (_GPT_SFDISK_JSON, "pc.img"),
        (_MBR_SFDISK_JSON, "pi.img"),
    ],
)
def test_get_partition_geometry(mocker, tmp_path, template, image_name):
    image_path = tmp_path / image_name
    fake_result = CompletedProcess(
        args=[],
        returncode=0,
        stdout=template % {"image": str(image_path)},
    )
    mocker.patch(
        "imagecraft.pack.diskutil.run", autospec=True, return_value=fake_result
    )

    geom1 = diskutil.get_partition_geometry(image_path, 1)
    geom2 = diskutil.get_partition_geometry(image_path, 2)

    assert geom1.sector_offset == 2048
    assert geom1.sector_count == 524288
    assert geom1.sector_size == 512
    assert geom1.size_bytes == 524288 * 512

    assert geom2.sector_offset == 526336
    assert geom2.sector_size == 512


def test_get_partition_geometry_missing(mocker, tmp_path):
    image_path = tmp_path / "pc.img"
    fake_result = CompletedProcess(
        args=[],
        returncode=0,
        stdout=_GPT_SFDISK_JSON % {"image": str(image_path)},
    )
    mocker.patch(
        "imagecraft.pack.diskutil.run", autospec=True, return_value=fake_result
    )

    with pytest.raises(CraftError, match="No partition numbered 9"):
        diskutil.get_partition_geometry(image_path, 9)
