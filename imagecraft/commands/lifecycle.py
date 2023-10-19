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
from overrides import overrides

from imagecraft.lifecycle import ImagecraftLifecycle


class ImagecraftLifecycleCommand(BaseCommand, abc.ABC):
    """Base class for all imagecraft lifecycle commands."""

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
            help="Only build image for the selected platforms."
        )
        parser.add_argument(
            "-O",
            "--output-dir",
            metavar="output_dir",
            type=str,
            help="Path to the output directory."
        )
        # TODO: add more common arguments

    def run(self, args):
        if not self.execute_step:
            return
        
        lifecycle = ImagecraftLifecycle(args)
        lifecycle.run(self.execute_step)


class PullCommand(ImagecraftLifecycleCommand):
    """Pull parts of the image build."""

    name = "pull"
    help_msg = "Pull parts of the image build."
    overview = "TBD"
    execute_step = "pull"


class BuildCommand(ImagecraftLifecycleCommand):
    """Build parts of the image build."""

    name = "build"
    help_msg = "Build parts of the image build."
    overview = "TBD"
    execute_step = "build"


class StageCommand(ImagecraftCommand):
    """Stage parts of the image build."""

    name = "stage"
    help_msg = "Stage parts of the image build."
    overview = "TBD"
    execute_step = "stage"


class PrimeCommand(ImagecraftLifecycleCommand):
    """Prime parts of the image build."""

    name = "prime"
    help_msg = "Prime parts of the image build."
    overview = "TBD"
    execute_step = "prime"


class PackCommand(ImagecraftLifecycleCommand):
    """Pack parts of the image build."""

    name = "pack"
    help_msg = "Pack parts of the image build."
    overview = "TBD"
    execute_step = "pack"

    @overrides
    def run(self, args):
        """Run only the pack command."""
        emit.debug("Running clean command")
        lifecycle = ImagecraftLifecycle(args)
        lifecycle.pack_selected_platforms()


class CleanCommand(ImagecraftLifecycleCommand):
    """Prime parts of the image build."""

    name = "clean"
    help_msg = "Clean parts of the image build."
    overview = "TBD"
    execute_step = "clean"

    def run(self, args):
        """Run the clean command."""
        emit.debug("Running clean command")
        lifecycle = ImagecraftLifecycle(args)
        lifecycle.clean()
