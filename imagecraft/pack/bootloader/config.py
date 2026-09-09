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

"""Early GRUB search stub configuration generation."""

from uuid import UUID


def render_early_cfg(
    search_uuid: UUID | str, *, boot_prefix: str = "/boot/grub"
) -> str:
    """Render the early GRUB search stub configuration.

    :param search_uuid: UUID of the filesystem holding the GRUB configuration
        (the root filesystem, or the dedicated ``/boot`` partition when one
        exists).
    :param boot_prefix: Path of the GRUB directory relative to the searched
        filesystem's root (``/boot/grub``, or ``/grub`` when ``/boot`` is a
        dedicated partition).
    """
    return (
        f"search.fs_uuid {search_uuid} root\n"
        f"set prefix=($root)'{boot_prefix}'\n"
        "configfile $prefix/grub.cfg\n"
    )
