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
the image by ``mke2fs -d``), rather than rendering a config ourselves.

``grub-mkconfig`` and its helper scripts unconditionally probe the chroot's
``/`` and ``/boot`` with ``grub-probe``, which cannot resolve a plain
directory on the build host to a block device (the backing device node is
typically not even available inside unprivileged build containers). The
chroot therefore gets a small ``grub-probe`` shim bind-mounted over the
guest's binary, answering device/fs queries with the values of the image
being built. The ``/etc/default/grub.d`` snippet with the pre-generated
filesystem UUIDs is belt-and-braces for the values sourced from it.
"""

import os
import re
import tempfile
from pathlib import Path
from uuid import UUID

from craft_cli import emit

from imagecraft.pack.bootloader.chrootenv import (
    build_prime_chroot,
    find_chroot_binary,
    run_checked,
)
from imagecraft.pack.chroot import Mount

_OS_PROBER = Path("/etc/grub.d/30_os-prober")
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
    *, mkconfig: str, grub_defaults: str, root_uuid: str, boot_uuid: str | None
) -> str:
    """Generate grub.cfg inside the chroot.

    Must be a top-level function so it can be pickled into the chroot child
    process.

    :param mkconfig: In-chroot path to grub-mkconfig.
    :param grub_defaults: Content for a transient /etc/default/grub.d snippet.
    :param root_uuid: UUID of the root filesystem.
    :param boot_uuid: UUID of the dedicated ``/boot`` filesystem, if any.
    :return: grub-mkconfig's combined output (for logging).
    :raises errors.BootloaderError: If grub-mkconfig fails.
    """
    _GRUB_DEFAULTS_SNIPPET.parent.mkdir(parents=True, exist_ok=True)
    _GRUB_DEFAULTS_SNIPPET.write_text(grub_defaults)
    _CHROOT_FAKE_DEVICE.touch(exist_ok=True)
    if boot_uuid is not None:
        _CHROOT_FAKE_BOOT_DEVICE.touch(exist_ok=True)
    # 10_linux only emits root=UUID= if /dev/disk/by-uuid/<uuid> exists.
    by_uuid_dir = Path("/dev/disk/by-uuid")
    by_uuid_dir.mkdir(parents=True, exist_ok=True)
    by_uuid_root = by_uuid_dir / root_uuid
    by_uuid_root.symlink_to(str(_CHROOT_FAKE_DEVICE))
    by_uuid_boot = None
    if boot_uuid is not None:
        by_uuid_boot = by_uuid_dir / boot_uuid
        by_uuid_boot.symlink_to(str(_CHROOT_FAKE_BOOT_DEVICE))
    Path("/dev/disk/by-partuuid").mkdir(exist_ok=True)
    # Disable os-prober so it doesn't scan the build host's devices and write
    # bogus entries (the historical flow used dpkg-divert for this). The
    # original permissions are restored afterwards.
    prober_was_executable = _OS_PROBER.is_file() and os.access(_OS_PROBER, os.X_OK)
    if prober_was_executable:
        _OS_PROBER.chmod(0o644)
    try:
        Path("/boot/grub").mkdir(parents=True, exist_ok=True)
        proc = run_checked([mkconfig, "-o", "/boot/grub/grub.cfg"])
        return (proc.stdout + proc.stderr).strip()
    finally:
        _GRUB_DEFAULTS_SNIPPET.unlink(missing_ok=True)
        _CHROOT_FAKE_DEVICE.unlink(missing_ok=True)
        _CHROOT_FAKE_BOOT_DEVICE.unlink(missing_ok=True)
        by_uuid_root.unlink(missing_ok=True)
        if by_uuid_boot is not None:
            by_uuid_boot.unlink(missing_ok=True)
        if prober_was_executable:
            _OS_PROBER.chmod(0o755)


def _fs_internal_path(path: Path) -> str:
    """Return path's location relative to the root of the filesystem hosting it.

    Matches the ``root`` field the kernel reports in mountinfo for a bind
    mount of this directory -- which is what ``grub-mkrelpath`` (run by
    ``grub-mkconfig`` inside the chroot) ends up using as the prefix for
    kernel paths under a bind-mounted ``/boot``.
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
    """Fix kernel-path directives in grub.cfg for a dedicated /boot partition.

    grub-mkconfig saw the kernels at ``/boot/...`` inside the chroot (or, via
    ``grub-mkrelpath``'s mountinfo parsing, under the host-fs-internal path of
    the bind-mounted boot prime directory), but at boot time GRUB reads them
    relative to the boot filesystem's root.
    """
    # Strip the longer (host-fs-internal) prefix first: it may itself end in
    # "/boot/" (e.g. a prime directory named "boot").
    prefixes = (_fs_internal_path(boot_dir).rstrip("/") + "/", "/boot/")
    directive_alternation = "|".join(_BOOT_PATH_DIRECTIVES)
    content = grub_cfg_path.read_text()
    for prefix in prefixes:
        pattern = re.compile(
            rf"^(\s*(?:{directive_alternation})\b.*){re.escape(prefix)}",
            re.MULTILINE,
        )
        while True:
            updated, count = pattern.subn(r"\1/", content)
            if not count:
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
    :param root_uuid: UUID that will be assigned to the root filesystem when
        it's formatted; baked into the generated config's ``root=`` and
        ``search --fs-uuid`` directives.
    :param boot_dir: Prime directory of a dedicated ``/boot`` partition,
        bound at ``/boot`` in the chroot. Defaults to the root partition's
        own ``/boot``.
    :param boot_uuid: UUID that will be assigned to the dedicated ``/boot``
        partition's filesystem, if any.
    :param partition_map: The image's partition table format as GRUB calls
        it (``gpt`` or ``msdos``).
    :return: Host-side path of the generated grub.cfg.
    :raises errors.BootloaderToolsMissingError: If grub-mkconfig isn't
        present in the staged rootfs.
    """
    mkconfig = find_chroot_binary(root_dir, "grub-mkconfig")
    real_probe = find_chroot_binary(root_dir, "grub-probe")

    fake_boot_device = (
        _CHROOT_FAKE_BOOT_DEVICE if boot_uuid is not None else _CHROOT_FAKE_DEVICE
    )
    # Override the values grub-mkconfig probed from the chroot with the
    # pre-generated image UUIDs, and force root=UUID= rather than
    # root=PARTUUID=.
    grub_defaults = (
        f"GRUB_DEVICE={_CHROOT_FAKE_DEVICE}\n"
        f"GRUB_DEVICE_UUID={root_uuid}\n"
        f"GRUB_DEVICE_BOOT={fake_boot_device}\n"
        f"GRUB_DEVICE_BOOT_UUID={boot_uuid or root_uuid}\n"
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
        "root_uuid": str(root_uuid),
        "boot_uuid": str(boot_uuid or root_uuid),
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
            relative_mountpoint=real_probe,
            options=["--bind"],
        )
    ]
    chroot = build_prime_chroot(root_dir, boot_dir=boot_dir, extra_mounts=extra_mounts)
    try:
        mkconfig_output = chroot.execute(
            target=_generate_grub_cfg_in_chroot,
            mkconfig=mkconfig,
            grub_defaults=grub_defaults,
            root_uuid=str(root_uuid),
            boot_uuid=str(boot_uuid) if boot_uuid is not None else None,
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

    effective_boot_dir = boot_dir if boot_dir is not None else root_dir / "boot"
    grub_cfg_path = effective_boot_dir / "grub" / "grub.cfg"
    if boot_dir is not None:
        _strip_boot_prefix(grub_cfg_path, boot_dir)
    if mkconfig_output:
        # grub-mkconfig logs its progress ("Generating grub configuration
        # file ...", menu entries added, ...) to the craft log.
        emit.debug(mkconfig_output)
    emit.debug(f"Generated {grub_cfg_path} with grub-mkconfig")
    return grub_cfg_path
