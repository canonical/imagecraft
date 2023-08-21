from craft_cli import emit

from imagecraft.lifecycle import ImagecraftLifecycle

from .common import ImagecraftCommand

class CleanCommand(ImagecraftCommand):
    """Prime parts of the image build."""

    name = "clean"
    help_msg = "Clean parts of the image build."
    overview = "TBD"
    execute_step = "clean"

    def run(self, args):
        """Run the command."""
        emit.debug("Running clean command")
        lifecycle = ImagecraftLifecycle(args)
        lifecycle.clean()
        # TBD
