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

.. kitbash-field:: craft_application.models.Project name

.. kitbash-field:: craft_application.models.Project title

.. kitbash-field:: craft_application.models.Project version

.. kitbash-field:: craft_application.models.Project license

.. kitbash-field:: craft_application.models.Project summary

.. kitbash-field:: craft_application.models.Project description

.. kitbash-field:: project.Project base

.. kitbash-field:: project.Project build_base

.. kitbash-field:: craft_application.models.Project platforms
    :override-type: dict[str, Platform]

.. kitbash-field:: craft_application.models.Project parts
    :override-type: dict[str, Part]

.. kitbash-field:: project.Project volumes
    :override-type: dict[str, Volume]


Part keys
---------

The ``parts`` key and its values declare the image's :ref:`parts <explanation-parts>`
and detail how they're built.

.. kitbash-field:: craft_parts.parts.PartSpec plugin
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec source
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec source_checksum
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec source_type
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec source_tag
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec source_branch
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec source_channel
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec source_commit
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec source_depth
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec source_submodules
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec source_subdir
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec disable_parallel
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec after
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec overlay_packages
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec overlay_script
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec overlay_files
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec organize_files
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec stage_files
    :prepend-name: parts.<part-name>
    :override-type: list[str]

.. kitbash-field:: craft_parts.parts.PartSpec stage_packages
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec stage_snaps
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec prime_files
    :prepend-name: parts.<part-name>
    :override-type: list[str]

.. kitbash-field:: craft_parts.parts.PartSpec build_packages
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec build_snaps
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec build_environment
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec build_attributes
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec override_pull
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec override_build
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec override_stage
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec override_prime
    :prepend-name: parts.<part-name>

.. kitbash-field:: craft_parts.parts.PartSpec permissions
    :prepend-name: parts.<part-name>


Volume keys
-----------

The ``volumes`` key and its values declare the schema and layout of the image's
partitions.

.. kitbash-field:: volume.Volume volume_schema
    :prepend-name: volumes.<volume-name>

.. kitbash-field:: volume.Volume structure
    :prepend-name: volumes.<volume-name>
    :override-type: list[Partition]


Partition keys
--------------

The following keys can be declared for each partition listed in the ``structure`` key.

.. kitbash-field:: volume.StructureItem name
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: volume.StructureItem id
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: volume.StructureItem role
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: volume.StructureItem structure_type
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: volume.StructureItem size
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: volume.StructureItem filesystem
    :prepend-name: volumes.<volume-name>.structure.<partition>

.. kitbash-field:: volume.StructureItem filesystem_label
    :prepend-name: volumes.<volume-name>.structure.<partition>
