.. _mmdebstrap_plugin:

mmdebstrap Plugin
=================

The mmdebstrap plugin sets up a Debian root file system using the
`mmdebstrap <https://manpages.debian.org/mmdebstrap>`_ command-line tool.

The plugin creates a minimal root file system with a customizable set
of additional packages.

Keys
----

This plugin provides the following unique keys.

mmdebstrap-suite
~~~~~~~~~~~~~~~~

**Type** string

The distribution suite to bootstrap (for example, ``noble``). If unset,
the suite in the build environment's ``/etc/os-release`` file is used.

mmdebstrap-variant
~~~~~~~~~~~~~~~~~~

**Type** string

**Default** "apt"

The package set to install. Valid values are ``extract``, ``custom``, ``essential``,
``apt``, ``required``, ``minbase``, ``buildd``, ``important``, ``debootstrap`` and
``standard``.

The `VARIANTS section of the documentation
<https://manpages.debian.org/mmdebstrap#VARIANTS>`_ contains more details.

mmdebstrap-packages
~~~~~~~~~~~~~~~~~~~

**Type** list of strings

Individual packages to install in the file system. These are installed in addition
to those set by ``mmdebstrap-variant``.


How it works
------------

During the build step, the plugin performs the following actions:

1. Runs ``mmdebstrap`` with the specified suite, variant and packages.
2. Removes files from ``/dev/*`` to avoid stalling final build.
3. Removes default sources configuration files (``/etc/apt/sources.list`` and
   ``/etc/apt/sources.list.d/*``) to allow for custom repository configuration.

The plugin selects the appropriate mirror for the target architecture:

- ``amd64`` and ``i386``: ``http://archive.ubuntu.com/ubuntu``
- Other architectures: ``http://ports.ubuntu.com/ubuntu-ports``


Examples
--------

The following snippet declares a part that creates an Ubuntu 24.04 LTS root
file system with curl installed:

.. code-block:: yaml

   parts:
     rootfs:
       plugin: mmdebstrap
       mmdebstrap-suite: noble
       mmdebstrap-packages: ["curl"]
       organize:
         '*': (overlay)/

A minimal example that uses the build environment's suite:

.. code-block:: yaml

   parts:
     rootfs:
       plugin: mmdebstrap
       organize:
         '*': (overlay)/
