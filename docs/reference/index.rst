.. _reference:

Reference
=========

References describe the structure and function of the individual components in
Imagecraft.


Commands
--------

Imagecraft is operated from the command line, with a command for each function.

:ref:`commands`


Project file
------------

The main object inside an Imagecraft project is a configurable project file. Read on
for a complete reference of this file's structure and contents.

:ref:`reference-imagecraft-yaml`

An image can be catered to each platform in its project file with special platform
grammar.

:ref:`reference-platform-grammar`


Parts
-----

Software is brought into an image through the declaration of parts. Each part must be
configured for the software's language and build systems.

:ref:`reference-parts-and-steps`


.. toctree::
    :hidden:

    imagecraft-yaml
    commands
    platform-grammar
    parts-and-steps
