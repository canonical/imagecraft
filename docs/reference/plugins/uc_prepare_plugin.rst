.. meta::
    :description: Reference for the UC-prepare plugin, which creates the seed directory
                  for Ubuntu Core images.

.. _reference-uc-prepare-plugin:

UC-prepare plugin
=================

The UC-prepare plugin creates the seed directory for Ubuntu Core images with the ``snap
prepare-image`` command. This downloads snaps and their assertions from the Snap Store
and prepares them to be installed during the initial boot.

The plugin can also install snaps and run their hooks when the image is being packed.
This process, known as *preseeding*, reduces the initial boot time.


Keys
----

This plugin provides the following unique keys.


uc-prepare-model-assert
~~~~~~~~~~~~~~~~~~~~~~~

**Type:** string

**Required**

The path to the model assertion file that defines the target device and its required
snaps.

The Ubuntu Core documentation details model assertions and their fields in the `model
<https://documentation.ubuntu.com/core/reference/assertions/model/>`_.


uc-prepare-snaps
~~~~~~~~~~~~~~~~

**Type:** list of strings

Snaps to seed into the image in addition to those required by the model assertion. Valid
entries are:

- a snap name
- a snap name and channel in the format ``<snap-name>/<channel>``
- a path to a local snap within the project directory

If the model assertion has a grade of ``signed`` or ``secured``, only snaps declared in
the model assertion can be specified, and they can't be referenced by a local path. This
is commonly used to include optional snaps from the model assertion.


uc-prepare-channel
~~~~~~~~~~~~~~~~~~

**Type:** string

The default store channel to fetch snaps from, overriding any channels in the model
assertion. If this key is set, the model assertion's ``grade`` must be set to
``dangerous``.

This is overridden by snaps listed with a channel in ``uc-prepare-snaps``.


uc-prepare-validation
~~~~~~~~~~~~~~~~~~~~~

**Type:** string

**Default:** ``enforce``

Controls whether `validation set
<https://snapcraft.io/docs/explanation/how-snaps-work/validation-sets>`_ constraints are
enforced. Valid values are ``ignore`` and ``enforce``.


uc-prepare-assertions
~~~~~~~~~~~~~~~~~~~~~

**Type:** list of strings

Additional assertion files to include in the image.

The Ubuntu Core documentation lists the available assertion types in `Assertions
<https://documentation.ubuntu.com/core/reference/assertions/>`_.


uc-prepare-revisions
~~~~~~~~~~~~~~~~~~~~

**Type:** string

Path to a manifest file specifying snap revisions to use.

Each line in a manifest file identifies a snap by name and revision number, like so:

.. code-block:: text

    core24 1587
    snapd 26865


uc-prepare-write-revisions
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** string or boolean

**Default:** ``False``

If set to ``true``, the plugin writes the resolved snap revisions to the
``seed.manifest`` file. If set to a file path, the revisions are written there instead.


uc-prepare-preseed
~~~~~~~~~~~~~~~~~~

**Type:** boolean

**Default:** ``false``

If set to ``true``, the plugin preseeds snaps to improve the initial boot speed.


uc-prepare-preseed-sign-key
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** string

The signing key for the preseed assertion. Requires ``uc-prepare-preseed`` to be
set to ``true``.


uc-prepare-apparmor-features-dir
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** string

Path to the `AppArmor features
<https://gitlab.com/apparmor/apparmor/-/wikis/AppArmorInterfaces/#syskernelsecurityapparmorfeatures>`_
directory to use during preseeding.

This directory should be a snapshot of the ``/sys/kernel/security/apparmor/features`` directory from
the target system. If this key is unset and ``uc-prepare-preseed`` is set to ``true``, the directory
from the host system is used.


uc-prepare-sysfs-overlay
~~~~~~~~~~~~~~~~~~~~~~~~

**Type:** string

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
