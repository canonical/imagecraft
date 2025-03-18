
.. _ref_commands_init:

init
====

Initialise a project.

If '<project-dir>' is provided, initialise in that directory,
otherwise initialise in the current working directory.

If '--name <name>' is provided, the project will be named '<name>'.
Otherwise, the project will be named after the directory it is initialised in.

'--profile <profile>' is used to initialise the project for a specific use case.

Init can work in an existing project directory. If there are any files in the
directory that would be overwritten, then init command will fail.


Usage
-----

:command:`imagecraft init [options] <project_dir>`

Required
--------

``project_dir``
   Path to initialise project in; defaults to current working directory.

Options
-------

``--name``
   The name of project; defaults to the name of <project_dir>.
``--profile``
   Use the specified project profile (default is simple, choices are 'simple').

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
