# This file is part of imagecraft.
#
# Copyright 2023-2025 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Imagecraft error definitions."""

from craft_cli import CraftError


class ImagecraftError(CraftError):
    """Base class for all imagecraft errors."""


class ImageError(ImagecraftError):
    """Raised when an error occurs when dealing with the Image class."""


class GRUBInstallError(ImagecraftError):
    """Raised when an error occurs when installing grub."""


class ChrootError(ImagecraftError):
    """Base class for chroot handler errors."""


class ChrootMountError(ChrootError):
    """Failed to mount in the chroot.

    :param mountpoint: The filesystem mount point.
    :param message: The error message.
    """

    def __init__(self, mountpoint: str, message: str) -> None:
        self.mountpoint = mountpoint
        self.message = message
        message = f"Failed to mount on {mountpoint}: {message}"

        super().__init__(message=message)


class ChrootExecutionError(ChrootError):
    """Raised when an error occurs when dealing with the chroot."""


class PartitionError(ImagecraftError):
    """Raised when an error occurs with a partition table."""

    def __init__(
        self,
        message: str,
        *,
        details: str | None = None,
        resolution: str | None = None,
        docs_url: str | None = None,
        logpath_report: bool = False,
        reportable: bool = False,
        retcode: int = 1,
        doc_slug: str | None = None,
    ) -> None:
        super().__init__(
            message,
            details=details,
            resolution=resolution,
            docs_url=docs_url,
            logpath_report=logpath_report,
            reportable=reportable,
            retcode=retcode,
            doc_slug=doc_slug,
        )


class MBRPartitionError(PartitionError):
    """Raised when an error occurs with an MBR partition table."""
