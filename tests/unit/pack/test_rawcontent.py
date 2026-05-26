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

"""Unit tests for the generic raw-content applier."""

from imagecraft.pack.rawcontent import (
    MbrBootCode,
    PartitionStart,
    RawContent,
    SectorOffset,
    apply_raw_content,
)


def _dd_args(call):
    return list(call.args)


def test_apply_mbr_boot_code_caps_write_length(mocker, tmp_path):
    disk_path = tmp_path / "pc.img"
    disk_path.write_bytes(b"\x00" * 2048)
    boot_img = tmp_path / "boot.img"
    boot_img.write_bytes(b"X" * 512)

    mock_run = mocker.patch("imagecraft.pack.rawcontent.run")

    apply_raw_content(
        disk_path=disk_path,
        contents=[
            RawContent(source=boot_img, target=MbrBootCode(max_bytes=440)),
        ],
    )

    mock_run.assert_called_once()
    args = _dd_args(mock_run.call_args)
    assert args[0] == "dd"
    # bs=1 + count=440 keeps the write inside the boot-code region so the
    # partition table at bytes 440..512 is preserved.
    assert "bs=1" in args
    assert "count=440" in args
    assert "conv=notrunc" in args
    assert any(a.startswith("of=") and "pc.img" in a for a in args)


def test_apply_sector_offset(mocker, tmp_path):
    disk_path = tmp_path / "pc.img"
    disk_path.write_bytes(b"\x00" * 2048)
    core_img = tmp_path / "core.img"
    core_img.write_bytes(b"C" * 8192)

    mock_run = mocker.patch("imagecraft.pack.rawcontent.run")

    apply_raw_content(
        disk_path=disk_path,
        contents=[
            RawContent(source=core_img, target=SectorOffset(sector=1)),
        ],
    )

    args = _dd_args(mock_run.call_args)
    assert "bs=512" in args
    assert "seek=1" in args
    # No count: the whole source is written.
    assert not any(a.startswith("count=") for a in args)


def test_apply_partition_start_resolves_offset(mocker, tmp_path):
    disk_path = tmp_path / "pc.img"
    disk_path.write_bytes(b"\x00" * 2048)
    core_img = tmp_path / "core.img"
    core_img.write_bytes(b"C" * 8192)

    mock_run = mocker.patch("imagecraft.pack.rawcontent.run")
    mock_offset = mocker.patch(
        "imagecraft.pack.rawcontent.gptutil.get_partition_sector_offset",
        return_value=34,
    )

    apply_raw_content(
        disk_path=disk_path,
        contents=[
            RawContent(
                source=core_img,
                target=PartitionStart(partition_name="bios-boot"),
            ),
        ],
    )

    mock_offset.assert_called_once_with(disk_path, "bios-boot")
    args = _dd_args(mock_run.call_args)
    assert "bs=512" in args
    assert "seek=34" in args


def test_apply_empty_contents_is_noop(mocker, tmp_path):
    disk_path = tmp_path / "pc.img"
    disk_path.write_bytes(b"\x00" * 2048)

    mock_run = mocker.patch("imagecraft.pack.rawcontent.run")

    apply_raw_content(disk_path=disk_path, contents=[])

    mock_run.assert_not_called()


def test_apply_writes_each_record_in_order(mocker, tmp_path):
    disk_path = tmp_path / "pc.img"
    disk_path.write_bytes(b"\x00" * 2048)
    boot_img = tmp_path / "boot.img"
    boot_img.write_bytes(b"X" * 512)
    core_img = tmp_path / "core.img"
    core_img.write_bytes(b"C" * 8192)

    mock_run = mocker.patch("imagecraft.pack.rawcontent.run")
    mocker.patch(
        "imagecraft.pack.rawcontent.gptutil.get_partition_sector_offset",
        return_value=34,
    )

    apply_raw_content(
        disk_path=disk_path,
        contents=[
            RawContent(source=boot_img, target=MbrBootCode(max_bytes=440)),
            RawContent(
                source=core_img,
                target=PartitionStart(partition_name="bios-boot"),
            ),
        ],
    )

    assert mock_run.call_count == 2
    first, second = mock_run.call_args_list
    assert any(a == "count=440" for a in first.args)
    assert any(a == "seek=34" for a in second.args)
