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

Similar logic applies when assigning values to lists.

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


``any`` platform
----------------

``any`` is a platform that, when included in a ``for`` statement, will always match
against the build's target platform.

.. code-block:: yaml

    <key>:
      - for <platform-1>: <value-1>
      - for any: <default>

If no other ``for`` statements match against the build's target platform, the ``for
any`` statement's value is assigned. If the key expects a single value and multiple
``for`` statements match against the build's target platform, the value of the first
match is assigned.

If a ``for any`` statement is included in a list, its items will always be appended.

.. code-block:: yaml

    <key>:
      - for <platform-1>:
        - <value-1>
      [...]
      - for <platform-n>:
        - <value-n>
      - for any:
        - <default>

Placing list items in a ``for any`` statement is equivalent to placing them in the
list without a ``for`` statement.


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
    :caption: imagecraft.yaml

    platforms:
      laptop:
        build-on: amd64
        build-for: amd64
      dev-board:
        build-on: [amd64, arm64]
        build-for: arm64

    [...]

    build-packages:
      - for laptop:
        - git
      - for dev-board:
        - python3-dev
      - else:
        - make

For a build targeting the ``laptop`` platform, the ``build-packages`` key would include
both ``git`` and ``make``. Despite ``for laptop`` matching, the ``else`` statement's
values are still appended, as the ``for dev-board`` statement didn't match.


Example
-------

The following project file snippet declares two platforms, ``laptop`` and ``dev-board``,
and platform-specific values for the ``source`` and ``build-environment`` keys in the
``node`` part.

.. code-block:: yaml
    :caption: imagecraft.yaml

    platforms:
      laptop:
        build-on: amd64
        build-for: amd64
      dev-board:
        build-on: [amd64, arm64]
        build-for: arm64

    [...]

    parts:
      node:
        plugin: dump
        source:
        - for laptop: https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-x64.tar.gz
        - for dev-board: https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-arm64.tar.gz
        build-environment:
        - for laptop:
          - DISPLAY: Idle
        - for dev-board:
          - BOARD_STATUS: Ready
        - NAME: Node.js part
    [...]

The build for the ``laptop`` platform pulls the x64 source for the ``node`` part and
sets the ``DISPLAY`` build environment variable to ``Idle``. The build for the
``dev-board`` platform pulls the arm64 source and sets the ``BOARD_STATUS`` build
environment variable to ``Ready``. The builds for both platforms set the ``NAME``
environment variable to ``Node.js part``.

After the grammar is resolved, the two builds are equivalent to those produced by the
following single-platform project files:

.. dropdown:: ``laptop`` project file after grammar resolution

    .. code-block:: yaml
        :caption: imagecraft.yaml:

        platforms:
          laptop:
            build-on: amd64
            build-for: amd64

        [...]

        parts:
          node:
            plugin: dump
            source: https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-x64.tar.gz
            build-environment:
              - DISPLAY: Idle
              - NAME: Node.js part
        [...]

.. dropdown:: ``dev-board`` project file after grammar resolution

    .. code-block:: yaml
        :caption: imagecraft.yaml

        platforms:
          dev-board:
            build-on: [amd64, arm64]
            build-for: arm64

        [...]

        parts:
          node:
            plugin: dump
            source: https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-arm64.tar.gz
            build-environment:
              - BOARD_STATUS: Ready
              - NAME: Node.js part
        [...]

.. Revise and uncomment once we've built a bootable, multi-platform image

.. When crafting an image, ``for`` statements are used to customize the image's
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
