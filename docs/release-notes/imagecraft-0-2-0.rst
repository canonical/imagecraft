.. meta::
    :description: Release notes for Imagecraft 0.2.0.

.. _release-0.2.0:

Imagecraft 0.2.0 release notes
==============================

22 July 2026

Learn about the new features, changes, and fixes introduced in Imagecraft 0.2.0.


Requirements and compatibility
------------------------------

Imagecraft 0.2.0 requires Python 3.11 or higher.


What's new
----------

Imagecraft 0.2.0 brings the following features, integrations, and improvements.


Support for MBR and hybrid volume schemas
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now accepts ``mbr`` and ``mbr,gpt`` volume schemas. MBR images are now
supported on x86, and Imagecraft generates the GRUB assets needed for them.


Support for snap prepare-image plugins
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now includes ``snap-preseed`` and ``uc-prepare`` plugins for core and
classic images. These plugins make it easier to prepare images that need snap
content or Ubuntu Core setup steps.


Support for the mmdebstrap plugin
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now includes an ``mmdebstrap`` plugin for building Debian-derived root
filesystems.


Improved boot image generation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now uses ``grub-mkimage`` asset generation instead of mounting the target
root filesystem and running ``grub-install``. This makes boot asset generation more
reliable during packing.


Minor features
--------------

Imagecraft 0.2.0 brings the following minor changes.


Support for writing to specific sectors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now writes volume data to temporary image files during lifecycle commands,
which lets it place data in specific sectors of the final output image.


Support for the ``@`` channel separator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``snap-preseed`` and ``uc-prepare`` plugins now accept ``@`` as the channel
separator, with optional surrounding whitespace.


Support for Ubuntu 26.04 as a build base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now accepts ``ubuntu@26.04`` as a build base.


Improved overlay handling
~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now enables ``override-overlay`` for image builds.


Backwards-incompatible changes
------------------------------

The following changes are incompatible with previous versions of Imagecraft.


Using the MINIMAL plugin group
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now extends craft-application's ``MINIMAL`` plugin group instead of the
``DEFAULT`` group. If you rely on custom plugin selection, review your setup against
the new plugin grouping behavior.


Fixed bugs and issues
---------------------

The following issues have been resolved in Imagecraft 0.2.0.


* ``snap-prepare`` now treats missing keys as optional instead of failing when they
  are absent.
* ``mmdebstrap`` now unmounts lingering mounts after use.


Contributors
------------

We would like to express a big thank you to all the people who contributed to this
release.

smethnani, JJ Coldiron, Alex Lowe, Imani Pelton, Michael DuBelko, Spilsed, Callahan
Kovacs, Alex M. Lowe, and Michael Hudson-Doyle.
