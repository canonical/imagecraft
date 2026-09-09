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

Written to the root partition's prime directory before it is formatted, so
``mke2fs -d`` embeds the result directly. ``/boot/grub/grub.cfg`` is
generated separately by :mod:`imagecraft.pack.bootloader.mkconfig`.
"""

from pathlib import Path
from uuid import UUID

_DEFAULT_FSTAB_OPTIONS = "defaults,errors=remount-ro"


def configure_fstab(root_dir: Path, root_uuid: UUID | str) -> None:
    """Ensure /etc/fstab contains an entry for the root filesystem UUID.

    An existing non-comment root entry (e.g. ``LABEL=writable / ...``) is
    replaced rather than duplicated.
    """
    fstab_path = root_dir / "etc" / "fstab"
    fstab_path.parent.mkdir(parents=True, exist_ok=True)
    str_uuid = str(root_uuid)
    fstab_entry = f"UUID={str_uuid} / ext4 {_DEFAULT_FSTAB_OPTIONS} 0 1\n"

    if not fstab_path.is_file():
        content = "# /etc/fstab: static file system information.\n" + fstab_entry
        fstab_path.write_text(content)
        return

    existing_content = fstab_path.read_text()
    if str_uuid in existing_content:
        return

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
            return

    separator = "" if existing_content.endswith("\n") else "\n"
    fstab_path.write_text(existing_content + separator + fstab_entry)
