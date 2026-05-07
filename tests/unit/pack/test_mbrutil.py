# Copyright 2026 Canonical Ltd.
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

import subprocess

import pytest
from imagecraft.errors import MBRPartitionError
from imagecraft.models.volume import MBRVolume
from imagecraft.pack import diskutil, mbrutil

MiB = 1024**2
GiB = 1024**3

_VOLUME_SINGLE = {
    "schema": "mbr",
    "structure": [
        {
            "name": "rootfs",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "2G",
        },
    ],
}

_VOLUME_TWO_PARTS = {
    "schema": "mbr",
    "structure": [
        {
            "name": "ubuntu-seed",
            "role": "system-boot",
            "type": "0C",
            "filesystem": "vfat",
            "size": "1200M",
        },
        {
            "name": "rootfs",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "3G",
        },
    ],
}

_VOLUME_FOUR_PARTS = {
    "schema": "mbr",
    "structure": [
        {
            "name": "boot",
            "role": "system-boot",
            "type": "0C",
            "filesystem": "vfat",
            "size": "256M",
        },
        {
            "name": "swap",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "512M",
        },
        {
            "name": "home",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "1G",
        },
        {
            "name": "rootfs",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "4G",
        },
    ],
}

_VOLUME_EXTENDED = {
    "schema": "mbr",
    "structure": [
        {
            "name": "boot",
            "role": "system-boot",
            "type": "0C",
            "filesystem": "vfat",
            "size": "256M",
        },
        {
            "name": "swap",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "512M",
        },
        {
            "name": "home",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "1G",
        },
        {
            "name": "logical1",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "2G",
        },
        {
            "name": "logical2",
            "role": "system-data",
            "type": "83",
            "filesystem": "ext4",
            "size": "2G",
        },
    ],
}


@pytest.fixture
def volume():
    return MBRVolume.unmarshal(_VOLUME_TWO_PARTS)


# ── _create_sfdisk_lines ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("partitions", "expected"),
    [
        pytest.param(
            [
                {"start": "2048", "size": "1024", "type": "0C", "bootable": None},
                {"start": "3072", "size": "4096", "type": "83"},
            ],
            [
                "label: dos",
                "unit: sectors",
                "start=2048, size=1024, type=0C, bootable",
                "start=3072, size=4096, type=83",
                "write",
            ],
            id="bootable-and-plain",
        ),
        pytest.param(
            [{"start": "2048", "size": "2048", "type": "83"}],
            [
                "label: dos",
                "unit: sectors",
                "start=2048, size=2048, type=83",
                "write",
            ],
            id="single-partition",
        ),
    ],
)
def test_create_sfdisk_lines(partitions, expected):
    assert mbrutil._create_sfdisk_lines(partitions) == expected


# ── _create_mbr_layout ────────────────────────────────────────────────────────


def test_create_mbr_layout_unsupported_sector_size(tmp_path, volume):
    with pytest.raises(
        MBRPartitionError, match="Unsupported disk sector size: 1024"
    ) as exc_info:
        mbrutil._create_mbr_layout(
            imagepath=tmp_path / "image.img",
            sector_size=1024,
            layout=volume,
        )
    assert exc_info.value.logpath_report is False
    assert exc_info.value.reportable is False


def test_create_mbr_layout_calls_sfdisk(mocker, tmp_path, volume):
    mocked_run = mocker.patch("imagecraft.pack.mbrutil.subprocess.run", autospec=True)

    mbrutil._create_mbr_layout(
        imagepath=tmp_path / "image.img",
        sector_size=512,
        layout=volume,
    )

    mocked_run.assert_called_once()
    call_args = mocked_run.call_args
    assert call_args.args[0][0] == "sfdisk"
    stdin = call_args.kwargs["input"]
    assert "label: dos" in stdin
    assert "bootable" in stdin  # ubuntu-seed has role system-boot


def test_create_mbr_layout_sfdisk_failure_raises(mocker, tmp_path, volume):
    mocked_run = mocker.patch("imagecraft.pack.mbrutil.subprocess.run", autospec=True)
    mocked_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["sfdisk"], stderr="sfdisk: bad input"
    )

    with pytest.raises(MBRPartitionError, match="failed to write") as exc_info:
        mbrutil._create_mbr_layout(
            imagepath=tmp_path / "image.img",
            sector_size=512,
            layout=volume,
        )
    assert exc_info.value.details == "sfdisk: bad input"


def test_create_mbr_layout_extended_partitions(mocker, tmp_path):
    layout = MBRVolume.unmarshal(_VOLUME_EXTENDED)
    mocked_run = mocker.patch("imagecraft.pack.mbrutil.subprocess.run", autospec=True)

    mbrutil._create_mbr_layout(
        imagepath=tmp_path / "image.img",
        sector_size=512,
        layout=layout,
    )

    stdin = mocked_run.call_args.kwargs["input"]
    assert "type=05" in stdin  # extended container
    # label + unit + 3 primaries + 1 extended container + 2 logicals + write = 9 lines
    assert stdin.count("\n") == 8


