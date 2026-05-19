.. meta::
    :description: Reference for the Snap-preseed plugin, which creates the seed directory
                  for classic images.

.. _reference-snap-preseed-plugin:

Snap-preseed plugin
===================

The Snap-preseed plugin creates the seed directory for a classic image with the ``snap
prepare-image --classic`` command. This downloads snaps and their assertions from the
Snap Store and prepares them to be installed during the initial boot.


Keys
----

This plugin provides the following unique keys.


snap-preseed-model-assert
~~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** string

The path to the model assertion file that defines the target device. If this key is set,
the model assertion's ``classic`` key must be set to ``true``.

The Ubuntu Core documentation details model assertions and their fields in `model
<https://documentation.ubuntu.com/core/reference/assertions/model/>`_.


snap-preseed-snaps
~~~~~~~~~~~~~~~~~~

**Type:** list of strings

The snaps to seed into the image. Valid entries are:

- a snap name
- a snap name and channel in the format ``<snap-name>/<channel>``
- a path to a local snap within the project directory

If the model assertion has a grade of ``signed`` or ``secured``, only snaps declared in
the model assertion can be specified, and they can't be referenced by a local path. This
is commonly used to include optional snaps from the model assertion.


snap-preseed-channel
~~~~~~~~~~~~~~~~~~~~

**Type:** string

The default store channel to fetch snaps from, overriding any channels in the model
assertion, if one is provided. If a model assertion is provided and has a grade, it
must be set to ``dangerous``.

This is overridden by snaps listed with a channel in ``snap-preseed-snaps``.


snap-preseed-validation
~~~~~~~~~~~~~~~~~~~~~~~

**Type:** string

**Default:** ``enforce``

Controls whether `validation set
<https://snapcraft.io/docs/explanation/how-snaps-work/validation-sets>`_ constraints are
enforced. Valid values are ``ignore`` and ``enforce``.


snap-preseed-assertions
~~~~~~~~~~~~~~~~~~~~~~~

**Type:** list of strings

Additional assertion files to include in the image.

The Ubuntu Core documentation lists the available assertion types in `Assertions
<https://documentation.ubuntu.com/core/reference/assertions/>`_.


snap-preseed-revisions
~~~~~~~~~~~~~~~~~~~~~~

**Type:** string

Path to a manifest file specifying snap revisions to use.

Each line in a manifest file identifies a snap by name and revision number, like so:

.. code-block:: text

    core24 1587
    snapd 26865


snap-preseed-write-revisions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** string or boolean

**Default:** ``False``

If set to ``true``, the plugin writes the resolved snap revisions to the
``seed.manifest`` file. If set to a file path, the revisions are written there instead.


Output
------

The seeded snaps are placed in ``var/lib/snapd/seed``. Use the :ref:`organize
<PartSpec.organize_files>` key to place ``var`` in the root file system.


Example
-------

The following snippet seeds the ``core24`` snap from the ``latest/stable`` channel and
the ``hello-world`` snap from the ``latest/edge`` channel into a classic image.

.. code-block:: yaml

 parts:
   seed-snaps:
     plugin: snap-preseed
     snap-preseed-snaps:
       - core24
       - hello-world/latest/edge
     organize:
       "var/*": (overlay)/var/
