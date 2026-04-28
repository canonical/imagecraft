.. _reference-snap-preseed-plugin:

Snap Preseed Plugin
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


snap-preseed-channel
~~~~~~~~~~~~~~~~~~~~

**Type** string

The default channel to use when fetching snaps from the store.


snap-preseed-model-assert
~~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

The path to a model assertion file that defines the Ubuntu Classic image.


snap-preseed-validation
~~~~~~~~~~~~~~~~~~~~~~~

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

If ``true``, the plugin writes a manifest file with the resolved snap revisions to
``seed.manifest``. If a string, it is treated as the path to which the manifest will be
written.


Output
------

The seeded snaps are placed in ``var/lib/snapd/seed``. Use ``organize`` to place them in
the root filesystem.


Example
-------

The following snippet seeds the ``core24`` snap and the ``hello-world`` snap from the
``latest/stable`` channel into an Ubuntu Classic image.

.. code-block:: yaml

 parts:
   seed-snaps:
     plugin: snap-preseed
     snap-preseed-snaps:
       - core24
       - hello-world/latest/stable
     organize:
       "var/*": (overlay)/var/
