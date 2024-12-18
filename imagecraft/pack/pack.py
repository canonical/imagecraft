# Copyright 2022-2024 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For further info, check https://github.com/canonical/imagecraft

"""Image packing."""

import pathlib
import uuid
from collections import OrderedDict

from imagecraft.models import Project, StructureItem, Volume
from imagecraft.platforms import (
    diskutil,
    gptutil,
    grubutil,
)
from imagecraft.platforms.gptutil import (
    DiskLayout,
    GptDisk,
    GptHeader,
    GptPartition,
)

# Disk sector size
_DISK_SECTOR = 512


def packer(
    *,
    prime_dir: pathlib.Path,
    work_dir: pathlib.Path,
    imagepath: pathlib.Path,
    project: Project,
) -> None:
    """Create the image for a given architecture."""
    ## create image file
    ## Prepare partitions and gpt table from volumes

    ## copy content to partitions
    ## prepare grub
    ## Kernel?

    pack_dir = work_dir / "pack"
    pack_dir.mkdir(parents=True, exist_ok=True)

    volume = project.volumes["pc"]

    # Create a directory for the image parts. Image parts are a
    # useful intermediary step allowing us to populate individual
    # partitions without using loopback devices. Image parts may
    # consist of raw partitions, filesystem partitions and GPT
    # header and footer snippets. This location is separately
    # specified because in the future it will be useful to migrate
    # this to the project directory for direct production line
    # sparse storage programming.
    pack_image_dir = pack_dir / "image"
    pack_image_dir.mkdir(parents=True, exist_ok=True)

    # Layout the partitions
    layout = gpt_layout(volume=volume)

    # Create an image
    write_gpt_layout(image_path=imagepath, layout=layout)

    # Extract GPT header and footer parts. These parts must be
    # extracted before bootloader install because the bootloader
    # installation may be required to modify the MBR sector in
    # the GPT header.
    extract_primary_gpt(image_path=imagepath, pack_image_dir=pack_image_dir)
    extract_backup_gpt(image_path=imagepath, pack_image_dir=pack_image_dir)

    data_structure = volume.data_structure()

    install_data(
        parts_prime_dir=prime_dir / "rootfs",
        pack_image_dir=pack_image_dir,
        layout=layout,
        data_structure=data_structure,
    )

    # Build a standalone image which contains all the parts
    # This is a separate step because this final step may be skipped
    # in the future, for example, if the output is to be used in
    # a factory line where parts are flashed sparsely to save time.
    populate_image(
        pack_image_dir=pack_image_dir,
        image_path=imagepath,
        layout=layout,
    )


def populate_image(
    pack_image_dir: pathlib.Path,
    image_path: pathlib.Path,
    layout: DiskLayout,
) -> None:
    """Merge all the image parts into one image file.

    :param pack_image_dir: Path to image parts files.
    :param image_path: Path to the firmware image.
    """
    diskutil.inject_partition_into_image(
        partition=pack_image_dir / "gpt-primary.bin",
        imagepath=image_path,
        sector_size=_DISK_SECTOR,
        sector_offset=0,
        sector_count=int(gptutil.primary_gpt_sector_count(imagepath=image_path)),
    )

    diskutil.inject_partition_into_image(
        partition=pack_image_dir / "rootfs",
        imagepath=image_path,
        sector_size=_DISK_SECTOR,
        sector_offset=layout.gptdisk.partitions["rootfs"].start,
        sector_count=layout.gptdisk.partitions["rootfs"].size,
    )

    # for structure in volume.structures

    diskutil.inject_partition_into_image(
        partition=pack_image_dir / "gpt-backup.bin",
        imagepath=image_path,
        sector_size=_DISK_SECTOR,
        sector_offset=int(gptutil.backup_gpt_sector_start(imagepath=image_path)),
        sector_count=layout.gptdisk.total_sectors()
        - int(gptutil.backup_gpt_sector_start(imagepath=image_path)),
    )


def gpt_layout(
    volume: Volume,
) -> DiskLayout:
    """Create GPT layout."""
    partitions = OrderedDict()

    for strucure_item in volume.structure:
        partitions[strucure_item.name] = GptPartition(
            start=204800 + 4096,
            size=strucure_item.size,
            type=strucure_item.type_,
            uuid=str(uuid.uuid4()),
            name=strucure_item.name,
        )

    gpt_disk = GptDisk(
        header_lines=GptHeader(label_id="8984DCD3-7190-1246-A4BB-980CEE0EB65A"),
        partitions=partitions,
    )

    return DiskLayout(
        gptdisk=gpt_disk,
    )


