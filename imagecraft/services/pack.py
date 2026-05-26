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

"""Imagecraft Package service."""

from pathlib import Path
from typing import cast

from craft_application import PackageService, models
from craft_cli import emit
from typing_extensions import override

from imagecraft.models import Project, get_partition_name
from imagecraft.pack import diskutil, grubutil, rawcontent
from imagecraft.services.image import ImageService


class ImagecraftPackService(PackageService):
    """Package service subclass for Imagecraft."""

    @override
    def pack(self, prime_dir: Path, dest: Path) -> list[Path]:
        """Pack the image.

        :param prime_dir: Directory path to the prime directory.
        :param dest: Directory into which to write the package(s).
        :returns: A list of paths to created packages.
        """
        project = cast(Project, self._services.get("project").get())
        if len(project.volumes) != 1:
            raise AssertionError("This code can only handle one volume")
        volume_name, volume = next(iter(project.volumes.items()))

        image_service = cast(ImageService, self._services.get("image"))
        # Both calls are idempotent — the prologue hook will have run them
        # already during the lifecycle, but pack may be called standalone.
        image_service.create_images()
        image_service.attach_images()

        project_dirs = self._services.get("lifecycle").project_info.dirs
        loop_paths = image_service.get_loop_paths()

        # Phase B grub asset preparation must happen BEFORE the
        # partition-format loop: update-grub writes /boot/grub/grub.cfg
        # into the rootfs prime dir, and the ESP shim/grub files are
        # laid down in the boot prime dir, so that mke2fs -d / mkfs.vfat
        # + mcopy pick them up automatically.
        arch = self._services.get("lifecycle").project_info.target_arch
        prime_dirs_map = {
            get_partition_name(volume_name, s): project_dirs.get_prime_dir(
                partition=get_partition_name(volume_name, s)
            )
            for s in volume.structure
        }
        grub_assets = grubutil.prepare_grub_assets(
            arch=arch,
            volume_name=volume_name,
            volume=volume,
            prime_dirs=prime_dirs_map,
            workdir=project_dirs.work_dir,
        )

        try:
            for structure_item in volume.structure:
                partition_name = get_partition_name(volume_name, structure_item)
                emit.progress(f"Preparing partition {partition_name}")
                partition_prime_dir = project_dirs.get_prime_dir(
                    partition=partition_name
                )
                loop_path = Path(loop_paths[f"{volume_name}/{structure_item.name}"])

                diskutil.format_device(
                    device_path=loop_path,
                    fstype=structure_item.filesystem,
                    label=structure_item.filesystem_label,
                    content_dir=partition_prime_dir,
                )

            image_service.verify_images()
        finally:
            image_service.detach_images()

        images = image_service.finalize_images(dest)

        # Post-finalisation: write GRUB's raw boot images into the final
        # disk. grubutil decides *what* bytes go *where* (policy); the
        # generic rawcontent applier does the byte-writing (mechanism)
        # and has no GRUB knowledge. No loop devices, no image mounts.
        if grub_assets is not None:
            raw_content = grubutil.grub_raw_content(grub_assets)
            for path in images.values():
                rawcontent.apply_raw_content(
                    disk_path=path, contents=raw_content
                )

        return list(images.values())

    @property
    def metadata(self) -> models.BaseMetadata:
        """Get the metadata model for this project."""
        # nop (no metadata file for Imagecraft)
        return models.BaseMetadata()

    @override
    def write_metadata(self, path: Path) -> None:
        """Write the project metadata to metadata.yaml in the given directory.

        :param path: The path to the prime directory.
        """
        # nop (no metadata file for Imagecraft)
