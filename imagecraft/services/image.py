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

"""Service for creating and modifying the image."""

import atexit
import contextlib
import json
import pathlib
import shutil
import subprocess
import time
from collections.abc import Mapping
from typing import Any, cast

from craft_application import AppMetadata, AppService, ServiceFactory
from craft_cli import CraftError, emit

from imagecraft.models import Project
from imagecraft.models.volume import PartitionSchema
from imagecraft.pack import gptutil
from imagecraft.pack.image import _volume_partition_nums, _wait_for_loopdev_partitions
from imagecraft.subprocesses import run

_LOSETUP_BIN = "losetup"


class ImageService(AppService):
    """Service for accessing the final image file."""

    def __init__(
        self,
        app: AppMetadata,
        services: ServiceFactory,
        *,
        project_dir: pathlib.Path,
    ) -> None:
        super().__init__(app, services)
        self._project_dir = project_dir
        self._sector_size = gptutil.SECTOR_SIZE_512
        self._images: dict[str, pathlib.Path] | None = None
        self._loop_devices: dict[str, str] = {}
        self._atexit_registered = False

    def get_images(self) -> Mapping[str, pathlib.Path]:
        """Return the current mapping of volume names to image paths.

        :raises ValueError: If images have not been created yet.
        """
        if self._images is None:
            raise ValueError("Images must be created before they can be retrieved.")
        return self._images

    def create_images(self) -> Mapping[str, pathlib.Path]:
        """Create the image files on disk.

        This method creates the image files described by the volumes key in
        imagecraft.yaml. The images are partitioned, but the partitions are not
        formatted. This is the state of the images that will be available during the
        parts lifecycle.
        """
        if self._images is not None:
            return self._images

        project = cast(Project, self._services.get("project").get())
        self._images = {}

        for name, volume in project.volumes.items():
            # Use predictable hidden names for temporary images.
            image_path = self._project_dir / f".{name}.img.tmp"
            match volume.volume_schema:
                case PartitionSchema.GPT:
                    gptutil.create_empty_gpt_image(
                        imagepath=image_path,
                        sector_size=self._sector_size,
                        layout=volume,
                    )
                case _:
                    # Reaching this case is a bug.
                    raise NotImplementedError(
                        f"Creating images with partition schema {volume.volume_schema} unimplemented."
                    )
            self._images[name] = image_path

        return self._images

    def _get_all_loop_devices(self) -> list[dict[str, Any]]:
        """Return a list of all loop devices on the system."""
        try:
            result = run(_LOSETUP_BIN, "--json")
            return cast(list[dict[str, Any]], json.loads(result.stdout)["loopdevices"])
        except (subprocess.CalledProcessError, KeyError, json.JSONDecodeError):
            return []

    def attach_images(self) -> Mapping[str, str]:
        """Attach all created images as loop devices.

        This method is idempotent. It will reuse existing loop devices if they
        are already attached to the correct files, and clean up stale devices
        pointing to deleted inodes.
        """
        if self._loop_devices:
            return self._loop_devices

        if self._images is None:
            raise ValueError("Images must be created before attaching.")

        all_devices = self._get_all_loop_devices()
        project = cast(Project, self._services.get("project").get())

        for name, image_path in self._images.items():
            attached_device: str | None = None
            is_fresh_attach = False

            # 1. Check for existing devices pointing to this file.
            for dev in all_devices:
                back_file = pathlib.Path(dev["back-file"])
                try:
                    if image_path.samefile(back_file):
                        attached_device = dev["name"]
                        emit.debug(
                            f"Reusing existing loop device {attached_device} for {image_path}"
                        )
                        break
                except FileNotFoundError:
                    # Stale inode: file deleted and recreated.
                    if back_file == image_path:
                        emit.debug(
                            f"Detaching stale loop device {dev['name']} for {image_path}"
                        )
                        run(_LOSETUP_BIN, "-d", dev["name"])

            # 2. Attach a fresh device if none was found/reused.
            if not attached_device:
                try:
                    attached_device = run(
                        _LOSETUP_BIN,
                        "--find",
                        "--show",
                        "--partscan",
                        str(image_path),
                    ).stdout.strip()
                    emit.debug(f"Attached {image_path} as {attached_device}")
                    is_fresh_attach = True
                except subprocess.CalledProcessError as err:
                    raise CraftError(
                        f"Failed to attach loop device for {image_path}.",
                        details=str(err),
                        resolution="Ensure loop devices are available and you have sufficient permissions (sudo).",
                    ) from err

            # 3. Wait for partition nodes after a fresh attach to avoid race conditions.
            if is_fresh_attach:
                _wait_for_loopdev_partitions(
                    attached_device, _volume_partition_nums(project.volumes[name])
                )

            self._loop_devices[name] = attached_device

        if not self._atexit_registered:
            atexit.register(self.detach_images)
            self._atexit_registered = True

        return self._loop_devices

    def detach_images(self) -> None:
        """Detach all attached loop devices.

        Includes a retry loop for busy devices. Safe to call as an atexit handler.
        """
        for name, device in list(self._loop_devices.items()):
            success = False
            start_time = time.monotonic()
            while time.monotonic() - start_time < 10:  # noqa: PLR2004 (10 seconds)
                try:
                    run(_LOSETUP_BIN, "-d", device)
                    success = True
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(1)

            if success:
                del self._loop_devices[name]
                with contextlib.suppress(Exception):
                    emit.debug(f"Detached loop device {device} for {name}")
            else:
                with contextlib.suppress(Exception):
                    emit.warning(
                        f"Failed to detach loop device {device} after 10 seconds."
                    )

    def get_loop_paths(self) -> Mapping[str, str]:
        """Return a mapping of loop device paths for all volumes and their partitions.

        Keys use the format 'volume_name' for volume devices and
        'volume_name/structure_name' for partition devices.
        Values are paths like '/dev/loop8' and '/dev/loop8p1'.
        """
        if not self._loop_devices:
            return {}

        project = cast(Project, self._services.get("project").get())
        mapping: dict[str, str] = {}

        for vol_name, loop_dev in self._loop_devices.items():
            mapping[vol_name] = loop_dev
            volume = project.volumes[vol_name]
            for i, structure in enumerate(volume.structure, start=1):
                part_num = structure.partition_number or i
                mapping[f"{vol_name}/{structure.name}"] = f"{loop_dev}p{part_num}"

        return mapping

    def verify_images(self) -> None:
        """Verify the integrity of all created images."""
        if self._images is None:
            return

        for image_path in self._images.values():
            gptutil.verify_partition_tables(image_path)

    def finalize_images(self, dest: pathlib.Path) -> Mapping[str, pathlib.Path]:
        """Move hidden image files to their final destination.

        Moves each .{name}.img.tmp to dest/{name}.img.

        :param dest: Directory to move the final images into.
        :returns: a Mapping of the image names to their paths.
        """
        images = dict(self.get_images())
        dest.mkdir(parents=True, exist_ok=True)
        for name, hidden_path in list(images.items()):
            final_path = dest / f"{name}.img"
            shutil.move(str(hidden_path), final_path)
            emit.debug(f"Finalized image {name!r} -> {final_path}")
            images[name] = final_path
        self._images = None
        return images
