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

"""Generation of ``/boot/grub/grub.cfg`` with the guest's own grub-mkconfig.

Runs ``grub-mkconfig`` inside a chroot rooted at the root partition's prime
directory (before formatting, so the resulting ``grub.cfg`` is embedded into
the image by ``mke2fs -d``).

``grub-mkconfig`` and its helper scripts unconditionally probe the chroot's
``/`` and ``/boot`` with ``grub-probe``, which cannot resolve a plain
directory on the build host to a block device (the backing device node is
typically not even available inside unprivileged build containers). The
chroot therefore gets a small ``grub-probe`` shim bind-mounted over the
guest's binary, answering device/fs queries with the values of the image
being built.
"""

import contextlib
import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

from craft_cli import emit

from imagecraft.pack.bootloader.chrootenv import (
    require_chroot_binary,
    run_checked,
)
from imagecraft.pack.chroot import Mount, build_prime_chroot

_GRUB_DEFAULTS_SNIPPET = Path("/etc/default/grub.d/60-imagecraft.cfg")
# grub scripts only need GRUB_DEVICE to exist (e.g. ``test -e``); the actual
# device identity in the generated config comes from the UUID overrides.
_CHROOT_FAKE_DEVICE = Path("/image")
_CHROOT_FAKE_BOOT_DEVICE = Path("/image-boot")
_SHIM_LOG = Path("/tmp/grub-probe-shim.log")  # noqa: S108

# grub.cfg directives that carry paths into the /boot filesystem. With a
# dedicated /boot partition those paths must be relative to the boot
# filesystem's root (i.e. the /boot prefix is stripped).
_BOOT_PATH_DIRECTIVES = (
    "linux",
    "initrd",
    "devicetree",
    "multiboot2",
    "multiboot",
    "module2",
    "module",
    "loadfont",
)

# Shim answering the grub-probe queries made by grub-mkconfig and the
# /etc/grub.d scripts with the values of the image being built. Note that
# the real grub-probe exits 0 with empty output when there's simply nothing
# to report (e.g. no abstraction layers), and several callers rely on that
# under ``set -e`` -- so unknown/empty queries must also exit 0 with no
# output, and only hard errors may fail.
_GRUB_PROBE_SHIM = """\
#!/bin/sh
device=""
target=""
path=""
while [ $# -gt 0 ]; do
  case "$1" in
    --device) device="$2"; shift 2 ;;
    --device=*) device="${1#--device=}"; shift ;;
    --target=*) target="${1#--target=}"; shift ;;
    -t) target="$2"; shift 2 ;;
    --*) shift ;;
    *) path="$1"; shift ;;
  esac
done
echo "device=$device target=$target path=$path" >> %(shim_log)s
case "$target" in
  device)
    if [ "$path" = "/boot" ]; then echo "%(boot_device)s"; else echo "%(root_device)s"; fi
    ;;
  fs) echo "ext2" ;;
  fs_uuid)
    if [ "$device" = "%(boot_device)s" ]; then echo "%(boot_uuid)s"; else echo "%(root_uuid)s"; fi
    ;;
  drive) echo "(hd0)" ;;
  partmap) echo "%(partmap)s" ;;
esac
exit 0
"""


