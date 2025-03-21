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

import abc
import logging
import multiprocessing
import os
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, NamedTuple

from craft_parts.utils import os_utils

from . import errors

logger = logging.getLogger(__name__)


class Mount(NamedTuple):
    """Mount entry for chroot setup."""

    fstype: str | None
    src: str
    mountpoint: str
    options: list[str] | None


class Chroot(abc.ABC):
    """Chroot class able to chroot in a directory to execute commands."""

    mounts: list[Mount]
    path: Path

    @abc.abstractmethod
    def _setup_chroot(self, path: Path) -> None:
        """Prepare the chroot environment before executing the target function."""

    @abc.abstractmethod
    def _cleanup_chroot(self, path: Path) -> None:
        """Clean the chroot environment after executing the target function."""

    def chroot(self, target: Callable, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        """Execute a callable in a chroot environment.

        :param path: The new filesystem root.
        :param target: The callable to run in the chroot environment.
        :param args: Arguments for target.
        :param kwargs: Keyword arguments for target.

        :returns: The target function return value.
        """
        logger.debug("[pid=%d] parent process", os.getpid())
        parent_conn, child_conn = multiprocessing.Pipe()
        child = multiprocessing.Process(
            target=_runner, args=(Path(self.path), child_conn, target, args, kwargs)
        )
        logger.debug("[pid=%d] set up chroot", os.getpid())
        self._setup_chroot(self.path)
        try:
            child.start()
            res, err = parent_conn.recv()
            child.join()
        finally:
            logger.debug("[pid=%d] clean up chroot", os.getpid())
            self._cleanup_chroot(self.path)

        if isinstance(err, str):
            raise errors.OverlayChrootExecutionError(err)

        return res


def _runner(
    path: Path,
    conn: Connection,
    target: Callable,
    args: tuple,
    kwargs: dict,
) -> None:
    """Chroot to the execution directory and call the target function."""
    logger.debug("[pid=%d] child process: target=%r", os.getpid(), target)
    try:
        logger.debug("[pid=%d] chroot to %r", os.getpid(), path)
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
    Mount(None, "/etc/resolv.conf", "/etc/resolv.conf", ["--bind"]),
    Mount("proc", "proc", "/proc", None),
    Mount("sysfs", "sysfs", "/sys", None),
    # Device nodes require MS_REC to be bind mounted inside a container.
    Mount(None, "/dev", "/dev", ["--rbind", "--make-rprivate"]),
]


class LinuxChroot(Chroot):
    """Linux chroot manager."""

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

        pid = os.getpid()
        for entry in self.mounts:
            args = []
            if entry.options:
                args.extend(entry.options)
            if entry.fstype:
                args.append(f"-t{entry.fstype}")

            mountpoint = self.path / entry.mountpoint.lstrip("/")

            # Only mount if mountpoint exists.
            if mountpoint.exists():
                logger.debug("[pid=%d] mount %r on chroot", pid, str(mountpoint))
                os_utils.mount(entry.src, str(mountpoint), *args)
            else:
                logger.debug(
                    "[pid=%d] mountpoint %r does not exist", pid, str(mountpoint)
                )

        logger.debug("chroot setup complete")

    def _cleanup_chroot(self) -> None:
        """Chroot environment cleanup."""
        logger.debug("cleanup chroot: %r", self.path)
        pid = os.getpid()
        for entry in reversed(self.mounts):
            mountpoint = self.path / entry.mountpoint.lstrip("/")

            if mountpoint.exists():
                logger.debug("[pid=%d] umount: %r", pid, str(mountpoint))
                if entry.options and "--rbind" in entry.options:
                    # Mount points under /dev may be in use and make the bind mount
                    # unmountable. This may happen in destructive mode depending on
                    # the host environment, so use MNT_DETACH to defer unmounting.
                    os_utils.umount(str(mountpoint), "--recursive", "--lazy")
                else:
                    os_utils.umount(str(mountpoint))
