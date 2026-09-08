.. _explanation-overlay-step:

Overlay step
============

Images are built in a sequence of :ref:`five separate steps <lifecycle>` -- pull,
overlay, build, stage, and prime.

The overlay step in each part provides the means to refine the contents of the
image. ``overlay-script`` will run the provided script in this step.
The location of the default overlay is made available in the ``${CRAFT_OVERLAY}``
environment variable.
The location of the partition-specific overlays is made available in the
``${CRAFT_<partition>_OVERLAY}`` environment variables.
``overlay`` can be used to specify which files will be
migrated to the next steps, and when omitted its default value will be ``"*"``.

Example part using ``override-overlay``
--------------------------------------

Use ``override-overlay`` when a part needs to replace the default overlay step
with custom shell commands.

.. code-block:: yaml

   parts:
     efi-packages:
       plugin: nil
       after: [rootfs]
       override-overlay: |
         ARCH="$(dpkg --print-architecture)"
         if [ "$ARCH" = "amd64" ]; then
           URL="http://archive.ubuntu.com/ubuntu"
         else
           URL="http://ports.ubuntu.com/ubuntu-ports"
         fi

         echo "deb $URL noble main" > /etc/apt/sources.list
         apt-get update
         apt-get install -y grub-efi-$ARCH

.. Include a section about overlay parameters from the Craft Parts documentation.
.. include:: /common/craft-parts/explanation/overlay_parameters.rst
