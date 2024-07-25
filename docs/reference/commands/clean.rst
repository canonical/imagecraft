
.. _ref_commands_clean:

clean
=====

Clean up artefacts belonging to parts. If no parts are specified,
remove the packing environment.


Usage
-----

:command:`imagecraft clean [options] <part-name>`

Required
--------

``part-name``
   Optional list of parts to process.

Options
-------

``--destructive-mode``
   Build in the current host.

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

