.. _reference-imagecraft-yaml:

imagecraft.yaml
===============

This reference describes the purpose, usage, and examples of all available keys in
an image's project file, ``imagecraft.yaml``.


Top-level keys
--------------

An Imagecraft project's top-level keys declare the image's descriptors and the
essential details of how it builds.

Top-level descriptors include the image's name, version, description, and license,
alongside operational values such as its supported architectures and build environment.

.. py:currentmodule:: imagecraft.models.project

.. kitbash-field:: Project name

.. kitbash-field:: Project title

.. kitbash-field:: Project version

.. kitbash-field:: Project license

.. kitbash-field:: Project summary

.. kitbash-field:: Project description

.. kitbash-field:: Project base

.. kitbash-field:: Project build_base
    :override-type: Literal['ubuntu@20.04', 'ubuntu@22.04', 'ubuntu@24.04']

.. kitbash-field:: Project platforms
    :override-type: dict[str, Platform]

.. kitbash-field:: Project parts
    :override-type: dict[str, Part]

.. kitbash-field:: Project volumes
    :override-type: dict[str, Volume]

.. kitbash-field:: Project filesystems
    :override-type: dict[str, FilesystemMount]


Part keys
---------

The ``parts`` key and its values declare the image's :ref:`parts <explanation-parts>`
and detail how they're built.

.. py:currentmodule:: craft_parts.parts

.. Main keys

.. kitbash-field:: PartSpec plugin
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec after
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec disable_parallel
    :prepend-name: parts.<part-name>

.. Pull step keys

.. kitbash-field:: PartSpec source
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec source_type
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec source_checksum
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec source_branch
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec source_tag
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec source_commit
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec source_depth
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec source_submodules
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec source_subdir
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec override_pull
    :prepend-name: parts.<part-name>

.. Overlay step keys

.. kitbash-field:: PartSpec overlay_files
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec overlay_packages
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec overlay_script
    :prepend-name: parts.<part-name>

.. Build step keys

.. kitbash-field:: PartSpec build_environment
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec build_packages
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec build_snaps
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec organize_files
    :prepend-name: parts.<part-name>

    Files from the build environment can be organized into specific partitions by
    prepending the destination path with the partition name, enclosed in parentheses.
    Source paths always reference the default partition.

.. kitbash-field:: PartSpec override_build
    :prepend-name: parts.<part-name>

.. Stage step keys

.. kitbash-field:: PartSpec stage_files
    :prepend-name: parts.<part-name>
    :override-type: list[str]

.. kitbash-field:: PartSpec stage_packages
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec stage_snaps
    :prepend-name: parts.<part-name>

.. kitbash-field:: PartSpec override_stage
    :prepend-name: parts.<part-name>

.. Prime step keys

.. kitbash-field:: PartSpec prime_files
    :prepend-name: parts.<part-name>
    :override-type: list[str]

.. kitbash-field:: PartSpec override_prime
    :prepend-name: parts.<part-name>

.. Permission keys

.. kitbash-field:: PartSpec permissions
    :prepend-name: parts.<part-name>

.. py:currentmodule:: craft_parts.permissions

.. kitbash-field:: Permissions path
    :prepend-name: parts.<part-name>.permissions.<permission>

.. kitbash-field:: Permissions owner
    :prepend-name: parts.<part-name>.permissions.<permission>

.. kitbash-field:: Permissions group
    :prepend-name: parts.<part-name>.permissions.<permission>

.. kitbash-field:: Permissions mode
    :prepend-name: parts.<part-name>.permissions.<permission>


Volume keys
-----------

The ``volumes`` key and its values declare the schema and layout of the image's
partitions.

.. py:currentmodule:: imagecraft.models.volume

.. kitbash-field:: Volume volume_schema
    :prepend-name: volumes.<volume-name>

.. kitbash-field:: Volume structure
    :prepend-name: volumes.<volume-name>
    :override-type: list[Partition]


Partition keys
--------------

The following keys can be declared for each partition listed in the ``structure`` key.

.. kitbash-field:: StructureItem name
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: StructureItem id
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: StructureItem role
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: StructureItem structure_type
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: StructureItem size
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: StructureItem filesystem
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: StructureItem filesystem_label
    :prepend-name: volumes.<volume-name>.structure.<partition>


Filesystem keys
---------------

The following keys can be declared for each filesystem mount listed.

.. py:currentmodule:: craft_parts.filesystem_mounts

.. kitbash-field:: FilesystemMountItem mount
    :prepend-name: filesystems.<filesystem-name>.<mount>
    :override-description:
    :skip-examples:

    **Description**

    The device's mount point.

    **Examples**

    .. code-block:: yaml

        mount: "/"

    .. code-block:: yaml

        mount: "/boot/efi"

.. kitbash-field:: FilesystemMountItem device
    :prepend-name: filesystems.<filesystem-name>.<mount>
    :override-description:
    :skip-examples:

    **Description**

    The device to be mounted. This must reference one of the partitions defined
    in ``volumes.<volume-name>.structure``.

    **Examples**

    .. code-block:: yaml

        device: "(default)"

    .. code-block:: yaml

        device: "(volume/pc/rootfs)"
