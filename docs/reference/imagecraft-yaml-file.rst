.. _imagecraft-yaml-file:

``imagecraft.yaml`` file
========================

.. include:: image_parts/toc.rst

An Imagecraft project is defined in a YAML file named ``imagecraft.yaml``
at the root of the project tree in the filesystem.

This Reference section is for when you need to know which options can be
used, and how, in this ``imagecraft.yaml`` file.


``name``
--------

**Type**: string

**Required**: Yes

The name of the image. This value must:

- start with a lowercase letter [a-z];
- contain at least one letter;
- contain only lowercase letters [a-z], numbers [0-9] or hyphens;
- not end with a hyphen, and must not contain two or more consecutive
  hyphens.

``title``
---------

**Type**: string

**Required**: No

The human-readable title of the image. If omitted, defaults to ``name``.

``summary``
-----------

**Type**: string

**Required**: Yes

A short summary describing the image.

``description``
---------------

**Type**: string

**Required**: Yes

A longer, possibly multi-line description of the image.

``version``
-----------

**Type**: string

**Required**: Yes

The imagecraft configuration version, used to track changes to the configuration file.

``base``
--------

**Type**: string ``bare``

**Required**: Yes

``build-base``
--------------

**Type**: One of ``ubuntu@20.04 | ubuntu@22.04 | ubuntu@24.04 | devel``

**Required**: Yes

The system and version that will be used during the build, but not
included in the final image itself. It comprises the set of tools and libraries
that Imagecraft will use when building the image contents.

.. note::
   ``devel`` is a "special" value that means "the next Ubuntu version, currently
   in development". This means that the contents of this system changes
   frequently and should not be relied on for production rocks.

``platforms``
-------------

**Type**: dict

**Required**: Yes

The architecture of the image to create. Supported architectures are:
``amd64``, ``arm64``, ``armhf``, ``i386``, ``ppc64el``, ``riscv64`` and ``s390x``.

Entries in the ``platforms`` dict can be free-form strings, or the name of a
supported architecture (in Debian format).

.. warning::
   **All** target architectures must be compatible with the architecture of
   the host where Imagecraft is being executed (i.e. emulation is not supported
   at the moment).

``platforms.<entry>.build-for``
-------------------------------

**Type**: string | list[string]

**Required**: Yes, if ``<entry>`` is not a supported architecture name.

Target architecture the image will be built for. Defaults to ``<entry>`` that
is a valid, supported architecture name.

.. note::
   At the moment Imagecraft will only build for a single architecture, so
   if provided ``build-for`` must be a single string or a list with exactly one
   element.

``platforms.<entry>.build-on``
------------------------------

**Type**: string | list[string]

**Required**: Yes, if ``build-for`` is specified *or* if ``<entry>`` is not a
supported architecture name.

Host architectures where the image will be built. Defaults to ``<entry>`` if that
is a valid, supported architecture name.

.. note::
   At the moment Imagecraft will only build on a single architecture, so
   if provided ``build-on`` must be a single string or a list with exactly one
   element.

``parts``
---------

**Type**: dict

**Required**: Yes

The set of parts that compose the image's contents
(see :doc:`/common/craft-parts/reference/part_properties`).

``volumes``
---------

**Type**: dict (single entry)

**Required**: Yes

Structure and conten of the image. A volume represents a "disk".

``volumes.<entry>.schema``
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type**: string ``gpt``

**Required**: Yes

Partitioning schema to use.

``volumes.<entry>.structure``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Type**: dict (at least one entry)

**Required**: Yes

Structure of the image, defining partitions.

``volumes.<entry>.structure.<entry>.name``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Type**: string

**Required**: Yes

Structure item name. Must respect the following:
- contain only lowercase letters [a-z] or hyphens;
- cannot start or end with a hyphen;
- maximum length: 36 characters (maximum of a partition name
  for GPT in the UTF-16 character set);

Structure names must be unique in a volume.

``volumes.<entry>.structure.<entry>.id``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Type**: string

**Required**: No

GPT unique partition id.

``volumes.<entry>.structure.<entry>.role``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Type**: One of ``system-boot | system-data``

**Required**: Yes

Role defines a special role for this item in the image.
- ``system-boot``: Partition holding the boot assets.
- ``system-data``: Partition holding the main operating system data.

``volumes.<entry>.structure.<entry>.type``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Type**: string

**Required**: Yes

Type of structure. A GPT partition type GUID.

``volumes.<entry>.structure.<entry>.size``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Type**: string

**Required**: Yes

Size for structure item. Conforms to the IEC 80000-13 Standard.

.. collapse:: Example

    .. code-block:: yaml

        size: "6GiB"

``volumes.<entry>.structure.<entry>.filesystem``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Type**: One of ``fat16 | vfat | ext4 | ext3``

**Required**: Yes

Filesystem type.

``volumes.<entry>.structure.<entry>.filesystem``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Type**: string

**Required**: No

Filesystem label. Defaults to name of structure item.
Labels must be unique in a volume.


Example file
------------

.. collapse:: imagecraft.yaml

    .. literalinclude:: code/example/imagecraft.yaml
       :language: yaml
