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

"""Non-EFI (legacy BIOS) bootloader installation via an in-chroot GRUB setup.

Runs GRUB's own tooling (``grub-mkimage`` and ``grub-bios-setup``) inside a
chroot rooted at the root partition's prime directory, with the raw disk
image bind-mounted into the chroot at ``/dev/image``. ``grub-bios-setup``
then writes ``boot.img`` to Sector 0 and embeds ``core.img`` into the
post-MBR gap (MBR) or BIOS Boot partition (GPT) itself, so no custom
byte-level patching or loop devices are needed.
"""

import subprocess
from pathlib import Path
from uuid import UUID

from imagecraft import errors
from imagecraft.pack.bootloader.config import render_early_cfg
from imagecraft.pack.bootloader.const import CORE_BIOS_MODULES
from imagecraft.pack.bootloader.fs import safe_copytree
from imagecraft.pack.bootloader.models import NonEfiInstallResult
from imagecraft.pack.chroot import Chroot, Mount

_GRUB_BIOS_FORMAT = "i386-pc"
_CHROOT_IMAGE_DEVICE = "/dev/image"
_CHROOT_WORK_DIR = "/tmp/grub-bios"  # noqa: S108


def _bios_mod_dir(root_dir: Path) -> Path:
    """Return the path to the rootfs's installed i386-pc GRUB module directory."""
    return root_dir / "usr" / "lib" / "grub" / _GRUB_BIOS_FORMAT


def stage_non_efi_modules(root_dir: Path, boot_dir: Path | None = None) -> Path:
    """Stage BIOS GRUB runtime modules into the ``/boot`` prime directory.

    Must be called *before* the partitions are formatted (unlike the rest of
    this module, which writes to the raw image file after formatting), since
    it writes into a prime directory that ``diskutil.format_device`` will
    later embed via ``mke2fs -d``.

    :param root_dir: Prime directory of the root filesystem partition (used
        to locate the rootfs's installed GRUB modules).
    :param boot_dir: Prime directory that corresponds to ``/boot``. Defaults
        to ``root_dir / "boot"`` when ``/boot`` isn't a dedicated partition.
    :return: The directory the modules were copied into.
    :raises errors.BootloaderToolsMissingError: If the GRUB BIOS modules
        directory isn't present in the staged rootfs.
    """
    mod_dir = _bios_mod_dir(root_dir)
    if not mod_dir.is_dir():
        raise errors.BootloaderToolsMissingError(
            f"GRUB BIOS modules directory not found: {mod_dir}"
        )

    effective_boot_dir = boot_dir if boot_dir is not None else root_dir / "boot"
    target_mod_dir = effective_boot_dir / "grub" / _GRUB_BIOS_FORMAT
    safe_copytree(mod_dir, target_mod_dir)
    return target_mod_dir


def _find_chroot_binary(root_dir: Path, name: str) -> str:
    """Locate a GRUB tool binary in the guest rootfs.

    :param root_dir: Prime directory of the root filesystem partition.
    :param name: Binary name (e.g. ``grub-mkimage``).
    :return: The binary's absolute path *inside* the chroot.
    :raises errors.BootloaderToolsMissingError: If the binary isn't present
        in the staged rootfs.
    """
    for prefix in ("/usr/sbin", "/usr/bin", "/sbin", "/bin"):
        candidate = f"{prefix}/{name}"
        if (root_dir / candidate.lstrip("/")).is_file():
            return candidate
    raise errors.BootloaderToolsMissingError(
        f"{name} not found in the staged rootfs",
        resolution="Install the grub-pc and grub2-common packages in the image.",
    )


def _run_grub_command(cmd: list[str]) -> None:
    """Run a GRUB command inside the chroot, wrapping failures.

    :raises errors.BootloaderError: If the command exits non-zero.
    """
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as err:
        raise errors.BootloaderError(
            f"Command {' '.join(cmd)!r} failed in chroot: "
            f"{err.stderr.strip() or err.stdout.strip()}"
        ) from err


def _install_boot_code_in_chroot(
    *, early_cfg_content: str, modules: list[str], mkimage: str, bios_setup: str
) -> None:
    """Build core.img and write the BIOS boot code to /dev/image.

    Runs entirely inside the chroot. Must be a top-level function so it can
    be pickled into the chroot child process.

    :param early_cfg_content: Rendered early GRUB config content.
    :param modules: GRUB modules to embed in core.img.
    :param mkimage: In-chroot path to grub-mkimage.
    :param bios_setup: In-chroot path to grub-bios-setup.
    :raises errors.BootloaderError: If any GRUB command fails.
    """
    mod_dir = f"/usr/lib/grub/{_GRUB_BIOS_FORMAT}"
    work_dir = Path(_CHROOT_WORK_DIR)
    work_dir.mkdir(parents=True, exist_ok=True)
    early_cfg = work_dir / "early.cfg"
    early_cfg.write_text(early_cfg_content)
    device_map = work_dir / "device.map"
    device_map.write_text(f"(hd0)\t{_CHROOT_IMAGE_DEVICE}\n")

    core_img = f"{mod_dir}/core.img"
    commands = [
        [
            mkimage,
            "-d",
            mod_dir,
            "-O",
            _GRUB_BIOS_FORMAT,
            "-o",
            core_img,
            "-p",
            "/boot/grub",
            "-c",
            str(early_cfg),
            *modules,
        ],
        [
            bios_setup,
            "--skip-fs-probe",
            "-m",
            str(device_map),
            "-d",
            mod_dir,
            _CHROOT_IMAGE_DEVICE,
        ],
    ]
    for cmd in commands:
        _run_grub_command(cmd)


