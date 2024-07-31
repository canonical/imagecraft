
.. _ref_commands_pull:

pull
====

Download or retrieve artifacts defined for a part. If part names
are specified only those parts will be pulled, otherwise all parts
will be pulled.


Usage
-----

:command:`imagecraft pull [options] <part-name>`

Required
--------

``part-name``
   Optional list of parts to process.

Options
-------

``--build-for``
   Set architecture to build for.
``--debug``
   Shell into the environment if the build fails.
``--destructive-mode``
   Build in the current host.
``--platform``
   Set platform to build for.
``--shell``
   Shell into the environment in lieu of the step to run.
``--shell-after``
   Shell into the environment after the step has run.

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

