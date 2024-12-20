# Copyright 2022-2024 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For further info, check https://github.com/canonical/imagecraft

"""Grub related utility install functions."""

import pathlib

from craft_cli import emit

from imagecraft import utils

# pylint: disable=no-member


def grub_efi_install(
    *,
    parts_stage_dir: pathlib.Path,
    esp_stage_dir: pathlib.Path,
    grub_modules: list[str],
) -> None:
    """Install Grub in EFI mode in the supplied staging location.

    :param parts_stage_dir: Parts staging area.
    :param esp_stage_dir: The ESP staging directory.
    :param grub_modules: Modules to be included in Grub.
    """
    # We only support one platform for now
    platform = "x86_64-efi"

    # This is the location where the platform specific files were staged
    grub_platform_files = parts_stage_dir / "usr/lib/grub" / platform

    # The Grub output binary
    grub_output_dir = esp_stage_dir / "EFI/boot"
    grub_output_dir.mkdir(parents=True, exist_ok=True)
    grub_output = grub_output_dir / "bootx64.efi"

    # Build GRUB kernel image with the required modules.
    utils.cmd(
        "grub_mkimage",
        "--directory",
        grub_platform_files,
        "--output",
        grub_output,
        "--format",
        platform,
        "--prefix",
        "/EFI/kernos",
        "--verbose",
        *grub_modules,
    )


# A generic grub configuration for KernOS platforms
_GRUB_CONFIG: str = """
# Generated GRUB config
set default=normal
set fallback=1
set timeout=0

function save_environment {
    save_env --file ${prefix}/grub.env BOOT REVERT_BOOT REVERT_STATE
}

function load_environment {
    load_env --file ${prefix}/grub.env BOOT REVERT_BOOT REVERT_STATE
}

function set_root {
    if [ ! -z "$1" ]; then
        search --set root --no-floppy --label "$1"
    else
        unset root
    fi
}

function set_valid_part_label {
    if [ "$1" = "kernos-a" ]; then
        set valid_part_label="$1"
    elif [ "$1" = "kernos-b" ]; then
        set valid_part_label="$1"
    elif [ "$1" = "kernos-f" ]; then
        set valid_part_label="$1"
    else

        # Explicitly making the part label empty (invalid)
        # will result in failing to boot the partition. If
        # failing happens during a firmware transition, the
        # fallback mechanism will revert it. If this is
        # happening for any other reason, we will stop here
        # in GRUB with a failed boot without any further
        # action to avoid a reboot loop for which we have no
        # implemented remedial action available today.

        unset valid_part_label
    fi
}

load_environment

# Default if no boot is set (first boot)
if [ -z "${BOOT}" ]; then
    set BOOT="kernos-a"
    save_environment
fi

set_valid_part_label "${BOOT}"
set_root "${valid_part_label}"

# This block is responsible for fallback logic in case
# of a newly selected partition failing to boot. GRUB can only
# intervene in early failures where it is still running and in
# this case GRUB will do what critical failures in userspace
# will do, issue a reboot using the fallback hook.

set_valid_part_label "${REVERT_BOOT}"
if [ -n "${valid_part_label}" ]; then
    if [ -z "${REVERT_STATE}" ]; then

        # In the case where a revert partition was specified,
        # we enable the early failure fallback hook to issue
        # a GRUB reboot. Revert state will be saved before the
        # failure is handled.

        set REVERT_STATE="pending"
        save_environment

    elif [ "${REVERT_STATE}" = "pending" ]; then

        # This is the point where following an attempted partition
        # change which failed and resulted in a reboot (either
        # inside GRUB or userspace) will revert to the previous state.

        set REVERT_STATE="applying"
        set_root "${valid_part_label}"
        save_environment
    fi
fi

menuentry "KernOS" --id normal {
    chainloader /kernos.img
}

menuentry "Recover" --id recover {
    # Recovery must re-measure from the start of boot.
    reboot
}
"""


def grub_efi_config(*, esp_stage_dir: pathlib.Path) -> None:
    """Write a config file for Grub.

    :param esp_stage_dir: The ESP staging directory.
    """
    grub_kernos_config_dir = "EFI/kernos"
    grub_config_path = esp_stage_dir / grub_kernos_config_dir
    grub_config_path.mkdir(parents=True, exist_ok=True)
    grub_config = grub_config_path / "grub.cfg"
    with grub_config.open("w", encoding="utf-8") as fp:
        fp.write(_GRUB_CONFIG)

    emit.debug(f"Grub config file: {grub_kernos_config_dir}/grub.cfg")
    emit.debug(f"Grub config: \n {_GRUB_CONFIG}")


# The environment file must always be this exact size
ENV_BLOCK_SIZE: int = 1024

# The default grub environment variables
_GRUB_ENV: dict[str, str] = {}


def grub_efi_env_default(*, esp_stage_dir: pathlib.Path) -> None:
    """Write a environment file for Grub.

    :param esp_stage_dir: The ESP staging directory.
    """
    lines = ["# GRUB Environment Block\n"]
    for key, value in _GRUB_ENV.items():
        lines.append(f"{key}={value}\n")
    block = "".join(lines)
    padded_block = block.ljust(ENV_BLOCK_SIZE, "#")

    grub_env_path = esp_stage_dir / "EFI" / "kernos"
    grub_env_path.mkdir(parents=True, exist_ok=True)
    grub_env = grub_env_path / "grub.env"
    with grub_env.open("w", encoding="utf-8") as fp:
        fp.write(padded_block)

    emit.debug(f"Grub environment file: {grub_env}")
    emit.debug(f"Grub env: \n {padded_block}")
