.. _howto_buld_basic_image:

===================
Build a basic image
===================

These instructions describe how to build a ``classic`` server 24.04 AMD64 Ubuntu image with Imagecraft.

Prerequisites
-------------

- AMD64 machine with Ubuntu 18.04 or newer
- ``snapd`` installed
- 15GiB or more disk space to process the build and hold the resulting image

.. note:: Following instructions build an **AMD64** image on an **AMD64** machine. Building on another architecture would need several modifications not described on this page.

Install Imagecraft
~~~~~~~~~~~~~~~~~~

Imagecraft is only available as a snap in the `latest/edge` channel `from the Snapstore <https://snapcraft.io/imagecraft>`_. Install it with:

.. code-block::

    sudo snap install --classic --edge imagecraft

Verify that ``imagecraft`` is properly installed:

.. code-block::

    imagecraft

.. important:: ``imagecraft`` requires **elevated permissions**. Run it with **root** privileges or using ``sudo`` if you plan on using the executing system as the build system ("destructive mode").


Prepare the configuration
-------------------------

Imagecraft configuration
~~~~~~~~~~~~~~~~~~~~~~~~

Save the following content as ``imagecraft.yaml``:

.. literalinclude:: code/basic_imagecraft.yaml
    :language: yaml

.. note:: The name of the configuration file, ``imagecraft.yaml``, is **important** because Imagecraft uses it automatically.


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


Build the image
------------------------

The build can be run in 2 different environments:

- in a ``multipass`` VM:

  .. code-block::

    CRAFT_BUILD_ENVIRONMENT=multipass imagecraft --verbosity debug pack

- on the local machine, with destructive mode. In this case the machine should be of the series of the ``base`` declared in the ``imagecraft.yaml`` file.

  .. code-block::

    sudo imagecraft --verbosity debug pack --destructive-mode


The resulting image file, ``pc.img``, is available in the current directory.

.. note:: Without any specific option imagecraft will rely by default on ``LXD`` to build the image. However this mode of operation is not working yet due to a bug in ubuntu-image.


Run the image
--------------

Test the resulting image with QEMU.

Copy UEFI variables to a temporary directory:

.. code-block::

    cp /usr/share/OVMF/OVMF_VARS.fd /tmp/OVMF_VARS.fd

Boot the resulting image with QEMU:

.. code-block:: none

    qemu-system-x86_64 \
    -accel kvm \
    -m 2G \
    -cpu host \
    -smp 4 \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE.fd \
    -drive if=pflash,format=raw,file=/tmp/OVMF_VARS.fd \
    -drive file=pc.img,format=raw,index=0,media=disk

You should be able to log in with the user name and password defined in the cloud-init configuration.
