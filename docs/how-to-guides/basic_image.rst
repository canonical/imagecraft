.. _how-to-build-basic-image:

===================
Build a basic image
===================

These instructions describe how to build a minimal ``classic`` Ubuntu 24.04 AMD64
server image with Imagecraft.

Prerequisites
-------------

- AMD64 machine with Ubuntu 24.04
- ``snapd`` installed (see `Install snap on Ubuntu
  <https://snapcraft.io/docs/installing-snap-on-ubuntu>`_)
- 15GiB or more disk space to process the build and hold the resulting image

.. note:: Following these instructions will build an **AMD64** image on an
          **AMD64** machine. Building on another architecture would need several
          modifications not described on this page.

Install Imagecraft
~~~~~~~~~~~~~~~~~~

Imagecraft is available as a snap on the ``latest/beta`` channel in the
`Snap Store <https://snapcraft.io/imagecraft>`_. Install it with:

.. code-block::

    sudo snap install imagecraft --channel=beta --classic

Verify that Imagecraft is properly installed:

.. code-block::

    imagecraft

.. caution:: Imagecraft mounts important (``/dev``, ``/sys``, etc.) system directories
             from the building environment. When running in destructive mode, a
             invalid project file leading to a failure of Imagecraft could damage the
             system.


Prepare the configuration
-------------------------

Project file
~~~~~~~~~~~~

The name of the project file, ``imagecraft.yaml``, is **important** because Imagecraft
uses it automatically. Save the following content as ``imagecraft.yaml``:

.. collapse:: imagecraft.yaml

    .. literalinclude:: code/basic_imagecraft.yaml
        :caption: imagecraft.yaml
        :language: yaml


Cloud-init configuration
~~~~~~~~~~~~~~~~~~~~~~~~

Prepare needed directories:

.. code-block::

    mkdir -p cloud-init/var/lib/cloud/seed/nocloud
    mkdir -p cloud-init/etc/cloud/cloud.cfg.d/

Write the following files in the ``cloud-init`` directory:

- ``cloud-init/var/lib/cloud/seed/nocloud/meta-data``

  .. literalinclude:: code/cloud-init/meta-data
      :language: yaml

- ``cloud-init/var/lib/cloud/seed/nocloud/user-data``

  .. literalinclude:: code/cloud-init/user-data
      :language: yaml

- ``cloud-init/etc/cloud/cloud.cfg.d/90_dpkg.cfg``

  .. literalinclude:: code/cloud-init/90_dpkg.cfg
      :language: yaml


Pack the image
--------------

The packing can be run in two different environments:

- In a ``multipass`` VM:

  .. code-block:: bash

      CRAFT_BUILD_ENVIRONMENT=multipass imagecraft --verbosity debug pack

- On the local machine, with destructive mode. In this case the machine must be
  of the series of the ``build-base`` declared in the ``imagecraft.yaml`` file.

  .. code-block:: bash

      sudo imagecraft --verbosity debug pack --destructive-mode

The resulting image file, ``pc.img``, will be deposited in the current directory.

.. note:: Without any specific option imagecraft will rely by default on ``LXD``
          to build the image. However this mode of operation is not working yet.


Run the image
--------------

Finally, test your new image with QEMU.

First, install QEMU and the Open Virtual Machine Firmware UEFI firmware for
64-bit x86 virtual machines:

.. code-block:: bash

    sudo apt install ovmf qemu-system-x86

Then, copy the UEFI variables to a temporary directory:

.. code-block::

    cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/OVMF_VARS_4M.fd

Boot the resulting image with QEMU:

.. code-block:: none

    qemu-system-x86_64 \
    -accel kvm \
    -m 4G \
    -cpu host \
    -smp 8 \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=/tmp/OVMF_VARS_4M.fd \
    -drive file=pc.img,format=raw,index=0,media=disk

The image should boot and give access to a shell.
