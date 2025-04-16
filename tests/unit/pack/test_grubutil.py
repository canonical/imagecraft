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

import contextlib
from pathlib import Path

import pytest
from craft_platforms import DebianArchitecture
from imagecraft.models import Volume
from imagecraft.pack.grubutil import setup_grub
from imagecraft.pack.image import Image


@pytest.fixture
def volume():
    return Volume.unmarshal(
        {
            "schema": "gpt",
            "structure": [
                {
                    "name": "efi",
                    "role": "system-boot",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "vfat",
                    "size": "3G",
                    "filesystem-label": "",
                },
                {
                    "name": "boot",
                    "role": "system-boot",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "fat16",
                    "size": "6G",
                },
                {
                    "name": "rootfs",
                    "role": "system-data",
                    "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                    "filesystem": "ext4",
                    "size": "0",
                    "filesystem-label": "writable",
                },
            ],
        }
    )


@contextlib.contextmanager
def fake_loopdev_handler():
    yield "loop99"


@pytest.mark.usefixtures("new_dir")
def test_setup_grub(mocker, new_dir, volume):
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(
        volume=volume,
        disk_path=disk_path,
    )
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    mock_chroot = mocker.patch("imagecraft.pack.grubutil.Chroot")
    mocker.patch.object(image, "attach_loopdev", side_effect=fake_loopdev_handler)

    setup_grub(image=image, workdir=workdir, arch=DebianArchitecture.AMD64)

    assert mock_chroot.return_value.execute.called


@pytest.mark.parametrize(
    ("volume", "arch", "message"),
    [
        (
            Volume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                    ],
                }
            ),
            DebianArchitecture.AMD64,
            "Skipping GRUB installation because no boot partition was found",
        ),
        (
            Volume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                    ],
                }
            ),
            DebianArchitecture.AMD64,
            "Skipping GRUB installation because no data partition was found",
        ),
        (
            Volume.unmarshal(
                {
                    "schema": "gpt",
                    "structure": [
                        {
                            "name": "efi",
                            "role": "system-boot",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "vfat",
                            "size": "3G",
                            "filesystem-label": "",
                        },
                        {
                            "name": "rootfs",
                            "role": "system-data",
                            "type": "0FC63DAF-8483-4772-8E79-3D69D8477DE4",
                            "filesystem": "ext4",
                            "size": "0",
                            "filesystem-label": "writable",
                        },
                    ],
                }
            ),
            DebianArchitecture.S390X,
            "Cannot install GRUB on this architecture",
        ),
    ],
)
@pytest.mark.usefixtures("new_dir")
def test_setup_grub_partitions(mocker, new_dir, volume, arch, emitter, message):
    disk_path = Path(new_dir, "pc.img")
    disk_path.touch(exist_ok=True)
    image = Image(
        volume=volume,
        disk_path=disk_path,
    )
    workdir = Path(new_dir, "workdir")
    workdir.mkdir()
    mock_chroot = mocker.patch("imagecraft.pack.grubutil.Chroot")
    mocker.patch.object(image, "attach_loopdev", side_effect=fake_loopdev_handler)

    setup_grub(image=image, workdir=workdir, arch=arch)

    mock_chroot.return_value.execute.assert_not_called()

    emitter.assert_progress(message, permanent=True)
