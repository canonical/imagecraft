.. meta::
    :description: Reference for the UC Prepare plugin, which creates the seed directory
                  for Ubuntu Core images.

.. _reference-uc-prepare-plugin:

UC Prepare plugin
=================

The UC Prepare plugin creates the seed directory for Ubuntu Core images with the ``snap
prepare-image`` command. This downloads snaps and their associated assertions from the
Snap store, organizing them into a structure that ``snapd`` reads at first boot to
install to the system.

The plugin can also preseed the image, which performs administrative tasks for the
snaps being seeded during the image-building phase rather than during the initial boot,
reducing first-boot time.


Keys
----

This plugin provides the following unique keys.


uc-prepare-model-assert
~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

**Required**

The path to the model assertion file that defines the target device, including its
required snaps.

For a complete reference of the contents of a model assertion, refer to `Ubuntu Core |
model <https://documentation.ubuntu.com/core/reference/assertions/model/>`_.


uc-prepare-snaps
~~~~~~~~~~~~~~~~

**Type** list of strings

Snaps to seed into the image in addition to those required by the model assertion. For
``grade: dangerous`` models, valid entries are:

- a snap name
- a snap name and channel in the format ``<snap-name>/<channel>``
- a path to a local snap within the project directory

For higher grades (``signed``, ``secured``), only snaps declared as optional in the
model assertion can be specified and must not be referenced by a local path.


uc-prepare-channel
~~~~~~~~~~~~~~~~~~

**Type** string

The default channel to use when fetching snaps from the store. Requires the model
to grade to be set to ``grade: dangerous``.


uc-prepare-validation
~~~~~~~~~~~~~~~~~~~~~

**Type** string

**Default:** ``enforce``

Controls whether `validation set
<https://snapcraft.io/docs/explanation/how-snaps-work/validation-sets>`_ constraints are
enforced. Valid values are ``ignore`` and ``enforce``.


uc-prepare-assertions
~~~~~~~~~~~~~~~~~~~~~

**Type** list of strings

Additional assertion files to include in the image.


uc-prepare-revisions
~~~~~~~~~~~~~~~~~~~~

**Type** string

Path to a manifest file specifying snap revisions to use.

Each line in a manifest file identifies a snap by name and revision number, like so:

.. code-block:: text

    core24 1587
    snapd 26865


uc-prepare-write-revisions
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string or boolean

**Default:** ``False``

If ``true``, the plugin writes a manifest file with the resolved snap revisions to
``seed.manifest``. If a string, it is treated as the path to which the manifest will be
written.


uc-prepare-preseed
~~~~~~~~~~~~~~~~~~

**Type** boolean

**Default** ``false``

If ``true``, the plugin runs the snap preseeding process to reduce first-boot time.


uc-prepare-preseed-sign-key
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

The signing key for the preseed assertion. Requires ``uc-prepare-preseed`` to be
set to ``true``.


uc-prepare-apparmor-features-dir
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

Path to the `AppArmor features
<https://gitlab.com/apparmor/apparmor/-/wikis/AppArmorInterfaces/#syskernelsecurityapparmorfeatures>`_
directory to use during preseeding.

This directory should be a snapshot of the ``/sys/kernel/security/apparmor/features`` directory from
the target system. If this key is unset and ``uc-prepare-preseed`` is set to ``true``, the directory
from the host system is used.


uc-prepare-sysfs-overlay
~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

Path to a sysfs overlay directory for preseeding. Requires ``uc-prepare-preseed`` to be
set to ``true``.


Output
------

The seed content for the image is placed under ``system-seed``. Place it in the desired
partition with the :ref:`organize <PartSpec.organize_files>` key.


Example
-------

The following snippet prepares snaps for an Ubuntu Core image as described by a model
assertion file named ``model.assert``.

.. code-block:: yaml

   parts:
     uc-seed:
       plugin: uc-prepare
       uc-prepare-model-assert: model.assert
       organize:
         "system-seed/*": (volume/disk/ubuntu-seed)/
