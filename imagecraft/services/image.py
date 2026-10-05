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
import pathlib
import shutil
from collections.abc import Mapping
from typing import cast

from craft_application import AppMetadata, AppService, ServiceFactory
from craft_cli import emit

from imagecraft import errors
from imagecraft.models import Project
from imagecraft.models.volume import PartitionSchema
from imagecraft.pack import gptutil, mbrutil
from imagecraft.utils.mount import VirtualDeviceManager

# Directory, relative to the project, holding the virtual partition devices.
DEVICES_DIR = ".devices"


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
        self._vdev_managers: dict[str, VirtualDeviceManager] = {}
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
                case PartitionSchema.MBR:
                    mbrutil.create_empty_mbr_image(
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

    def attach_images(self) -> None:
        """Provide virtual devices for all created images.

        Each volume is exposed as its raw image file, and each of its
        partitions as a fusefile virtual device under the project's
        ``.devices`` directory. This method is idempotent.

        Use :meth:`get_device_paths` to obtain the resulting paths.

        :raises ValueError: If images have not been created yet.
        :raises errors.MountError: If a virtual device cannot be created.
        """
        if self._images is None:
            raise ValueError("Images must be created before attaching.")

        if self._vdev_managers:
            missing = set(self._images) - set(self._vdev_managers)
            if not missing:
                self.get_device_paths()
                return
            emit.debug(
                f"Partially-attached state: present={sorted(self._vdev_managers)}, missing={sorted(missing)}"
            )
            raise errors.MountError("Unexpected partially-attached state found.")

        project = cast(Project, self._services.get("project").get())
        target_dir = self._project_dir / DEVICES_DIR

        new_managers: dict[str, VirtualDeviceManager] = {}
        try:
            for name, image_path in self._images.items():
                slices = gptutil.get_partition_slices(image_path, project.volumes[name])
                vdev = VirtualDeviceManager(
                    image_path=image_path,
                    slices={
                        f"{name}_{part}": part_slice
                        for part, part_slice in slices.items()
                    },
                    target_dir=target_dir,
                )
                # Register before mount so the rollback below owns devices
                # mounted before a mid-mount failure and can retry them.
                new_managers[name] = vdev
                devices = vdev.mount()
                emit.debug(f"Provided virtual devices for {image_path}: {devices}")
            self._vdev_managers.update(new_managers)
        except Exception:
            for name, vdev in new_managers.items():
                try:
                    vdev.unmount()
                except Exception:  # noqa: BLE001, PERF203
                    # Retain the manager so detach_images()/atexit can retry
                    # the devices it could not unmount.
                    self._vdev_managers[name] = vdev
            if self._vdev_managers and not self._atexit_registered:
                atexit.register(self.detach_images)
                self._atexit_registered = True
            raise

        if not self._atexit_registered:
            atexit.register(self.detach_images)
            self._atexit_registered = True

    def detach_images(self) -> None:
        """Unmount all virtual devices.

        Failures are reported as warnings rather than raised, so this is safe
        to call from a ``finally`` block or as an atexit handler.
        """
        for name, vdev in list(self._vdev_managers.items()):
            try:
                vdev.unmount()
                del self._vdev_managers[name]
            except Exception as err:  # noqa: BLE001, PERF203
                with contextlib.suppress(Exception):
                    emit.warning(
                        f"Failed to unmount the virtual devices of {name}: {err}"
                    )

    def cleanup_temporary_images(self) -> None:
        """Remove any on-disk temporary images tracked by this service.

        This is intended for flows that created temp images eagerly but later
        skipped final packing, so no finalize step will move them away.
        """
        if self._images is None:
            return

        # Unmount first so the virtual devices do not keep the deleted inodes
        # mapped.
        self.detach_images()
        # Only remove images whose devices fully detached; a busy FUSE
        # device must keep its backing file and the service must keep the
        # state needed to retry.
        remaining = dict(self._images)
        for name in self._vdev_managers:
            remaining.pop(name, None)
        for name, image_path in remaining.items():
            image_path.unlink(missing_ok=True)
            del self._images[name]
        if not self._images:
            self._images = None

    def get_device_paths(self) -> Mapping[str, pathlib.Path]:
        """Return a mapping of device paths for all volumes and partitions.

        Keys use the format 'volume_name' for volumes and
        'volume_name/structure_name' for partitions. Volume values are the
        raw image files; partition values are the virtual partition devices
        created by :meth:`attach_images`.

        :returns: An empty mapping if no images are attached.
        """
        if not self._vdev_managers or self._images is None:
            return {}

        project = cast(Project, self._services.get("project").get())
        mapping: dict[str, pathlib.Path] = {}

        for vol_name, vdev in self._vdev_managers.items():
            mapping[vol_name] = self._images[vol_name]
            devices = vdev.devices
            for structure in project.volumes[vol_name].structure:
                key = f"{vol_name}_{structure.name}"
                if key not in devices:
                    # A partially unmounted volume stays registered so a
                    # later detach can retry it. Reporting an incomplete
                    # mapping here would let pack format a partition that
                    # is no longer backed by a device file, so fail loudly
                    # instead.
                    raise errors.MountError(
                        f"Virtual device for partition {key} is not mounted; "
                        f"volume {vol_name} was only partially attached"
                    )
                mapping[f"{vol_name}/{structure.name}"] = devices[key]

        return mapping

    def verify_images(self) -> None:
        """Verify the integrity of all created images."""
        if self._images is None:
            return

        project = cast(Project, self._services.get("project").get())
        for name, image_path in self._images.items():
            schema = project.volumes[name].volume_schema
            match schema:
                case PartitionSchema.GPT:
                    gptutil.verify_partition_tables(image_path)
                case PartitionSchema.MBR:
                    mbrutil.verify_partition_tables(image_path)

    def finalize_images(self, dest: pathlib.Path) -> Mapping[str, pathlib.Path]:
        """Move hidden image files to their final destination.

        Move each .{name}.img.tmp to dest/{name}.img. Finalization consumes the
        tracked temporary image set so callers must recreate images before new
        image-service operations.

        :param dest: Directory to move the final images into.
        :returns: a Mapping of the image names to their paths.
        """
        if self._vdev_managers:
            raise errors.MountError(
                "Cannot finalize images while virtual devices remain mounted."
            )

        images = dict(self.get_images())
        dest.mkdir(parents=True, exist_ok=True)
        for name, hidden_path in images.items():
            final_path = dest / f"{name}.img"
            shutil.move(str(hidden_path), final_path)
            emit.debug(f"Finalized image {name!r} -> {final_path}")
            images[name] = final_path

        self._images = None
        return images
