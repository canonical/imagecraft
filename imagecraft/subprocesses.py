# Copyright 2025 Canonical Ltd.
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

"""Imagecraft subprocess utility functions."""

import subprocess
from subprocess import PIPE, CompletedProcess
from typing import Any, cast

from craft_cli import emit


def run(cmd: str, *args: Any, **kwargs: Any) -> CompletedProcess[str]:
    """Thin wrapper around subprocess.run.

    Execute a command line with useful defaults.

    :raises CalledProcessError: If the command fails.
    """
    # Allow callers to override these defaults but set them for convenience
    defaults = {
        "text": True,
        "check": True,
        "stdout": PIPE,
    }
    for key, value in defaults.items():
        if key not in kwargs:
            kwargs[key] = value

    full_command = [cmd, *(str(a) for a in args)]
    emit.debug(f"Running command: {full_command}")

    return cast(
        CompletedProcess[str],
        subprocess.run(full_command, **kwargs),  # noqa: PLW1510
    )
