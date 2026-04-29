.. _reference-snap-preseed-plugin:

Snap Preseed Plugin
===================

The snap-preseed plugin seeds snaps into a Classic image by running ``snap prepare-image
--classic``, making them available on first boot.


Keys
----

This plugin provides the following unique keys.


snap-preseed-snaps
~~~~~~~~~~~~~~~~~~

**Type** list of strings

The snaps to seed into the image. Valid entries are:

- a snap name
- a snap name and channel in the format ``snap-name/channel``
- a path to a local snap within the project directory


snap-preseed-channel
~~~~~~~~~~~~~~~~~~~~

**Type** string

The default channel to use when fetching snaps from the store. This is overridden by any
channel specified directly in a snap reference.


snap-preseed-model-assert
~~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

The path to a model assertion file that defines the snaps to seed into the image.


snap-preseed-validation
~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

**Default** ``enforce``

Controls whether `validation set
<https://snapcraft.io/docs/explanation/how-snaps-work/validation-sets>`_ constraints are
enforced. Valid values are ``ignore`` and ``enforce``.


snap-preseed-assertions
~~~~~~~~~~~~~~~~~~~~~~~

**Type** list of strings

Additional assertion files to include in the image.


snap-preseed-revisions
~~~~~~~~~~~~~~~~~~~~~~

**Type** string

Path to a manifest file specifying snap revisions to use.

Each line in a manifest file identifies a snap by name and revision number, like so:

.. code-block:: text

    core24 1587
    snapd 26865


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
``latest/stable`` channel into an image.

.. code-block:: yaml

 parts:
   seed-snaps:
     plugin: snap-preseed
     snap-preseed-snaps:
       - core24
       - hello-world/latest/stable
     organize:
       "var/*": (overlay)/var/
