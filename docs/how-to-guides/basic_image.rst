.. _howto_buld_basic_image:

===================
Build a basic image
===================

These instructions describe how to build a ``classic`` server 24.04 AMD64 Ubuntu image
with Imagecraft.

Prerequisites
-------------

- AMD64 machine with Ubuntu 24.04
- ``snapd`` installed
- 15GiB or more disk space to process the build and hold the resulting image

.. note:: Following instructions build an **AMD64** image on an **AMD64** machine.
          Building on another architecture would need several modifications not
          described on this page.

Install Imagecraft
~~~~~~~~~~~~~~~~~~

Imagecraft is only available as a snap in the ``latest/edge`` channel
`from the Snapstore <https://snapcraft.io/imagecraft>`_. Install it with:

.. code-block::

    sudo snap install --classic --edge imagecraft

Verify that ``imagecraft`` is properly installed:

.. code-block::

    imagecraft

.. important:: ``imagecraft`` requires **elevated permissions**. Run it with **root**
               privileges or using ``sudo`` if you plan on using the executing system
               as the build system ("destructive mode").


Prepare the configuration
-------------------------

Imagecraft configuration
~~~~~~~~~~~~~~~~~~~~~~~~

Save the following content as ``imagecraft.yaml``:

.. literalinclude:: code/basic_imagecraft.yaml
    :caption: imagecraft.yaml
    :language: yaml

.. note:: The name of the configuration file, ``imagecraft.yaml``, is **important**
          because Imagecraft uses it automatically.


Build the image
---------------

Build the image with destructive mode. In this case the machine must be of the series
of the ``build-base`` declared in the ``imagecraft.yaml`` file.

  .. code-block::

    sudo imagecraft --verbosity debug pack --destructive-mode


The resulting image file, ``pc.img``, is available in the current directory.

.. note:: Without any specific option imagecraft will rely by default on ``LXD``
          to build the image. However this mode of operation is not working yet.


Run the image
--------------

Test the resulting image with QEMU.

Copy UEFI variables to a temporary directory:

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
