.. meta::
    :description: How to include custom files in your image.

.. _include-custom-files:

Include custom files
====================

Images may need to include arbitrary files, such as custom scripts or packages beyond what's available in package archives. You can include custom files in your image by placing them in your project directory and
copying them to the overlay file system with a part that uses the :ref:`dump plugin
<craft_parts_dump_plugin>`.

To apply a configuration at first boot rather than baking it into the image, see :ref:`configure-instances-with-cloud-init`.


Prepare the files
-----------------

In your project directory, create a directory to hold the custom files:

.. code-block:: bash

    mkdir my-files

Place the files you want to include in this directory, preserving any directory structure
that they should have in the final image.


Copy the files to the image
---------------------------

Copy the files to the image with a new part that uses the :ref:`dump plugin
<craft_parts_dump_plugin>` and the :ref:`organize <PartSpec.organize_files>` key. The
part should run after the root file system is in place.

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

The ``(overlay)/`` prefix ensures the file is copied to the overlay file system and
appears in the final image at the specified path.

Apply custom operations
-----------------------

To apply custom operations to the files, use the ``override-overlay`` key to run
commands in the overlay file system.

For example, to set the file permissions on ``/usr/bin/local/my-script.sh`` in the final image:

.. code-block:: yaml
    :caption: imagecraft.yaml

    parts:
      my-files-perms:
        after: [my-files]
        plugin: nil
        override-overlay: |
          chmod +x /usr/local/bin/my-script.sh

For more information on the overlay step, see :ref:`explanation-overlay-step`.
