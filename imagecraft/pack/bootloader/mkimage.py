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

"""Wrapper for the host grub-mkimage executable."""

import os
import shutil
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from subprocess import CompletedProcess

from imagecraft import errors
from imagecraft.subprocesses import run

_GRUB_MKIMAGE_BIN = "grub-mkimage"


class GrubMkimage:
    """Wrapper class to build GRUB core/EFI images using host grub-mkimage."""

    def __init__(self, root_dir: Path | None = None) -> None:
        """Initialize GrubMkimage.

        :param root_dir: Optional guest rootfs directory, used as a fallback
            module directory when a target's modules aren't found in the host's
            own GRUB installation.
        :raises errors.BootloaderError: If grub-mkimage cannot be located.
        """
        self.root_dir = root_dir.resolve() if root_dir is not None else None
        self.binary_path = self._locate_binary(root_dir=self.root_dir)

    @staticmethod
    def _locate_binary(root_dir: Path | None = None) -> Path:
        """Locate the grub-mkimage binary on the host PATH or in the guest rootfs."""
        which_bin = shutil.which(_GRUB_MKIMAGE_BIN)
        if which_bin:
            return Path(which_bin).resolve()

        if root_dir is not None:
            guest_bin = root_dir / "usr" / "bin" / _GRUB_MKIMAGE_BIN
            if guest_bin.is_file() and os.access(guest_bin, os.X_OK):
                return guest_bin.resolve()

        raise errors.BootloaderError(
            f"{_GRUB_MKIMAGE_BIN} not found on host PATH or in guest rootfs "
            "(usr/bin/grub-mkimage)",
            resolution="Install the grub-common package on the build host.",
        )

    def run(
        self,
        *,
        grub_format: str,
        output: Path,
        directory: Path,
        prefix: PurePosixPath | None = None,
        config: Path | None = None,
        modules: Sequence[str] = (),
        filter_available: bool = True,
    ) -> CompletedProcess[str]:
        """Execute grub-mkimage to assemble a core/EFI image.

        :param grub_format: GRUB target format (e.g. ``x86_64-efi``, ``i386-pc``).
        :param output: Path of the image file to produce.
        :param directory: Directory containing the ``.mod``/module files for
            ``grub_format``.
        :param prefix: Optional embedded GRUB prefix directory.
        :param config: Optional configuration file to embed in the image.
        :param modules: GRUB module names to embed.
        :param filter_available: If True, silently skip modules whose ``.mod``
            file isn't present in ``directory`` (some modules are architecture
            or build-specific).
        :raises FileNotFoundError: If ``directory`` or ``config`` don't exist.
        :raises CalledProcessError: If grub-mkimage fails.
        """
        if not directory.is_dir():
            raise FileNotFoundError(f"GRUB modules directory not found: {directory}")
        if config is not None and not config.is_file():
            raise FileNotFoundError(f"GRUB config file not found: {config}")

        cmd_args: list[str | Path] = [
            "-d",
            directory,
            "-O",
            grub_format,
            "-o",
            output,
        ]
        if prefix is not None:
            cmd_args.extend(["-p", str(prefix)])
        if config is not None:
            cmd_args.extend(["-c", config])

        if filter_available:
            selected_modules = [
                module for module in modules if (directory / f"{module}.mod").is_file()
            ]
        else:
            selected_modules = list(modules)
        cmd_args.extend(selected_modules)

        return run(str(self.binary_path), *cmd_args)
