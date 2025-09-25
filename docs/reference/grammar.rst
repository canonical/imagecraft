.. _reference-grammar:

Grammar
=======

*Grammar* describes statements that select a project file's key values based on the
build target. This allows for an image to be catered to the needs of each platform
declared in its project file.


``for`` statements
------------------

The ``for`` statement selects key values based on the build's target platform, and
accepts a single platform as its argument.

.. code-block:: yaml

    <key>:
      - for <platform-1>: <value-1>
      [...]
      - for <platform-n>: <value-n>

If a ``for`` statement matches against the build's target platform, its value is
assigned.

The same logic applies when assigning values to lists.

.. code-block:: yaml

    <key>:
      - for <platform-1>:
        - <value-1>
      [...]
      - for <platform-n>:
        - <value-n>
      - <default>

If a ``for`` statement matches against the build's target platform, its values are
appended to the list. Values that aren't nested in a ``for`` statement are appended
regardless of the target platform.


The ``any`` platform
--------------------

``any`` is a platform that, when included in a ``for`` statement, will always match
against the build's target platform.

.. code-block:: yaml

    <key>:
      - for <platform-1>: <value-1>
      - for any: <default>

If no other ``for`` statements match against the build's target platform, the ``for
any`` statement's value is assigned. If multiple ``for`` statements match against the
build's target platform, the value of the first match is assigned.


``else`` clauses
----------------

A ``for`` statement can be followed by an optional ``else`` clause.

.. code-block:: yaml

    <key>:
      - for <platform-1>: <value-1>
      - else: <default>

The body of the ``else`` clause is only assigned if the preceding ``for`` statement
doesn't match against the build's target platform.

An ``else`` clause can only be attached to a single ``for`` statement. This means that
an ``else`` clause won't consider the outcome of any ``for`` statements besides the one
that comes immediately before it.

.. code-block:: yaml

    platforms:
      amd64:
      arm64:

    [...]

    build-packages:
      - for amd64:
        - git
      - for arm64:
        - python3-dev
      - else:
        - make

For a build targeting the ``amd64`` platform, the ``build-packages`` key would include
both ``git`` and ``make``. Despite the ``for amd64`` matching, the ``else`` statement's
values are still appended, as the ``for arm64`` statement didn't match.


Example
-------

The following project file snippet declares two platforms, ``device`` and ``amd64``, and
platform-specific values for the ``source`` and ``build-environment`` keys in the
``node`` part.

.. code-block:: yaml

    platforms:
      microwave:
        build-on: [amd64, arm64]
        build-for: arm64
      amd64:

    [...]

    parts:
      node:
        plugin: dump
        source:
        - for microwave: https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-arm64.tar.gz
        - for amd64: https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-x64.tar.gz
        build-environment:
        - for microwave:
          - TARGET_ARCH: ARM64
        - for amd64:
          - TARGET_ARCH: AMD64
        - NAME: Node.js part
    [...]

The build for the ``microwave`` platform pulls the ARM64 source for the ``node`` part
and sets the ``TARGET_ARCH`` build environment variable to 'ARM64'. The build for the
``amd64`` platform pulls the x64 source and sets the ``TARGET_ARCH`` build environment
variable to 'AMD64'. The builds for both platforms set the ``NAME`` environment variable
to 'Node.js part'.

After the grammar is resolved, the two builds are equivalent to those produced by the
following single-platform project files:

.. dropdown:: ``microwave`` project file after grammar resolution

    .. code-block:: yaml

        platforms:
          microwave:
            build-on: [amd64, arm64]
            build-for: arm64

        [...]

        parts:
          node:
            plugin: dump
            source: https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-arm64.tar.gz
            build-environment:
              - TARGET_ARCH: ARM64
              - NAME: Node.js part
        [...]

.. dropdown:: ``amd64`` project file after grammar resolution

    .. code-block:: yaml

        platforms:
          amd64:

        [...]

        parts:
          node:
            plugin: dump
            source: https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-x64.tar.gz
            build-environment:
              - TARGET_ARCH: AMD64
              - NAME: Node.js part
        [...]

.. Revise and uncomment once we've built a bootable, multi-platform image

.. When crafting an image, the ``for`` statement is used to customize the image's
.. partitions and filesystem mount points, declared with the ``structure`` and
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
