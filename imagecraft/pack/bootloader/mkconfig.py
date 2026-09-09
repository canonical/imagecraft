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
the image by ``mke2fs -d``), rather than rendering a config ourselves. The
GRUB device/UUID variables are preset via a transient
``/etc/default/grub.d`` snippet so ``grub-mkconfig`` doesn't probe the build
host's devices for the chroot's ``/``.
"""

import os
from pathlib import Path
from uuid import UUID

from craft_cli import emit

from imagecraft.pack.bootloader.chrootenv import (
    CHROOT_IMAGE_DEVICE,
    build_prime_chroot,
    find_chroot_binary,
    run_checked,
)

_OS_PROBER = Path("/etc/grub.d/30_os-prober")
_GRUB_DEFAULTS_SNIPPET = Path("/etc/default/grub.d/60-imagecraft.cfg")


def _generate_grub_cfg_in_chroot(*, mkconfig: str, grub_defaults: str) -> None:
    """Generate grub.cfg inside the chroot.

    Must be a top-level function so it can be pickled into the chroot child
    process.

    :param mkconfig: In-chroot path to grub-mkconfig.
    :param grub_defaults: Content for a transient /etc/default/grub.d snippet.
    :raises errors.BootloaderError: If grub-mkconfig fails.
    """
    _GRUB_DEFAULTS_SNIPPET.parent.mkdir(parents=True, exist_ok=True)
    _GRUB_DEFAULTS_SNIPPET.write_text(grub_defaults)
    # Disable os-prober so it doesn't scan the build host's devices and write
    # bogus entries (the historical flow used dpkg-divert for this). The
    # original permissions are restored afterwards.
    prober_was_executable = _OS_PROBER.is_file() and os.access(_OS_PROBER, os.X_OK)
    if prober_was_executable:
        _OS_PROBER.chmod(0o644)
    try:
        Path("/boot/grub").mkdir(parents=True, exist_ok=True)
        run_checked([mkconfig, "-o", "/boot/grub/grub.cfg"])
    finally:
        _GRUB_DEFAULTS_SNIPPET.unlink(missing_ok=True)
        if prober_was_executable:
            _OS_PROBER.chmod(0o755)


def generate_grub_cfg(
    root_dir: Path,
    root_uuid: UUID | str,
    *,
    boot_dir: Path | None = None,
    image_path: Path | None = None,
) -> Path:
    """Generate /boot/grub/grub.cfg using the guest rootfs's grub-mkconfig.

    :param root_dir: Prime directory of the root filesystem partition.
    :param root_uuid: UUID that will be assigned to the root filesystem when
        it's formatted; baked into the generated config's ``root=`` and
        ``search --fs-uuid`` directives.
    :param boot_dir: Prime directory of a dedicated ``/boot`` partition,
        bound at ``/boot`` in the chroot. Defaults to the root partition's
        own ``/boot``.
    :param image_path: If given, the raw disk image is exposed at
        ``/dev/image`` in the chroot.
    :return: Host-side path of the generated grub.cfg.
    :raises errors.BootloaderToolsMissingError: If grub-mkconfig isn't
        present in the staged rootfs.
    """
    mkconfig = find_chroot_binary(root_dir, "grub-mkconfig")

    # Preset the device/UUID variables grub-mkconfig would otherwise probe
    # from the chroot's / (which lives on the build host's filesystem).
    grub_defaults = (
        f"GRUB_DEVICE={CHROOT_IMAGE_DEVICE}\n"
        f"GRUB_DEVICE_UUID={root_uuid}\n"
        f"GRUB_DEVICE_BOOT={CHROOT_IMAGE_DEVICE}\n"
        f"GRUB_DEVICE_BOOT_UUID={root_uuid}\n"
        "GRUB_FS=ext4\n"
        "GRUB_DISABLE_OS_PROBER=true\n"
    )

    chroot = build_prime_chroot(root_dir, image_path=image_path, boot_dir=boot_dir)
    chroot.execute(
        target=_generate_grub_cfg_in_chroot,
        mkconfig=mkconfig,
        grub_defaults=grub_defaults,
    )

    effective_boot_dir = boot_dir if boot_dir is not None else root_dir / "boot"
    grub_cfg_path = effective_boot_dir / "grub" / "grub.cfg"
    emit.debug(f"Generated {grub_cfg_path} with grub-mkconfig")
    return grub_cfg_path