def _generate_grub_cfg_in_chroot(
    *, grub_defaults: str, root_uuid: str, boot_uuid: str | None
) -> str:
    """Generate grub.cfg inside the chroot and return mkconfig's output.

    Must be a top-level function so it can be pickled into the chroot child
    process.

    :raises errors.BootloaderError: If grub-mkconfig fails.
    """
    _GRUB_DEFAULTS_SNIPPET.parent.mkdir(parents=True, exist_ok=True)
    # The staged rootfs may already ship this file; restore it afterwards
    # rather than deleting project-provided configuration.
    previous_defaults = (
        _GRUB_DEFAULTS_SNIPPET.read_text() if _GRUB_DEFAULTS_SNIPPET.exists() else None
    )
    _GRUB_DEFAULTS_SNIPPET.write_text(grub_defaults)
    _CHROOT_FAKE_DEVICE.touch(exist_ok=True)
    # 10_linux only emits root=UUID= if /dev/disk/by-uuid/<uuid> exists.
    by_uuid_dir = Path("/dev/disk/by-uuid")
    by_uuid_dir.mkdir(parents=True, exist_ok=True)
    by_uuid_root = by_uuid_dir / root_uuid
    by_uuid_root.symlink_to(_CHROOT_FAKE_DEVICE)
    created = [_CHROOT_FAKE_DEVICE, by_uuid_root]
    if boot_uuid is not None:
        _CHROOT_FAKE_BOOT_DEVICE.touch(exist_ok=True)
        by_uuid_boot = by_uuid_dir / boot_uuid
        by_uuid_boot.symlink_to(_CHROOT_FAKE_BOOT_DEVICE)
        created += [_CHROOT_FAKE_BOOT_DEVICE, by_uuid_boot]
    try:
        Path("/boot/grub").mkdir(parents=True, exist_ok=True)
        proc = run_checked(["grub-mkconfig", "-o", "/boot/grub/grub.cfg"])
        return (proc.stdout + proc.stderr).strip()
    finally:
        for path in created:
            path.unlink(missing_ok=True)
        if previous_defaults is None:
            _GRUB_DEFAULTS_SNIPPET.unlink(missing_ok=True)
        else:
            _GRUB_DEFAULTS_SNIPPET.write_text(previous_defaults)
        # Remove the by-uuid directory if we created it (pre-format, so an
        # empty leftover would leak into the image).
        with contextlib.suppress(OSError):
            by_uuid_dir.rmdir()
            by_uuid_dir.parent.rmdir()


def _fs_internal_path(path: Path) -> str:
    """Return path's location relative to the root of the filesystem hosting it.

    This is the prefix ``grub-mkrelpath`` (run by ``grub-mkconfig`` inside
    the chroot) uses for kernel paths under a bind-mounted ``/boot``.
    """
    resolved = str(path.resolve())
    best_mount = ""
    mountpoint_field_index = 4
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        fields = line.split(" ")
        if len(fields) > mountpoint_field_index:
            mountpoint = fields[mountpoint_field_index].replace("\\040", " ")
            if (
                resolved == mountpoint or resolved.startswith(mountpoint + "/")
            ) and len(mountpoint) > len(best_mount):
                best_mount = mountpoint
    if not best_mount:
        return "/"
    rel = os.path.relpath(resolved, best_mount)
    return "/" if rel == "." else f"/{rel}"


def _strip_boot_prefix(grub_cfg_path: Path, boot_dir: Path) -> None:
    """Make kernel-path directives relative to the boot filesystem's root.

    Needed with a dedicated ``/boot`` partition: grub-mkconfig saw the
    kernels at ``/boot/...`` inside the chroot (or, via ``grub-mkrelpath``,
    under the host-fs-internal path of the bind-mounted boot prime
    directory).
    """
    # Strip the longer (host-fs-internal) prefix first: it may itself end in
    # "/boot/" (e.g. a prime directory named "boot").
    internal = _fs_internal_path(boot_dir).rstrip("/")
    # A "/" internal prefix (boot_dir at a mount root) needs no stripping.
    prefixes = (internal + "/", "/boot/") if internal else ("/boot/",)
    directive_alternation = "|".join(_BOOT_PATH_DIRECTIVES)
    content = grub_cfg_path.read_text()
    for prefix in prefixes:
        pattern = re.compile(
            rf"^(\s*(?:{directive_alternation})\b.*){re.escape(prefix)}",
            re.MULTILINE,
        )
        while True:
            updated, count = pattern.subn(r"\1/", content)
            if not count or updated == content:
                break
            content = updated
    grub_cfg_path.write_text(content)


