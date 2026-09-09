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

"""Root filesystem configuration: /etc/fstab.

Writes are made to the root partition's prime directory before it is
formatted, so the resulting files are embedded directly by ``mke2fs -d``.
``/boot/grub/grub.cfg`` is generated separately by
:mod:`imagecraft.pack.bootloader.mkconfig` using the guest's own
``grub-mkconfig``.
"""

from pathlib import Path
from uuid import UUID

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

    # Replace an existing root entry (e.g. a project-provided
    # ``LABEL=writable / ...`` line) rather than appending a second one,
    # which would leave the stale root specification in place.
    lines = existing_content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        fields = line.split()
        if (
            fields
            and not line.lstrip().startswith("#")
            and len(fields) > 1
            and fields[1] == "/"
        ):
            lines[index] = fstab_entry
            fstab_path.write_text("".join(lines))
            return fstab_path, True

    separator = "" if existing_content.endswith("\n") else "\n"
    fstab_path.write_text(existing_content + separator + fstab_entry)
    return fstab_path, True
