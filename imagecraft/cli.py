# This file is part of imagecraft.
#
# Copyright 2023 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import sys

from craft_cli import (
    ArgumentParsingError,
    CommandGroup,
    CraftError,
    Dispatcher,
    EmitterMode,
    GlobalArgument,
    ProvideHelpException,
    emit,
)

from imagecraft.commands import (
    build, pull, stage, prime, pack, clean,
)
from imagecraft.plugins import register
from imagecraft.ubuntu_image import UbuntuImageError

COMMAND_GROUPS = [
    CommandGroup(
        "Lifecycle",
        [
            build.BuildCommand,
            pull.PullCommand,
            stage.StageCommand,
            prime.PrimeCommand,
            pack.PackCommand,
        ],
    ),
    CommandGroup(
        "General",
        [
            clean.CleanCommand,
        ],
    ),
]

GLOBAL_ARGS = []


def run():
    """Run the CLI."""
    for lib_name in ("craft_providers", "craft_parts"):
        logger = logging.getLogger(lib_name)
        logger.setLevel(logging.DEBUG)

    emit.init(
        EmitterMode.BRIEF,
        "imagecraft",
        "Starting imagecraft",
        log_filepath=None,
    )

    # Create the dispatcher
    dispatcher = Dispatcher(
        "imagecraft",
        COMMAND_GROUPS,
        summary="Imagecraft is a tool for building Ubuntu images.",
        extra_global_args=GLOBAL_ARGS,
        default_command=pack.PackCommand,
    )

    try:
        global_args = dispatcher.pre_parse_args(sys.argv[1:])
        dispatcher.load_command(global_args)
        register.register_plugins()
        ret = dispatcher.run()
    except CraftError as e:
        emit.error(e)
        ret = e.retcode
    except UbuntuImageError as e:
        emit.error(e)
        ret = 1
    except ProvideHelpException as e:
        print(e, file=sys.stderr)
        emit.ended_ok()
        ret = 0
    except Exception as e:
        error = CraftError(f"Internal error: {e!r}")
        error.__cause__ = e
        emit.error(error)
        ret = 1
    
    return ret