def generate_grub_cfg(
    root_dir: Path,
    root_uuid: UUID | str,
    *,
    boot_dir: Path | None = None,
    boot_uuid: UUID | str | None = None,
    partition_map: str = "gpt",
) -> Path:
    """Generate /boot/grub/grub.cfg using the guest rootfs's grub-mkconfig.

    :param root_dir: Prime directory of the root filesystem partition.
    :param root_uuid: UUID that will be assigned to the root filesystem;
        baked into the config's ``root=`` and ``search --fs-uuid`` values.
    :param boot_dir: Prime directory of a dedicated ``/boot`` partition,
        bound at ``/boot`` in the chroot.
    :param boot_uuid: UUID that will be assigned to the dedicated ``/boot``
        partition's filesystem, if any.
    :param partition_map: The image's partition table format as GRUB calls
        it (``gpt`` or ``msdos``).
    :return: Host-side path of the generated grub.cfg.
    :raises errors.BootloaderToolsMissingError: If grub-mkconfig isn't
        present in the staged rootfs.
    """
    require_chroot_binary(root_dir, "grub-mkconfig")
    probe_rel = require_chroot_binary(root_dir, "grub-probe")

    root_uuid_str = str(root_uuid)
    boot_uuid_str = str(boot_uuid or root_uuid)
    fake_boot_device = (
        _CHROOT_FAKE_BOOT_DEVICE if boot_uuid is not None else _CHROOT_FAKE_DEVICE
    )
    # Override the values grub-mkconfig probed from the chroot with the
    # pre-generated image UUIDs, and force root=UUID= rather than
    # root=PARTUUID=.
    grub_defaults = (
        f"GRUB_DEVICE={_CHROOT_FAKE_DEVICE}\n"
        f"GRUB_DEVICE_UUID={root_uuid_str}\n"
        f"GRUB_DEVICE_BOOT={fake_boot_device}\n"
        f"GRUB_DEVICE_BOOT_UUID={boot_uuid_str}\n"
        "GRUB_FS=ext4\n"
        "GRUB_DEVICE_PARTUUID=\n"
        "GRUB_DEVICE_BOOT_PARTUUID=\n"
        "GRUB_DISABLE_LINUX_PARTUUID=true\n"
        "GRUB_DISABLE_OS_PROBER=true\n"
    )

    shim_content = _GRUB_PROBE_SHIM % {
        "shim_log": _SHIM_LOG,
        "root_device": _CHROOT_FAKE_DEVICE,
        "boot_device": fake_boot_device,
        "root_uuid": root_uuid_str,
        "boot_uuid": boot_uuid_str,
        "partmap": partition_map,
    }
    with tempfile.NamedTemporaryFile(
        "w", prefix="imagecraft-grub-probe-shim-", suffix=".sh", delete=False
    ) as shim:
        shim.write(shim_content)
        shim_path = Path(shim.name)
    shim_path.chmod(0o755)

    extra_mounts = [
        Mount(
            fstype=None,
            src=str(shim_path),
            relative_mountpoint=f"/{probe_rel}",
            options=["--bind"],
        )
    ]
    chroot = build_prime_chroot(root_dir, boot_dir=boot_dir, extra_mounts=extra_mounts)
    try:
        mkconfig_output = chroot.execute(
            target=_generate_grub_cfg_in_chroot,
            grub_defaults=grub_defaults,
            root_uuid=root_uuid_str,
            boot_uuid=boot_uuid_str if boot_uuid is not None else None,
        )
    finally:
        shim_path.unlink(missing_ok=True)
        shim_log = root_dir / _SHIM_LOG.relative_to("/")
        if shim_log.is_file():
            emit.debug(
                "grub-probe shim answered: "
                + ", ".join(sorted(set(shim_log.read_text().splitlines())))
            )
            shim_log.unlink()

    grub_cfg_path = (boot_dir or root_dir / "boot") / "grub" / "grub.cfg"
    if boot_dir is not None:
        _strip_boot_prefix(grub_cfg_path, boot_dir)
    if mkconfig_output:
        # grub-mkconfig logs its progress ("Generating grub configuration
        # file ...", menu entries added, ...) to the craft log.
        emit.debug(mkconfig_output)
    emit.debug(f"Generated {grub_cfg_path} with grub-mkconfig")
    return grub_cfg_path
