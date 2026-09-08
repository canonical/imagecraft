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

"""GRUB configuration file generation using Jinja2 templates."""

from uuid import UUID

from jinja2 import Environment, PackageLoader


def _get_jinja_env() -> Environment:
    """Return a configured Jinja2 environment loading templates/ from this package."""
    # These templates render GRUB config files, not HTML, so autoescaping
    # would incorrectly escape shell-like syntax (e.g. quotes in kernel args).
    return Environment(  # noqa: S701
        loader=PackageLoader("imagecraft.pack.bootloader", "templates"),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_early_cfg(root_uuid: UUID | str) -> str:
    """Render the early GRUB search stub configuration.

    :param root_uuid: UUID of the root filesystem to search for.
    """
    env = _get_jinja_env()
    template = env.get_template("early.cfg.j2")
    return template.render(root_uuid=str(root_uuid))


def render_grub_cfg(
    *,
    arch: str,
    root_uuid: UUID | str,
    vmlinuz: str = "vmlinuz",
    initrd: str = "initrd.img",
    console: str | None = None,
    timeout: int = 3,
    default: str = "0",
) -> str:
    """Render the primary /boot/grub/grub.cfg configuration.

    :param arch: Target architecture (used in the menu entry title).
    :param root_uuid: UUID of the root filesystem.
    :param vmlinuz: Kernel image filename under /boot.
    :param initrd: Initrd image filename under /boot.
    :param console: Kernel console arguments. Defaults to a sensible value
        for the given architecture if unset.
    :param timeout: GRUB boot menu timeout in seconds.
    :param default: Default menu entry index or title.
    """
    env = _get_jinja_env()
    template = env.get_template("grub.cfg.j2")

    if console is None:
        console = "console=tty0 console=ttyS0,115200"
        if arch == "riscv64":
            console += " console=ttySIF0,115200"
        elif arch in ("arm64", "armhf"):
            console = "console=tty0 console=ttyAMA0,115200 console=ttyS0,115200"

    return template.render(
        arch=arch,
        root_uuid=str(root_uuid),
        vmlinuz=vmlinuz,
        initrd=initrd,
        console=console,
        timeout=timeout,
        default=default,
    )
