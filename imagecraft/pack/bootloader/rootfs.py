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

"""Root filesystem configuration: /etc/fstab and /boot/grub/grub.cfg.

Writes are made to the root partition's prime directory before it is
formatted, so the resulting files are embedded directly by ``mke2fs -d``.
"""

from pathlib import Path
from uuid import UUID

from craft_platforms import DebianArchitecture

from imagecraft.pack.bootloader.config import render_grub_cfg
from imagecraft.pack.bootloader.fs import find_kernel_and_initrd
from imagecraft.pack.bootloader.models import RootfsConfigResult

_DEFAULT_FSTAB_OPTIONS = "defaults,errors=remount-ro"


def configure_fstab(
    root_dir: Path,
    root_uuid: UUID | str,
    *,
    fstype: str = "ext4",
    options: str = _DEFAULT_FSTAB_OPTIONS,
    dump: int = 0,
    passno: int = 1,
) -> tuple[Path, bool]:
    """Ensure /etc/fstab contains an entry for the root filesystem UUID.

    :param root_dir: Prime directory of the root filesystem partition.
    :param root_uuid: UUID that will be assigned to the root filesystem.
    :param fstype: Filesystem type.
    :param options: Mount options.
    :param dump: Dump frequency.
    :param passno: Fsck pass number (1 for root).
    :return: Tuple of (fstab_path, updated).
    """
    fstab_path = root_dir / "etc" / "fstab"
    fstab_path.parent.mkdir(parents=True, exist_ok=True)
    str_uuid = str(root_uuid)
    fstab_entry = f"UUID={str_uuid} / {fstype} {options} {dump} {passno}\n"

    if not fstab_path.is_file():
        content = "# /etc/fstab: static file system information.\n" + fstab_entry
        fstab_path.write_text(content)
        return fstab_path, True

    existing_content = fstab_path.read_text()
    if str_uuid in existing_content:
        return fstab_path, False

    separator = "" if existing_content.endswith("\n") else "\n"
    fstab_path.write_text(existing_content + separator + fstab_entry)
    return fstab_path, True


def configure_grub_cfg(
    root_dir: Path,
    root_uuid: UUID | str,
    arch: DebianArchitecture,
    *,
    console: str | None = None,
    timeout: int = 3,
    default: str = "0",
) -> tuple[Path, bool, str, str]:
    """Render and write /boot/grub/grub.cfg on the root filesystem.

    :param root_dir: Prime directory of the root filesystem partition.
    :param root_uuid: UUID that will be assigned to the root filesystem.
    :param arch: Target architecture.
    :param console: Optional custom kernel console string.
    :param timeout: GRUB boot menu timeout in seconds.
    :param default: Default menu entry index or title.
    :return: Tuple of (target_cfg_path, rendered, vmlinuz_name, initrd_name).
    """
    target_cfg = root_dir / "boot" / "grub" / "grub.cfg"
    target_cfg.parent.mkdir(parents=True, exist_ok=True)

    vmlinuz, initrd = find_kernel_and_initrd(root_dir / "boot")

    content = render_grub_cfg(
        arch=arch.value,
        root_uuid=root_uuid,
        vmlinuz=vmlinuz,
        initrd=initrd,
        console=console,
        timeout=timeout,
        default=default,
    )
    target_cfg.write_text(content)
    return target_cfg, True, vmlinuz, initrd


def configure_rootfs(
    root_dir: Path,
    root_uuid: UUID | str,
    arch: DebianArchitecture,
    *,
    console: str | None = None,
    timeout: int = 3,
    default: str = "0",
) -> RootfsConfigResult:
    """Configure /etc/fstab and /boot/grub/grub.cfg on the root filesystem.

    :param root_dir: Prime directory of the root filesystem partition.
    :param root_uuid: UUID that will be assigned to the root filesystem.
    :param arch: Target architecture.
    :param console: Optional custom kernel console string.
    :param timeout: GRUB boot menu timeout in seconds.
    :param default: Default menu entry index or title.
    """
    cfg_path, rendered, vmlinuz, initrd = configure_grub_cfg(
        root_dir,
        root_uuid,
        arch,
        console=console,
        timeout=timeout,
        default=default,
    )
    fstab_path, fstab_updated = configure_fstab(root_dir, root_uuid)

    return RootfsConfigResult(
        grub_cfg_path=cfg_path,
        grub_cfg_rendered=rendered,
        fstab_path=fstab_path,
        fstab_updated=fstab_updated,
        vmlinuz=vmlinuz,
        initrd=initrd,
    )