class NonEfiInstaller:
    """Installs the BIOS (``i386-pc``) bootloader using in-chroot GRUB tools.

    Only the amd64/i386 ``i386-pc`` target is currently supported; there is
    no non-EFI target for arm64/armhf/riscv64 in this package (those
    architectures always boot via EFI).
    """

    def __init__(
        self,
        *,
        image_path: Path,
        root_dir: Path,
        root_uuid: UUID | str,
    ) -> None:
        """Initialize the non-EFI bootloader installer.

        :param image_path: Path to the raw, partitioned disk image file.
        :param root_dir: Prime directory of the root filesystem partition.
            Used as the chroot root; GRUB modules and tools come from here.
        :param root_uuid: UUID assigned to the root filesystem.
        """
        self.image_path = image_path
        self.root_dir = root_dir
        self.root_uuid = str(root_uuid)

    def _prepare_chroot(self) -> Chroot:
        """Set up the chroot with the image exposed at ``/dev/image``.

        Rather than overmounting ``/dev`` (which would hide the bind-mount
        targets), only the device files GRUB needs are bind-mounted in.
        """
        for mountpoint in ("proc", "sys", "dev"):
            (self.root_dir / mountpoint).mkdir(parents=True, exist_ok=True)
        for device in ("null", "zero", "urandom", "image"):
            (self.root_dir / "dev" / device).touch(exist_ok=True)

        mounts = [
            Mount(fstype="proc", src="proc-build", relative_mountpoint="/proc"),
            Mount(fstype="sysfs", src="sysfs-build", relative_mountpoint="/sys"),
            *(
                Mount(
                    fstype=None,
                    src=f"/dev/{device}",
                    relative_mountpoint=f"/dev/{device}",
                    options=["--bind"],
                )
                for device in ("null", "zero", "urandom")
            ),
            Mount(
                fstype=None,
                src=str(self.image_path.resolve()),
                relative_mountpoint=_CHROOT_IMAGE_DEVICE,
                options=["--bind"],
            ),
        ]
        return Chroot(path=self.root_dir, mounts=mounts)

    def install(self) -> NonEfiInstallResult:
        """Build core.img and install the BIOS boot code into the disk image.

        Assumes :func:`stage_non_efi_modules` has already been called during
        the pre-format staging phase to place GRUB runtime modules into the
        boot partition's prime directory.

        :raises errors.BootloaderToolsMissingError: If GRUB modules, boot.img,
            or the GRUB tools themselves aren't present in the staged rootfs.
        """
        mod_dir = _bios_mod_dir(self.root_dir)
        if not mod_dir.is_dir():
            raise errors.BootloaderToolsMissingError(
                f"GRUB BIOS modules directory not found: {mod_dir}"
            )
        boot_img_file = mod_dir / "boot.img"
        if not boot_img_file.is_file():
            raise errors.BootloaderToolsMissingError(
                f"GRUB stage 1 boot.img not found: {boot_img_file}"
            )
        mkimage = _find_chroot_binary(self.root_dir, "grub-mkimage")
        bios_setup = _find_chroot_binary(self.root_dir, "grub-bios-setup")

        modules = [m for m in CORE_BIOS_MODULES if (mod_dir / f"{m}.mod").is_file()]

        chroot = self._prepare_chroot()
        chroot.execute(
            target=_install_boot_code_in_chroot,
            early_cfg_content=render_early_cfg(self.root_uuid),
            modules=modules,
            mkimage=mkimage,
            bios_setup=bios_setup,
        )

        core_img = mod_dir / "core.img"
        return NonEfiInstallResult(
            format=_GRUB_BIOS_FORMAT,
            core_img_size_bytes=core_img.stat().st_size if core_img.is_file() else 0,
            installed_files=[core_img] if core_img.is_file() else [],
            modules_installed=True,
        )


def install_non_efi(
    *,
    image_path: Path,
    root_dir: Path,
    root_uuid: UUID | str,
) -> NonEfiInstallResult:
    """Install the BIOS bootloader into a raw disk image.

    :param image_path: Path to the raw, partitioned disk image file.
    :param root_dir: Prime directory of the root filesystem partition.
    :param root_uuid: UUID assigned to the root filesystem.
    :return: NonEfiInstallResult.
    """
    installer = NonEfiInstaller(
        image_path=image_path,
        root_dir=root_dir,
        root_uuid=root_uuid,
    )
    return installer.install()
