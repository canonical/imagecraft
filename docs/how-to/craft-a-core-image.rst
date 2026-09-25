.. meta::
    :description: How to build an Ubuntu Core image with Imagecraft.


.. _how-to-craft-a-core-image:

Craft an Ubuntu Core image
==========================

Imagecraft builds Ubuntu Core images by preparing the image's seed directory from a
model assertion. The advantage over other image tools is that the ``imagecraft.yaml``
file gives you fine-grained control over the build process.

If you're building an Ubuntu Core image from scratch, complete the
:external+ubuntu-core:ref:`ref-create-a-model_create-a-model` and
:external+ubuntu-core:ref:`ref-sign-the-model_sign-the-model` tutorials before
proceeding.


Initialize the project
----------------------

Start by creating a directory to work in and copying your signed model assertion into
it. Then, create a template project file in the directory by running:

.. code-block:: bash

    imagecraft init

Open the project file, named ``imagecraft.yaml``.

The ``build-base`` key only affects the build environment, not the contents of the
image. So, while it may seem intuitive to declare the build base corresponding to your
model assertion's base snap, you should almost always use the latest build base. The
main exception is for projects that require build tools that aren't available in more
recent releases.

Give the ``version``, ``summary``, and ``description`` keys meaningful values for your
image.


Declare the target architecture
-------------------------------

Unlike the model assertion, you declare the architectures of the build and target
systems with the ``platforms`` key, where each platform consists of a ``build-on`` and
``build-for`` key.

List the CPU architectures that will build the image in the ``build-on`` key. Then, set
the ``build-for`` key to match the top-level architecture key in your model assertion.

To build an image for ARM64 machines that can be built on either an AMD64 or ARM64
machine, you'd declare the following ``platforms`` key:

.. code-block:: yaml
    :caption: imagecraft.yaml

    platforms:
      arm64:
        build-on: [amd64, arm64]
        build-for: arm64


Partition the image
-------------------

If you've created Ubuntu Core images with the ubuntu-image tool, partitioning your image
with Imagecraft will feel a little different. Unlike the ubuntu-image tool, Imagecraft
creates pre-installed Ubuntu Core images. These are packed with every partition in
place, so the snap daemon only validates the structure instead of installing the
contents of the seed partition on first boot.

To validate an image's structure, the snap daemon compares it against that of the gadget
snap. Fortunately, the syntax for declaring a gadget snap's partitions is very similar
to how it's done in Imagecraft, so it can be copied into your project file with only
minor adjustments.


Download the gadget snap
~~~~~~~~~~~~~~~~~~~~~~~~

Open your model assertion. Under the ``snaps`` key, find the snap with its ``type`` key
set to ``gadget``. This is what you'll download to base your image's structure off of.
The process for doing so differs slightly depending on the architecture of your local
machine.

If your image's target architecture matches that of your local machine, download the
snap by substituting its name and channel in the following command:


.. code-block:: bash

    snap download <name> --channel=<default-channel>

If your image's target architecture differs from that of your local machine, find the
latest snap revision for your target channel and architecture by querying the Snap Store
API. Replace the architecture, name, and channel placeholders in the following command:

.. code-block:: bash

    curl -s -H 'X-Ubuntu-Series: 16' \
            -H 'X-Ubuntu-Architecture: <target-arch>' \
            'https://api.snapcraft.io/api/v1/snaps/details/<snap-name>?channel=<channel>&fields=revision,channel,architecture' \
            | jq

The command and output for the ARM64 version of the ``pc`` snap, for example, are:

.. terminal::
    :scroll:

    curl -s -H 'X-Ubuntu-Series: 16' \
      -H 'X-Ubuntu-Architecture: arm64' \
      'https://api.snapcraft.io/api/v1/snaps/details/pc?channel=24/edge&fields=revision,channel,architecture' \
      | jq

    {
      "architecture": [
        "arm64"
      ],
      "channel": "24/edge",
      "package_name": "pc",
      "revision": 226
    }

Download the listed revision of the gadget snap with:

.. code-block:: bash

    snap download <name> --revision=<revision>


Copy the partition scheme
~~~~~~~~~~~~~~~~~~~~~~~~~

Now that the contents of the gadget snap are available locally, extract the
``gadget.yaml`` file, which contains the snap's partition structure:

.. code-block:: bash

    unsquashfs -d gadget <snap-name>_<revision>.snap --extract-file meta/gadget.yaml

