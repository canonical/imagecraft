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

import multiprocessing
from pathlib import Path
from unittest.mock import ANY, call

import pytest
from imagecraft import errors
from imagecraft.pack.chroot import Chroot, Mount, _runner


def target_func(content: str) -> str:
    Path("foo.txt").write_text(content)
    return "1337"


@pytest.mark.usefixtures("new_dir")
class TestChroot:
    """Fork process and execute in chroot."""

    def test_chroot(self, mocker, new_dir, mock_chroot):
        mock_mount = mocker.patch("imagecraft.pack.chroot.os_utils.mount")
        mock_umount = mocker.patch("imagecraft.pack.chroot.os_utils.umount")

        spy_process = mocker.spy(multiprocessing, "Process")
        new_root = Path(new_dir, "dir1")

        new_root.mkdir()
        for subdir in ["etc", "proc", "sys", "dev"]:
            Path(new_root, subdir).mkdir()

        mounts: list[Mount] = [
            Mount(fstype="proc", src="proc-build", relative_mountpoint="proc"),
        ]

        chroot = Chroot(path=new_root, mounts=mounts)

        chroot.execute(
            target=target_func,
            content="content",
        )

        assert (new_root / Path("foo.txt")).read_text() == "content"
        assert spy_process.mock_calls == [
            call(
                target=_runner,
                args=(new_root, ANY, target_func, (), {"content": "content"}),
            )
        ]
        assert mock_mount.mock_calls == [
            call("proc-build", f"{new_root}/proc", "-tproc"),
            call(f"{new_root}/proc", "--make-rprivate"),
        ]
        assert mock_umount.mock_calls == [
            call(f"{new_root}/proc", "--recursive"),
        ]


@pytest.fixture
def relative_path():
    return "/relative"


@pytest.fixture
def mount_call_test1(request, new_dir, relative_path):
    return (
        Mount(
            fstype=None,
            src="/test",
            relative_mountpoint=request.getfixturevalue("relative_path"),
        ),
        call(
            "/test",
            f"{request.getfixturevalue('new_dir')}{request.getfixturevalue('relative_path')}",
        ),
    )


@pytest.fixture
def mount_call_test2(request, new_dir, relative_path):
    return (
        Mount(
            fstype="proc",
            src="/test",
            relative_mountpoint=request.getfixturevalue("relative_path"),
        ),
        call(
            "/test",
            f"{request.getfixturevalue('new_dir')}{request.getfixturevalue('relative_path')}",
            "-tproc",
        ),
    )


@pytest.fixture
def mount_call_test3(request, new_dir, relative_path):
    return (
        Mount(
            fstype="devpts",
            src="devpts-build",
            relative_mountpoint=request.getfixturevalue("relative_path"),
            options=["-o", "nodev,nosuid"],
        ),
        call(
            "devpts-build",
            f"{request.getfixturevalue('new_dir')}{request.getfixturevalue('relative_path')}",
            "-o",
            "nodev,nosuid",
            "-tdevpts",
        ),
    )


@pytest.mark.usefixtures("new_dir")
class TestMount:
    """Handle a mounting/umounting of a directory."""

    @pytest.mark.parametrize(
        ("mount_call"),
        [
            "mount_call_test1",
            "mount_call_test2",
            "mount_call_test3",
        ],
    )
    def test_mount(self, mocker, request, new_dir, relative_path, mount_call):
        (new_dir / relative_path).mkdir()
        mock_mount = mocker.patch("imagecraft.pack.chroot.os_utils.mount")
        mount, received_call = request.getfixturevalue(mount_call)
        mount.mount(base_path=new_dir)
        assert mock_mount.mock_calls == [received_call]

    def test_mount_missing_dir(self, mocker, new_dir):
        mocker.patch("imagecraft.pack.chroot.os_utils.mount")

        mount = Mount(fstype=None, src="source", relative_mountpoint="/destination")

        with pytest.raises(errors.ChrootExecutionError) as raised:
            mount.mount(base_path=new_dir / "inexistent")
        assert (
            str(raised.value)
            == f"mountpoint {new_dir}/inexistent/destination does not exist."
        )