def test_create_mbr_layout_boot_in_logical_raises(tmp_path):
    spec = {
        "schema": "mbr",
        "structure": [
            {
                "name": "p1",
                "role": "system-data",
                "type": "83",
                "filesystem": "ext4",
                "size": "256M",
            },
            {
                "name": "p2",
                "role": "system-data",
                "type": "83",
                "filesystem": "ext4",
                "size": "256M",
            },
            {
                "name": "p3",
                "role": "system-data",
                "type": "83",
                "filesystem": "ext4",
                "size": "256M",
            },
            {
                "name": "p4",
                "role": "system-data",
                "type": "83",
                "filesystem": "ext4",
                "size": "256M",
            },
            {
                "name": "boot",
                "role": "system-boot",
                "type": "0C",
                "filesystem": "vfat",
                "size": "256M",
            },
        ],
    }
    layout = MBRVolume.unmarshal(spec)
    with pytest.raises(MBRPartitionError, match="system-boot") as exc_info:
        mbrutil._create_mbr_layout(
            imagepath=tmp_path / "image.img",
            sector_size=512,
            layout=layout,
        )
    assert exc_info.value.details == "Offending partitions: boot"
    assert (
        exc_info.value.resolution == "Move boot to one of the first 3 partition slots."
    )
    assert exc_info.value.logpath_report is False
    assert exc_info.value.reportable is False


# ── get_image_size ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("volume_spec", "expected_size"),
    [
        pytest.param(
            _VOLUME_SINGLE,
            mbrutil.MBR_RESERVED_SIZE + 2 * GiB,
            id="single-partition",
        ),
        pytest.param(
            _VOLUME_TWO_PARTS,
            mbrutil.MBR_RESERVED_SIZE + 1200 * MiB + 3 * GiB,
            id="two-partitions",
        ),
        pytest.param(
            _VOLUME_FOUR_PARTS,
            mbrutil.MBR_RESERVED_SIZE + 256 * MiB + 512 * MiB + 1 * GiB + 4 * GiB,
            id="four-partitions",
        ),
        pytest.param(
            _VOLUME_EXTENDED,
            mbrutil.MBR_RESERVED_SIZE
            + 256 * MiB
            + 512 * MiB
            + 1 * GiB
            + (mbrutil._EBR_OVERHEAD_SECTORS * 512 + 2 * GiB)
            + (mbrutil._EBR_OVERHEAD_SECTORS * 512 + 2 * GiB),
            id="extended-partitions",
        ),
    ],
)
def test_get_image_size(volume_spec, expected_size):
    layout = MBRVolume.unmarshal(volume_spec)
    assert mbrutil.get_image_size(512, layout) == expected_size


# ── create_empty_mbr_image ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("volume_spec", "expected_bytes"),
    [
        pytest.param(
            _VOLUME_SINGLE,
            mbrutil.MBR_RESERVED_SIZE + 2 * GiB,
            id="single-partition",
        ),
        pytest.param(
            _VOLUME_TWO_PARTS,
            mbrutil.MBR_RESERVED_SIZE + 1200 * MiB + 3 * GiB,
            id="two-partitions",
        ),
        pytest.param(
            _VOLUME_FOUR_PARTS,
            mbrutil.MBR_RESERVED_SIZE + 256 * MiB + 512 * MiB + 1 * GiB + 4 * GiB,
            id="four-partitions",
        ),
        pytest.param(
            _VOLUME_EXTENDED,
            mbrutil.MBR_RESERVED_SIZE
            + 256 * MiB
            + 512 * MiB
            + 1 * GiB
            + (mbrutil._EBR_OVERHEAD_SECTORS * 512 + 2 * GiB)
            + (mbrutil._EBR_OVERHEAD_SECTORS * 512 + 2 * GiB),
            id="extended-partitions",
        ),
    ],
)
def test_create_empty_mbr_image(mocker, tmp_path, volume_spec, expected_bytes):
    layout = MBRVolume.unmarshal(volume_spec)
    imagepath = tmp_path / "image.img"
    create_mbr_layout = mocker.patch(
        "imagecraft.pack.mbrutil._create_mbr_layout", autospec=True
    )
    create_zero_image = mocker.patch(
        "imagecraft.pack.diskutil.create_zero_image", autospec=True
    )

    mbrutil.create_empty_mbr_image(imagepath, 512, layout)

    create_mbr_layout.assert_called_once_with(
        imagepath=imagepath,
        sector_size=512,
        layout=layout,
    )
    create_zero_image.assert_called_once_with(
        imagepath=imagepath,
        disk_size=diskutil.DiskSize(bytesize=expected_bytes, sector_size=512),
    )


# ── verify_partition_tables ───────────────────────────────────────────────────


def test_verify_partition_tables_passes_on_no_stderr(mocker, tmp_path):
    imagepath = tmp_path / "image.img"
    mock_run = mocker.patch("imagecraft.pack.mbrutil.subprocess.run", autospec=True)
    mock_run.return_value.stderr = ""

    mbrutil.verify_partition_tables(imagepath)


def test_verify_partition_tables_raises_on_stderr(mocker, tmp_path):
    imagepath = tmp_path / "image.img"
    mock_run = mocker.patch("imagecraft.pack.mbrutil.subprocess.run", autospec=True)
    mock_run.return_value.stderr = "some sfdisk warning"

    with pytest.raises(
        MBRPartitionError, match="problem with the partition table"
    ) as exc_info:
        mbrutil.verify_partition_tables(imagepath)
    assert exc_info.value.details == "some sfdisk warning"


def test_verify_partition_tables_raises_on_sfdisk_failure(mocker, tmp_path):
    imagepath = tmp_path / "image.img"
    mock_run = mocker.patch("imagecraft.pack.mbrutil.subprocess.run", autospec=True)
    mock_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["sfdisk"], stderr="sfdisk: cannot open"
    )

    with pytest.raises(MBRPartitionError, match="failed to read") as exc_info:
        mbrutil.verify_partition_tables(imagepath)
    assert exc_info.value.details == "sfdisk: cannot open"
