.. _reference-imagecraft-yaml:

imagecraft.yaml
===============

This reference describes the purpose, usage, and examples of all available keys in
an image's project file, ``imagecraft.yaml``.


Top-level keys
==============

.. kitbash-field:: craft_application.models.Project name

.. kitbash-field:: craft_application.models.Project title

.. kitbash-field:: craft_application.models.Project license

.. kitbash-field:: craft_application.models.Project summary

.. kitbash-field:: craft_application.models.Project description

.. kitbash-field:: craft_application.models.Project version

.. kitbash-field:: project.Project base

.. kitbash-field:: project.Project build_base

.. kitbash-field:: project.Project volumes
    :override-type: dict[str, Volume]

.. kitbash-field:: craft_application.models.Project parts
    :override-type: dict[str, Part]


Volume keys
===========

.. kitbash-field:: volume.Volume volume_schema
    :prepend-name: volumes.<volume-name>

.. kitbash-field:: volume.Volume structure
    :prepend-name: volumes.<volume-name>


Structure item keys
===================

.. kitbash-field:: volume.StructureItem name
    :prepend-name: volumes.<volume-name>.structure.<item-name>

.. kitbash-field:: volume.StructureItem id
    :prepend-name: volumes.<volume-name>.structure.<item-name>

.. kitbash-field:: volume.StructureItem role
    :prepend-name: volumes.<volume-name>.structure.<item-name>

.. kitbash-field:: volume.StructureItem structure_type
    :prepend-name: volumes.<volume-name>.structure.<item-name>

.. kitbash-field:: volume.StructureItem size
    :prepend-name: volumes.<volume-name>.structure.<item-name>

.. kitbash-field:: volume.StructureItem filesystem
    :prepend-name: volumes.<volume-name>.structure.<item-name>

.. kitbash-field:: volume.StructureItem filesystem_label
    :prepend-name: volumes.<volume-name>.structure.<item-name>
