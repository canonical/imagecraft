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


class MountError(ImagecraftError):
    """Raised when an error occurs mounting or unmounting an image or partition."""


class BootloaderError(ImagecraftError):
    """Raised when an error occurs when installing the bootloader."""


class BootloaderToolsMissingError(BootloaderError):
    """Raised when GRUB tools or module files aren't present in the build environment.

    Distinct from other :class:`BootloaderError` failures (e.g. insufficient
    space to embed core.img) so callers can gracefully skip bootloader
    installation instead of failing the whole ``pack`` operation, matching
    the historical behaviour of the loop-device/chroot based installer.
    """


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