def write_gpt_layout(
    image_path: pathlib.Path,
    layout: DiskLayout,
) -> None:
    """Write a GPT layout to a disk image.

    :param image_path: Path to the firmware image.
    :param layout: The GPT layout
    """
    diskutil.create_zero_image(
        imagepath=image_path,
        sector_size=_DISK_SECTOR,
        sector_count=layout.gptdisk.total_sectors(),
    )
    gptutil.create_gpt_layout(
        imagepath=image_path, sector_size=_DISK_SECTOR, layout=layout
    )


def extract_primary_gpt(image_path: pathlib.Path, pack_image_dir: pathlib.Path) -> None:
    """Extract the primary gpt sectors.

    :param image_path: Path to the firmware image.
    :param pack_image_dir: Path to image parts files.
    """
    gptutil.extract_primary_gpt(
        imagepath=image_path,
        sector_size=_DISK_SECTOR,
        headerpath=pack_image_dir / "gpt-primary.bin",
    )


def extract_backup_gpt(image_path: pathlib.Path, pack_image_dir: pathlib.Path) -> None:
    """Extract the backup gpt sectors.

    :param image_path: Path to the firmware image.
    :param pack_image_dir: Path to image parts files.
    """
    gptutil.extract_backup_gpt(
        imagepath=image_path,
        sector_size=_DISK_SECTOR,
        footerpath=pack_image_dir / "gpt-backup.bin",
    )


def install_bootloaders(
    parts_stage_dir: pathlib.Path,
    pack_stage_dir: pathlib.Path,
    pack_image_dir: pathlib.Path,
    layout: DiskLayout,
) -> None:
    """Device specific bootloader installation.

    :param parts_stage_dir: Parts lifecycle staging directory.
    :param pack_stage_dir: Pack step staging directory.
    :param pack_image_dir: Pack step image parts directory.
    """
    partition_stage_dir = pack_stage_dir / "kernos-boot"
    partition_stage_dir.mkdir(parents=True, exist_ok=True)

    # Install the Grub executable
    # When you see this fail with "moddep.lst doesn't exist", the issue is
    # that the platform-specific part wasn't injected.
    grubutil.grub_efi_install(
        parts_stage_dir=parts_stage_dir,
        esp_stage_dir=partition_stage_dir,
        grub_modules=[
            "all_video",
            "biosdisk",
            "boot",
            "cat",
            "chain",
            "configfile",
            "echo",
            "ext2",
            "fat",
            "font",
            "gettext",
            "gfxmenu",
            "gfxterm",
            "gfxterm_background",
            "gzio",
            "halt",
            "jpeg",
            "keystatus",
            "loadenv",
            "loopback",
            "linux",
            "memdisk",
            "minicmd",
            "normal",
            "part_gpt",
            "png",
            "reboot",
            "search",
            "search_fs_uuid",
            "search_fs_file",
            "search_label",
            "sleep",
            "squash4",
            "test",
            "true",
            "btrfs",
            "hfsplus",
            "iso9660",
            "part_apple",
            "part_msdos",
            "password_pbkdf2",
            "zfs",
            "zfscrypt",
            "zfsinfo",
            "lvm",
            "mdraid09",
            "mdraid1x",
            "raid5rec",
            "raid6rec",
            "video",
        ],
    )

    # Write a config file
    grubutil.grub_efi_config(esp_stage_dir=partition_stage_dir)

    # Write the default empty environment
    grubutil.grub_efi_env_default(esp_stage_dir=partition_stage_dir)

    # Create actual EFI System Partition.
    diskutil.format_install_fat_partition(
        content_dir=partition_stage_dir,
        sector_size=_DISK_SECTOR,
        sector_count=layout.gptdisk.partitions["boot"].size,
        partitionpath=pack_image_dir / "kernos-boot.fat",
        label="kernos-boot",
    )


def install_data(
    parts_prime_dir: pathlib.Path,
    pack_image_dir: pathlib.Path,
    layout: DiskLayout,
    data_structure: StructureItem,
) -> None:
    """Install the rootfs."""
    diskutil.format_install_ext_partition(
        content_dir=parts_prime_dir,
        sector_size=_DISK_SECTOR,
        sector_count=layout.gptdisk.partitions[data_structure.name].size,
        partitionpath=pack_image_dir / "rootfs",
        fstype="ext4",
        label=data_structure.filesystem_label,
    )
