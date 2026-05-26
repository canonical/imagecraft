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

"""Generic raw-content placement for assembled disk images.

A :class:`RawContent` record pairs a source blob with a target location
in the final disk image; :func:`apply_raw_content` ``dd``'s each record
into place after the image has been partitioned and finalised.

This module is deliberately bootloader-agnostic. It is the *mechanism*
("write these bytes to that offset"), not the *policy* ("GRUB's boot.img
belongs in the MBR boot-code region"). Policy lives in the caller — see
:func:`imagecraft.pack.grubutil.grub_raw_content` — which decides what
content to emit and where it lands. Keeping the split means the
disk-writing code stays reusable for any future raw payload (second-stage
bootloaders, vendor blobs, …) without learning the word "GRUB".
"""

import dataclasses
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from craft_cli import emit

from imagecraft.pack import gptutil
from imagecraft.subprocesses import run

if TYPE_CHECKING:
    from collections.abc import Iterable

_SECTOR_SIZE = 512


# ── Target placements ───────────────────────────────────────────────────────


@dataclasses.dataclass(frozen=True)
class MbrBootCode:
    """The MBR boot-code region: bytes ``0..max_bytes`` of the disk.

    Only the first ``max_bytes`` bytes of the source are written, so the
    disk signature and partition table that follow the boot code (bytes
    440..512 on a classic MBR) are left untouched.
    """

    max_bytes: int


@dataclasses.dataclass(frozen=True)
class SectorOffset:
    """A fixed sector offset from the start of the disk.

    Used for content that lives in an unpartitioned gap — e.g. the
    post-MBR gap, which begins at sector 1.
    """

    sector: int
    sector_size: int = _SECTOR_SIZE


@dataclasses.dataclass(frozen=True)
class PartitionStart:
    """The first sector of a named partition.

    The sector offset is resolved against the image's on-disk partition
    table at apply time, so it tracks whatever layout the partitioner
    produced rather than a hard-coded number.
    """

    partition_name: str
    sector_size: int = _SECTOR_SIZE


RawContentTarget = MbrBootCode | SectorOffset | PartitionStart


@dataclasses.dataclass(frozen=True)
class RawContent:
    """A blob to write verbatim to a fixed location in a disk image."""

    source: Path
    target: RawContentTarget
    description: str = ""


# ── Applier ─────────────────────────────────────────────────────────────────


def apply_raw_content(
    *, disk_path: Path, contents: "Iterable[RawContent]"
) -> None:
    """Write each raw-content record into the assembled disk image.

    Uses ``dd ... conv=notrunc`` so the existing image bytes (partition
    table, filesystems) are preserved. Must run *after* the image has
    been partitioned and finalised: :class:`PartitionStart` targets are
    resolved against the on-disk partition table here.
    """
    for item in contents:
        _write_one(disk_path, item)


def _write_one(disk_path: Path, item: RawContent) -> None:
    target = item.target
    label = item.description or item.source.name

    if isinstance(target, MbrBootCode):
        emit.progress(f"Writing {label} to MBR boot code of {disk_path}")
        # bs=1 + count caps the write at the boot-code length so the
        # partition table that follows the boot code is never clobbered.
        _dd(
            source=item.source,
            disk_path=disk_path,
            block_size=1,
            seek=0,
            count=target.max_bytes,
        )
        return

    if isinstance(target, SectorOffset):
        emit.progress(
            f"Writing {label} to sector {target.sector} of {disk_path}"
        )
        _dd(
            source=item.source,
            disk_path=disk_path,
            block_size=target.sector_size,
            seek=target.sector,
        )
        return

    # PartitionStart: resolve the partition's start sector against the
    # actual partition table now that the image is finalised.
    sector = gptutil.get_partition_sector_offset(
        disk_path, target.partition_name
    )
    emit.progress(
        f"Writing {label} to partition {target.partition_name!r} "
        f"at sector {sector} of {disk_path}"
    )
    _dd(
        source=item.source,
        disk_path=disk_path,
        block_size=target.sector_size,
        seek=sector,
    )


def _dd(
    *,
    source: Path,
    disk_path: Path,
    block_size: int,
    seek: int,
    count: int | None = None,
) -> None:
    """Run ``dd`` to write ``source`` into ``disk_path`` non-destructively."""
    args = [
        "dd",
        f"if={source}",
        f"of={disk_path}",
        f"bs={block_size}",
        f"seek={seek}",
        "conv=notrunc",
    ]
    if count is not None:
        args.append(f"count={count}")
    run(*args, stderr=subprocess.STDOUT)
