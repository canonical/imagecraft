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

import abc

from craft_cli import BaseCommand, emit
from craft_cli.dispatcher import _CustomArgumentParser

from imagecraft.lifecycle import ImagecraftLifecycle


class ImagecraftCommand(BaseCommand, abc.ABC):
    """Base class for all imagecraft commands."""

    execute_step = None

    def __init__(self, config):
        super().__init__(config)

    def fill_parser(self, parser):
        # Common arguments
        parser.add_argument(
            "--debug",
            action="store_true",
            help="Enable debug mode.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Enable verbose mode.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Enable quiet mode.",
        )
        parser.add_argument(
            "--platform",
            action="append",
            help=(
                "Only build image for the selected platforms."
            ),
        )
        # TODO: add more common arguments

    def run(self, args):
        if not self.execute_step:
            return
        
        lifecycle = ImagecraftLifecycle(args)
        lifecycle.run(self.execute_step)

