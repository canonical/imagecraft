.. _reference-uc-prepare-plugin:

UC Prepare Plugin
=================

The uc-prepare plugin prepares snaps for Ubuntu Core images using the ``snap
prepare-image`` command, making them available on first boot.


Keys
----

This plugin provides the following unique keys.


uc-prepare-model-assert
~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

**Required**

The path to the model assertion file that defines the Ubuntu Core image.

The `Create a model
<https://documentation.ubuntu.com/core/tutorials/build-your-first-image/create-a-model>`_
tutorial from the Ubuntu Core documentation contains more details.


uc-prepare-snaps
~~~~~~~~~~~~~~~~

**Type** list of strings

Additional snaps to seed into the image. Each entry can be a snap name or a path to a
local snap.


uc-prepare-channel
~~~~~~~~~~~~~~~~~~

**Type** string

The default channel to use when fetching snaps from the store.


uc-prepare-validation
~~~~~~~~~~~~~~~~~~~~~

**Type** string

**Default** ``enforce``

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

The following is an example manifest file:

.. code-block:: text

    core24 1587
    snapd 26865


uc-prepare-write-revisions
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string or boolean

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

The key to use for signing the preseed assertion. Requires ``uc-prepare-preseed`` to be
enabled.


uc-prepare-apparmor-features-dir
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

Path to the `AppArmor features
<https://gitlab.com/apparmor/apparmor/-/wikis/AppArmorInterfaces/#syskernelsecurityapparmorfeatures>`_
directory to use during preseeding.

This directory should be a snapshot of ``sys/kernel/security/apparmor/features`` from
the target system. If not specified, the ``sys/kernel/security/apparmor/features`` from
the host system will be used when ``uc-prepare-preseed`` is enabled.


uc-prepare-sysfs-overlay
~~~~~~~~~~~~~~~~~~~~~~~~

**Type** string

Path to a sysfs overlay directory for preseeding. Requires ``uc-prepare-preseed`` to be
enabled.


Output
------

The seed content for the image is placed under ``system-seed``. Use ``organize`` to
place it in the desired partition.


Example
-------

The following snippet prepares snaps for an Ubuntu Core image as defined by a model
assertion file named ``model.assert``.

.. code-block:: yaml

   parts:
     uc-seed:
       plugin: uc-prepare
       uc-prepare-model-assert: model.assert
       organize:
         "system-seed/*": (volume/disk/ubuntu-seed)/
