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

"""Execute a callable in a chroot environment."""

import logging
import multiprocessing
import os
import subprocess
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from craft_parts.utils import os_utils

from imagecraft import errors

logger = logging.getLogger(__name__)


class Mount:
    """Mount entry for chroot setup."""

    _fstype: str | None
    _src: str
    _relative_mountpoint: str
    _options: list[str] | None = None
    _mountpoint: Path | None = None

    def __init__(
        self,
        fstype: str | None,
        src: str,
        relative_mountpoint: str,
        *,
        options: list[str] | None = None,
    ) -> None:
        self._fstype = fstype
        self._src = src
        self._relative_mountpoint = relative_mountpoint
        if options:
            self._options = options

    def mount(self, base_path: Path) -> None:
        """Mount the mountpoint.

        :param base_path: path to mount the mountpoint under.
        """
        args: list[str] = []
        if self._options:
            args.extend(self._options)
        if self._fstype:
            args.append(f"-t{self._fstype}")

        self._mountpoint = base_path / self._relative_mountpoint.lstrip("/")
        pid = os.getpid()
        if not self._mountpoint.exists():
            raise errors.ChrootExecutionError(
                f"mountpoint {str(self._mountpoint)} does not exist."
            )

        logger.debug("[pid=%d] mount %r on chroot", pid, str(self._mountpoint))
        os_utils.mount(self._src, str(self._mountpoint), *args)

    def umount(self, *, lazy: bool = False) -> None:
        """Umount the mountpoint."""
        pid = os.getpid()

        if self._mountpoint and self._mountpoint.exists():
            logger.debug("[pid=%d] umount: %r", pid, str(self._mountpoint))

            os_utils.mount(str(self._mountpoint), "--make-rprivate")
            args: list[str] = ["--recursive"]

            # Mount points under /dev may be in use and make the bind mount
            # unmountable. This may happen in destructive mode depending on
            # the host environment, so use MNT_DETACH to defer unmounting.
            if lazy:
                args.append("--lazy")
            os_utils.umount(str(self._mountpoint), *args)


def _runner(
    path: Path,
    conn: Connection,
    target: Callable[..., str | None],
    args: tuple[str],
    kwargs: dict[str, Any],
) -> None:
    """Chroot to the execution directory and call the target function."""
    pid = os.getpid()
    logger.debug("[pid=%d] child process: target=%r", pid, target)
    try:
        logger.debug("[pid=%d] chroot to %r", pid, path)
        os.chdir(path)
        os.chroot(path)
        res = target(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001
        conn.send((None, str(exc)))
        return

    conn.send((res, None))


class Chroot:
    """Chroot manager."""

    mounts: list[Mount]
    path: Path

    def __init__(self, *, path: Path, mounts: list[Mount]) -> None:
        self.path = path
        self.mounts = mounts

    def _setup(self) -> None:
        """Chroot environment preparation."""
        logger.debug("setup chroot: %r", self.path)

        for entry in self.mounts:
            entry.mount(base_path=self.path)

        logger.debug("chroot setup complete")

    def _cleanup(self) -> None:
        """Chroot environment cleanup."""
        umount_errors: list[Exception] = []
        logger.debug("cleanup chroot: %r", self.path)
        for entry in reversed(self.mounts):
            try:
                entry.umount()
            except subprocess.CalledProcessError as err:  # noqa: PERF203
                umount_errors.append(err)

        if umount_errors:
            raise errors.ChrootExecutionError(umount_errors)

    def execute(
        self, target: Callable[..., str | None], *args: Any, **kwargs: Any
    ) -> Any:  # noqa: ANN401
        """Execute a callable in a chroot environment.

        :param target: The callable to run in the chroot environment.
        :param args: Arguments for target.
        :param kwargs: Keyword arguments for target.

        :returns: The target function return value.
        """
        logger.debug("[pid=%d] parent process", os.getpid())
        parent_conn, child_conn = multiprocessing.Pipe()
        child = multiprocessing.Process(
            target=_runner, args=(self.path, child_conn, target, args, kwargs)
        )
        logger.debug("[pid=%d] set up chroot", os.getpid())
        try:
            self._setup()
            child.start()
            res, err = parent_conn.recv()
            child.join()
        finally:
            logger.debug("[pid=%d] clean up chroot", os.getpid())
            self._cleanup()

        if isinstance(err, str):
            raise errors.ChrootExecutionError(err)

        return res
