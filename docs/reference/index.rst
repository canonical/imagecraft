.. _reference:

Reference
=========

References describe the structure and function of the individual components in
Imagecraft.


Commands
--------

Imagecraft is operated from the command line, with a command for each function.

* :ref:`commands`


Project file
------------

The main object inside an Imagecraft project is a configurable project file. Read on
for a complete reference of this file's structure and contents.

* :ref:`reference-imagecraft-yaml`

An image can be catered to each platform in its project file with special platform
grammar.

* :ref:`reference-platform-grammar`


Parts
-----

Files in an image are manipulated by declaring parts. Some common tools and tasks
have plugins, which determine how parts are built.

* :ref:`reference-parts-and-steps`
* :ref:`plugins`

.. toctree::
    :hidden:

    imagecraft-yaml
    commands
    platform-grammar
    parts-and-steps
    plugins
