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
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from craft_cli import emit
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
        mountpoint: Path | None = None,
    ) -> None:
        self._fstype = fstype
        self._src = src
        self._relative_mountpoint = relative_mountpoint
        if options:
            self._options = options
        if mountpoint:
            self._mountpoint = mountpoint

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
        # Only mount if mountpoint exists.
        emit.debug(f"Mount {self._src} on {str(self._mountpoint)}")
        logger.debug("[pid=%d] mount %r on chroot", pid, str(self._mountpoint))
        if self._mountpoint.exists():
            logger.debug("[pid=%d] mount %r on chroot", pid, str(self._mountpoint))
            os_utils.mount(self._src, str(self._mountpoint), *args)
        else:
            logger.debug(
                "[pid=%d] mountpoint %r does not exist", pid, str(self._mountpoint)
            )

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


# Default essential filesystems to mount in order to have basic utilities and
# name resolution working inside the chroot environment.
default_linux_mounts: list[Mount] = [
    Mount(
        fstype=None,
        src="/etc/resolv.conf",
        relative_mountpoint="/etc/resolv.conf",
        options=["--bind"],
    ),
    Mount(fstype="proc", src="proc", relative_mountpoint="/proc", options=None),
    Mount(fstype="sysfs", src="sysfs", relative_mountpoint="/sys", options=None),
    # Device nodes require MS_REC to be bind mounted inside a container.
    Mount(
        fstype=None,
        src="/dev",
        relative_mountpoint="/dev",
        options=["--rbind", "--make-rprivate"],
    ),
]


class Chroot:
    """Chroot manager."""

    mounts: list[Mount]
    path: Path

    def __init__(
        self, *, path: Path, mounts: list[Mount] = default_linux_mounts
    ) -> None:
        self.path = path
        self.mounts = mounts

    def _setup_chroot(self) -> None:
        """Chroot environment preparation."""
        # Some images (such as cloudimgs) symlink ``/etc/resolv.conf`` to
        # ``/run/systemd/resolve/stub-resolv.conf``. We want resolv.conf to be
        # a regular file to bind-mount the host resolver configuration on.
        #
        # There's no need to restore the file to its original condition because
        # this operation happens on a temporary filesystem layer.
        logger.debug("setup chroot: %r", self.path)
        resolv_conf = self.path / "etc/resolv.conf"
        if resolv_conf.is_symlink():
            resolv_conf.unlink()
            resolv_conf.touch()
        elif not resolv_conf.exists() and resolv_conf.parent.is_dir():
            resolv_conf.touch()

        for entry in self.mounts:
            entry.mount(base_path=self.path)

        logger.debug("chroot setup complete")

    def _cleanup_chroot(self) -> None:
        """Chroot environment cleanup."""
        logger.debug("cleanup chroot: %r", self.path)
        for entry in reversed(self.mounts):
            entry.umount()

    def chroot(
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
        self._setup_chroot()
        try:
            child.start()
            res, err = parent_conn.recv()
            child.join()
        finally:
            logger.debug("[pid=%d] clean up chroot", os.getpid())
            self._cleanup_chroot()

        if isinstance(err, str):
            raise errors.ChrootExecutionError(err)

        return res
