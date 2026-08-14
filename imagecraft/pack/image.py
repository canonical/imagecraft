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

"""Image handling."""

from pathlib import Path

from imagecraft import errors
from imagecraft.models import Role, Volume


class Image:
    """Image.

    :param volume: the Volume associated to the image.
    :param disk_path: path to the disk.
    """

    volume: Volume
    disk_path: Path

    def __init__(
        self,
        *,
        volume: Volume,
        disk_path: Path,
    ) -> None:
        self.volume = volume
        self.disk_path = disk_path
        if not self.disk_path.is_file():
            raise errors.ImageError(
                f"Image specified ({self.disk_path}) doesn't exist or is not a valid file."
            )

    @property
    def has_data_partition(self) -> bool:
        """Check if a data partition is present in the image."""
        return any(s.role == Role.SYSTEM_DATA for s in self.volume.structure)

    @property
    def has_boot_partition(self) -> bool:
        """Check if a boot partition is present in the image."""
        return any(s.role == Role.SYSTEM_BOOT for s in self.volume.structure)
