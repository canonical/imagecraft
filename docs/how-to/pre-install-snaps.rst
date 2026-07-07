.. meta::
    :description: How to install and configure default snaps on Ubuntu Desktop, Server, and Core images.


.. _how-to-pre-install-snaps:

Pre-install snaps
=================

When crafting your image, you may want to install and configure a default set of snaps.
Instead of installing these snaps during the initial boot, it's best to build the
scaffolding for them directly into the image. How you do this depends on the type of
image you're crafting.

Because Ubuntu Core images are composed entirely of snaps, pre-installation is strongly
recommended and dramatically reduces the initial boot time. If you're crafting an Ubuntu
Core image, read on.

For classic images, default snaps are an optional customization. If you're crafting an
Ubuntu Desktop or Ubuntu Server image and want to ship it with default snaps, skip ahead
to :ref:`how-to-pre-install-snaps-classic-images`.


Core images
-----------


Prepare your signing key
~~~~~~~~~~~~~~~~~~~~~~~~

The snap daemon needs a signing key to pre-install snaps. If you haven't registered a
key or signed your model, complete the
:external+ubuntu-core:ref:`ref-sign-the-model_sign-the-model` tutorial in the Ubuntu
Core documentation before continuing.

In your project directory, run the following command, replacing ``<key-name>`` with the
name of the signing key you wish to use:

.. code-block:: bash

    gpg --homedir ~/.snap/gnupg --export-secret-keys <key-name> sign.key

To make the signing key available in the build environment, copy the following part into
your project file:

.. code-block:: yaml
    :caption: imagecraft.yaml

    import-key:
      plugin: nil
      source: .
      override-build: |
        mkdir -p /home/ubuntu/.snap/gnupg
        chmod 700 /home/ubuntu/.snap/gnupg
        gpg --homedir /home/ubuntu/.snap/gnupg --import $CRAFT_PART_SRC/sign.key

.. admonition:: Required interaction during packing
    :class: caution

    When packing, you'll be prompted to unlock this signing key twice. If these prompts
    aren't acknowledged within a few minutes, the packing process will time out and
    fail.


Pre-install model assertion snaps
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you haven't already, copy your image's model assertion into the directory holding
your project file.

Next, copy the following part into your project file, replacing ``<assertion-name>`` and
``<key-name>`` with the name of your model assertion and signing key, respectively:

.. code-block:: yaml
    :caption: imagecraft.yaml

    uc-seed:
      after: [import-key]
      plugin: uc-prepare
      source: .
      uc-prepare-model-assert: <assertion-name>
      uc-prepare-preseed: true
      uc-prepare-preseed-sign-key: <key-name>
      organize:
        "system-seed/*": (volume/disk/ubuntu-seed)/
      prime:
        - -kernel
        - -gadget
        - -resolved-content
        - -system-seed

This part prepares the scaffolding for the snaps in a ``system-seed/`` directory, copies
them to your image's ``ubuntu-seed`` partition, and cleans up the original copies so
they don't cause conflicts.

If your model assertion contains optional snaps that you wish to install, list them with
the ``uc-prepare-snaps`` key:

.. code-block:: yaml
    :caption: imagecraft.yaml
    :emphasize-lines: 8-10

    uc-seed:
      after: [import-key]
      plugin: uc-prepare
      source: .
      uc-prepare-model-assert: <assertion-name>
      uc-prepare-preseed: true
      uc-prepare-preseed-sign-key: <key-name>
      uc-prepare-snaps:
        - core22
        - hello-world@latest/edge
      organize:
        "system-seed/*": (volume/disk/ubuntu-seed)/
      prime:
        - -kernel
        - -gadget
        - -resolved-content
        - -system-seed

To tweak the snaps' channels or revisions further, refer to the additional keys in the
:ref:`reference-uc-prepare-plugin` reference. Configuration that deviates from the model
assertion requires the model assertion's grade to be ``dangerous``.


.. _how-to-pre-install-snaps-classic-images:

Classic images
--------------

To pre-install snaps into your classic image, declare a part that uses the Snap-preseed
plugin. This plugin prepares the scaffolding for the snaps in the part's
``var/lib/snapd/seed/`` directory, which you'll need to copy into your image with the
``organize`` key.

For example, if you wanted to pre-install the ``core24`` snap from the ``latest/stable``
channel and the ``hello-world`` snap from the ``latest/edge`` channel, your part would
be declared as:

.. code-block:: yaml
    :caption: imagecraft.yaml

    seed-snaps:
      plugin: snap-preseed
      snap-preseed-snaps:
        - core24
        - hello-world @ latest/edge
      organize:
        "var/*": (overlay)/var/

To tweak the snap channels or revisions further, refer to the additional keys in the
:ref:`reference-snap-preseed-plugin` reference.
