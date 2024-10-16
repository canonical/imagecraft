
.. _ref_commands_pack:

pack
====

Process parts and create the final artifact.


Usage
-----

:command:`imagecraft pack [options]`


Options
-------

``--build-for``
   Set architecture to build for.
``--debug``
   Shell into the environment if the build fails.
``--destructive-mode``
   Build in the current host.
``--output`` or ``-o``
   Output directory for created packages.
``--platform``
   Set platform to build for.
``--shell``
   Shell into the environment in lieu of the step to run.
``--shell-after``
   Shell into the environment after the step has run.
``--use-lxd``
   Build in a LXD container.

Global options
--------------

``-h`` or ``--help``
   Show this help message and exit.
``-q`` or ``--quiet``
   Only show warnings and errors, not progress.
``-v`` or ``--verbose``
   Show debug information and be more verbose.
``--verbosity``
   Set the verbosity level to 'quiet', 'brief', 'verbose', 'debug' or 'trace'.
``-V`` or ``--version``
   Show the application version and exit.

