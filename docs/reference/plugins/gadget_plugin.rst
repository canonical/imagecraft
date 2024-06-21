Gadget plugin
=============

The Gadget plugin builds the gadget containing bootloader configuration.

Keywords
--------

This plugin uses the common :ref:`plugin <part-properties-plugin>` keywords as
well as those for :ref:`sources <part-properties-sources>`.

Additionally, this plugin provides the plugin-specific keywords defined in the
following sections.

gadget_target
~~~~~~~~~~~~~

**Type:** string

Optional target to give to the ``make`` command.


Environment variables
---------------------

This plugin also sets environment variables in the build environment. These are
defined in the following sections.

ARCH
~~~~

**Default value:** target architecture defined in the platform section.

The architecture provided to the `make` command used to build the gadget.

SERIES
~~~~~~

**Default value:** value provided in the ``series`` field of the configuration file.

The series provided to the ``make`` command used to build the gadget.


Dependencies
------------

This plugin relies on ``make``. This dependency will be installed with the snap.


Example
-------

.. code-block:: yaml
    
  gadget:
    plugin: gadget
    source: https://github.com/snapcore/pc-gadget.git
    source-branch: classic
    gadget-type: git
    gadget-target: server