Next, replace the entire ``volumes`` key in your project file with the ``volumes`` key
from the ``gadget/meta/gadget.yaml`` file. For each partition, remove all but the
``name``, ``role``, ``type``, ``filesystem``, and ``size`` keys. If the partition types
list both the MBR and GPT partition types, remove the MBR partition type.

If you copied the ``volumes`` key of the ARM64 ``pc`` snap into your project file, for
example, you'd make the following changes:

.. code-block:: diff
    :caption: imagecraft.yaml

      volumes:
        pc:
          schema: gpt
    -     bootloader: grub
          structure:
            - name: ubuntu-seed
              role: system-seed
              filesystem: vfat
    -         type: EF,C12A7328-F81F-11D2-BA4B-00A0C93EC93B
    +         type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
              size: 1200M
    -          update:
    -            edition: 3
    -          content:
    -            - source: grubaa64.efi
    -              target: EFI/ubuntu/grubaa64.efi
    -            - source: shim.efi.signed
    -              target: EFI/ubuntu/shimaa64.efi
    -            - source: boot.csv
    -              target: EFI/ubuntu/bootaa64.csv
    -            - source: fb.efi
    -              target: EFI/boot/fbaa64.efi
    -            - source: shim.efi.signed
    -              target: EFI/boot/bootaa64.efi
            - name: ubuntu-boot
              role: system-boot
              filesystem: ext4
    -         type: 83,0FC63DAF-8483-4772-8E79-3D69D8477DE4
    +         type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
              size: 750M
    -         update:
    -           edition: 1
    -         content:
    -           - source: grubaa64.efi
    -             target: EFI/boot/grubaa64.efi
            - name: ubuntu-save
              role: system-save
              filesystem: ext4
    -         type: 83,0FC63DAF-8483-4772-8E79-3D69D8477DE4
    +         type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
              size: 32M
            - name: ubuntu-data
              role: system-data
              filesystem: ext4
    -         type: 83,0FC63DAF-8483-4772-8E79-3D69D8477DE4
    +         type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
              size: 1G


Clean up
~~~~~~~~

Unless you want to keep your local copy of the gadget snap around for reference, delete
the downloaded files from the project directory:

.. code-block:: bash

    rm -rf gadget pc_<revision>.*


Create the seed partition
-------------------------

Though the full partition structure is declared in the project file, only the seed
partition needs to be created and mounted. The snap daemon mounts the others on first
boot.

In the ``filesystems`` key, map the seed partition to the root by updating the
``device`` key as follows:

.. code-block:: yaml
    :caption: imagecraft.yaml
    :emphasize-lines: 4

    filesystems:
      default:
        - mount: /
          device: (volume/pc/ubuntu-seed)

If your model assertion is located in the root of your project directory and named
``model.assert``, copy the following part into your project file verbatim. Otherwise,
update the source and ``uc-prepare-model-assert`` keys accordingly.

.. code-block:: yaml
    :caption: imagecraft.yaml

    parts:
      seed:
        plugin: uc-prepare
        source: .
        uc-prepare-model-assert: model.assert
        organize:
          system-seed: (volume/pc/ubuntu-seed)

The UC-prepare plugin supports further customization of the seed directory, such as with
additional snaps or assertions, through its optional keys. A complete reference of these
keys is available in :ref:`reference-uc-prepare-plugin`.

One of the most important optimizations enabled by the UC-prepare plugin is preseeding,
which speeds up the first boot by building the scaffolding for the model assertion snaps
directly into the image. To preseed your image, follow the instructions in
:ref:`how-to-pre-install-snaps`.


Pack the image
--------------

Now that the seed partition has been created and mounted, pack the image with:

.. code-block:: bash

    imagecraft pack

Expect the following warning when the image is packed:

.. vale off

.. terminal::
    :output-only:

    Cannot install GRUB on this rootfs: Failed to mount on /root/mount/dev: mountpoint does not exist.
    Packed pc.img

.. vale on

The resulting image is ready to be installed on the target hardware. The Ubuntu Core
documentation provides installation instructions for popular devices in its
:external+ubuntu-core:ref:`ref-index_how-to-deploy-an-image` guides.


Example project
---------------

The following files comprise a complete Ubuntu Core image project for ARM64 machines.

