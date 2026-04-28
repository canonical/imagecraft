.. _reference-snap-preseed-plugin:

Snap-Preseed Plugin
===================

The snap-preseed plugin seeds snaps into a Classic Ubuntu image by running ``snap
prepare-image --classic``, making them available on first boot.


Keys
----

This plugin provides the following unique keys.


snap-preseed-snaps
~~~~~~~~~~~~~~~~~~

**Type** list of strings

**Required**

The snaps to seed into the image. Each entry can be a snap name or a path to a local
snap.


snap-preseed-model-assert
~~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

The path to a model assertion file that defines the image.


snap-preseed-channel
~~~~~~~~~~~~~~~~~~~~

**Type** string

**Default** ``ignore``

The validation mode for snap signatures. Valid values are ``ignore`` and
``enforce``.


snap-preseed-assertions
~~~~~~~~~~~~~~~~~~~~~~~

**Type** list of strings

Additional assertion files to include in the image.


snap-preseed-revisions
~~~~~~~~~~~~~~~~~~~~~~

**Type** string

Path to a manifest file specifying snap revisions to use.


snap-preseed-write-revisions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string or boolean

If ``true``, writes the resolved snap revisions to ``seed.manifest``. If a string, it
is treated as the path to which the revisions will be written.


Output
------

The seeded snaps are placed in ``var/lib/snapd/seed``. Use ``organize`` to place them on
the root filesystem.


Example
-------

The following snippet prepares snaps for a Classic image with core24 and hello-world
from the ``latest/stable`` channel.

.. code-block:: yaml

 parts:
   seed-snaps:
     plugin: snap-preseed
     snap-preseed-snaps:
       - core24
       - hello-world/latest/stable
     organize:
       "var/*": (overlay)/var/

