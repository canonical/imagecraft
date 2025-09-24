.. _reference-for-statements:

``for`` statements
==================

The ``for`` statement is a YAML selector that selects key values based on the build's
target platform. This allows the image to be catered to the needs of each platform
declared in its project file.


Syntax and behavior
-------------------

The ``for`` statement accepts a single platform as its argument.

.. code-block:: yaml

  <key>:
    - for <platform-1>: <value-1>
    [...]
    - for <platform-n>: <value-n>

If the build's target platform matches a ``for`` statement's specified platform, the
corresponding value will be assigned to the parent key.

.. Document the ``any`` platform when Imagecraft brings in craft-grammar 2.3.0

The same logic applies when assigning values to keys that expect lists.

.. code-block:: yaml

  <key>:
    - for <platform-1>:
      - <value-1>
    [...]
    - for <platform-n>:
      - <value-n>
    - <default>

If the build's target platform matches a ``for`` statement's specified platform, the
corresponding values will be appended to the parent key. Values that aren't nested in a
``for`` statement will be appended to the parent key regardless of the target platform.

.. Uncomment when Imagecraft brings in craft-grammar 2.3.0

.. ``for`` statements can also be followed by an optional ``else`` statement.

.. .. code-block:: yaml

..     <key>:
..       - for <platform-1>: <value-1>
..       - else: <default>

.. The body of the ``else`` statement will only be assigned to the parent key if the target
.. platform does not match the platform specified by the preceding ``for`` statement.


Example
-------

The following project file snippet declares two platforms, ``device`` and ``amd64``, and
platform-specific values for the ``source`` and ``build-environment`` keys in the
``node`` part.

.. code-block:: yaml

    platforms:
      device:
        build-on: [amd64, arm64]
        build-for: arm64
      amd64:

    [...]

    parts:
      node:
        plugin: dump
        source:
        - for device: https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-arm64.tar.gz
        - for amd64: https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-x64.tar.gz
        build-environment:
        - for device:
          - TARGET_ARCH: ARM64
        - for amd64:
          - TARGET_ARCH: AMD64
        - NAME: Node.js part
    [...]

The build for the ``device`` platform pulls the ARM64 source for the ``node`` part and
sets the ``TARGET_ARCH`` build environment variable to 'ARM64'. The build for the
``amd64`` platform pulls the x64 source and sets the ``TARGET_ARCH`` build environment
variable to 'AMD64'. The builds for both platforms set the ``NAME`` environment variable
to 'Node.js part'.

.. Revise and uncomment once we've built a bootable, multi-platform image

.. When crafting an image, the ``for`` statement is most commonly used to customize the
.. image's partitions and filesystem mount points, declared with the ``structure`` and
.. ``filesystems`` keys.

.. The following project file snippet declares platform-specific partitions through the use
.. of ``for`` statements in its ``structure`` key:

.. .. code-block:: yaml

..     platforms:
..       amd64:
..       raspi-arm64:
..         build-on: [amd64, arm64]
..         build-for: arm64

..     volumes:
..       pc:
..         schema: gpt
..         structure:
..           - for amd64:
..             - name: efi
..               type: C12A7328-F81F-11D2-BA4B-00A0C93EC93B
..               filesystem: vfat
..               role: system-boot
..               size: 256M
..           - for raspi-arm64:
..             - name: boot
..               role: system-boot
..               type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
..               filesystem: vfat
..               size: 512M
..           - name: rootfs
..             type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
..             filesystem: ext4
..             filesystem-label: writable
..             role: system-data
..             size: 6G

..     [...]

.. The resulting ``amd64`` image will contain the ``efi`` and ``rootfs`` partitions, while
.. the ``raspi-arm64`` image will contain the ``boot`` and ``rootfs`` partitions.