.. dropdown:: imagecraft.yaml

    .. code-block:: yaml

        name: core-arm64
        base: bare
        build-base: ubuntu@24.04
        version: '0.1'
        summary: A minimal Ubuntu Core image for ARM64 machines.
        description: |
          A minimal, pre-installed Ubuntu Core image for ARM64 machines. Its seed partition is
          created with the UC-prepare plugin.

        platforms:
          arm64:
            build-on: [amd64, arm64]
            build-for: arm64

        volumes:
          pc:
            schema: gpt
            structure:
              - name: ubuntu-seed
                role: system-seed
                filesystem: vfat
                type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
                size: 1200M
              - name: ubuntu-boot
                role: system-boot
                filesystem: ext4
                type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                size: 750M
              - name: ubuntu-save
                role: system-save
                filesystem: ext4
                type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                size: 32M
              - name: ubuntu-data
                role: system-data
                filesystem: ext4
                type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
                size: 1G

        filesystems:
          default:
            - device: (volume/pc/ubuntu-seed)
              mount: /

        parts:
          import-key:
            plugin: nil
            source: .
            override-build: |
              mkdir -p /home/ubuntu/.snap/gnupg
              chmod 700 /home/ubuntu/.snap/gnupg
              gpg --homedir /home/ubuntu/.snap/gnupg --import $CRAFT_PART_SRC/sign.key

          seed:
            after: [import-key]
            plugin: uc-prepare
            source: .
            uc-prepare-model-assert: model.assert
            uc-prepare-preseed-sign-key: model-key
            uc-prepare-preseed: True
            organize:
              system-seed: (volume/pc/ubuntu-seed)

.. dropdown:: model.assert

    .. code-block:: yaml

        type: model
        authority-id: canonical
        series: 16
        brand-id: canonical
        model: ubuntu-core-24-arm64
        architecture: arm64
        base: core24
        grade: signed
        snaps:
          -
            default-channel: 24/edge
            id: UqFziVZDHLSyO3TqSWgNBoAdHbLI4dAH
            name: pc
            type: gadget
          -
            default-channel: 24/beta
            id: pYVQrBcKmBa0mZ4CCN7ExT6jH8rY1hza
            name: pc-kernel
            type: kernel
          -
            default-channel: latest/edge
            id: dwTAh7MZZ01zyriOZErqd1JynQLiOGvM
            name: core24
            type: base
          -
            default-channel: latest/edge
            id: PMrrV4ml8uWuEUDBT8dSGnKUYbevVhc4
            name: snapd
            type: snapd
          -
            default-channel: 24/edge
            id: ASctKBEHzVt3f1pbZLoekCvcigRjtuqw
            name: console-conf
            type: app
        timestamp: 2026-09-25T15:58:11+00:00
        sign-key-sha3-384: j3FBN0eU1XeZ7qAuTR066Id5hZ5hcNd8uNDBH5nU2QPv4JQsVQ8LubPHu-F-L1D6

        AcLBcwQAAQoAHRYhBBahy7wwOOJ/WD5geOTJRuX8A398BQJqtpqBAAoJEOTJRuX8A398YhQP/iob
        xxwMDHuxjisizD65HH91DH9+zMntCPtaVntCmIm0nfDaCnVOPrpty1wYMikH41olcUDyVsmVPlLa
        P8LewMVYMgy+uEeE5VOq8ep2xcFprznyyjUmOMguDeFJPWcqLaPAycxw8Qm1e9KgZT+rKqUWhBS7
        IvQnxdJn2cr/M4V2id2SPT/YZWl47TLK3xEpEbYHtPVBc8+pgVYjE9dgsK/BVhLGvV/5ydeFrxRa
        rKOW+L5Ov+WMNK9/mXb/baUQFqp10IKRiO6hTzsbqNabcX8CyaM9AE2/bQtw89N8WmhuE2Qrc/31
        HyQePNx00JFuBClbq73kmBc29QHc72qt72lUOx09TuiDoh9HZ7GPhwdzS5shSqzVlUufmqNP+PSf
        ehdLsicNpbdaxks64ssuT18lQn+mzY334euh+3/R6HRUVRQ2y01WvzSLeJNa97XVQZ6b3j9BkGvQ
        40wnFb/3Ja26qBJrzg5t9XhSuu+X0Hm93aKl43Qh0bcKYQiSvh8E/ru6aKj0JACJYxlPu/+TROno
        f0E39a+7fjvX4BHONAj4aThjLrKfAYl1Wze0CI00TPtvYa0hovQphXPeg4P/Hytww/CqUP+gIXhr
        XxFUB+KYWoWkoNDOOyb79Lg995FRUPnRKk1kDXhz1OOKnZziB/MU+/Y4ljXoNBPNzcOalmwe
