.. meta::
    :description: How to include custom files in your image.

.. _include-local-files:

Include local files
===================

When crafting your image, you may need to copy custom scripts, pre-built packages,
or other static files from your local machine to the image's file system. This is done
by placing them in your image project directory and copying them to the overlay file
system with the :ref:`craft_parts_dump_plugin`.


Prepare the files
-----------------

In your project directory, create a directory to hold the custom files:

.. code-block:: bash

    mkdir my-files

Place the files you want to include in this directory, preserving the directory structure
they should have in the final image.


Copy the files to the image
---------------------------

Copy the files to the image with a new part that uses the :ref:`craft_parts_dump_plugin` and the :ref:`organize <PartSpec.organize_files>` key. This part must be processed after the root file system is in place.

For example, to copy the script ``my-files/my-script.sh`` to ``/usr/local/bin/``:

.. code-block:: yaml
    :caption: imagecraft.yaml

    parts:
      my-files:
        after: [rootfs]
        plugin: dump
        source: my-files/
        organize:
          my-script.sh: (overlay)/usr/local/bin/my-script.sh

The ``(overlay)/`` prefix in the destination file path causes the file to be copied
into the image's overlay file system, which is where the image's contents are
prepared.


Perform additional file operations
----------------------------------

To apply custom operations to the files, use the ``override-overlay`` key in a separate
part to run commands in the overlay file system.

For example, to modify the file permissions on ``/usr/local/bin/my-script.sh`` in the final
image:

.. code-block:: yaml
    :caption: imagecraft.yaml

    parts:
      my-files-perms:
        after: [my-files]
        plugin: nil
        override-overlay: |
          chmod +x /usr/local/bin/my-script.sh

This technique is not limited to custom scripts and can be used for key components of
the image. For example, to install a custom kernel from a set of ``.deb`` files, copy
the packages into the overlay and install them:

.. code-block:: yaml
    :caption: imagecraft.yaml

    parts:
      custom-kernel:
        after: [rootfs]
        plugin: dump
        source: my-files/
        organize:
          "*.deb": (overlay)/tmp/custom-kernel

      install-kernel:
        after: [custom-kernel]
        plugin: nil
        override-overlay: |
          apt-get install -y /tmp/custom-kernel/*.deb
          rm -rf /tmp/custom-kernel

For more information on the overlay step, see :ref:`explanation-overlay-step`.
