.. _reference-imagecraft-yaml:

imagecraft.yaml
===============

This reference describes the purpose, usage, and examples of all available keys in
an image's project file, ``imagecraft.yaml``.


``Project`` keys
----------------

.. kitbash-field:: project.Project base

.. kitbash-field:: project.Project build_base

.. kitbash-field:: project.Project volumes
    :override-type: dict[str, Volume]


``Volume`` keys
---------------

.. kitbash-field:: volume.Volume volume_schema

.. kitbash-field:: volume.Volume structure


``StructureItem`` keys
----------------------

.. kitbash-field:: volume.StructureItem name

.. kitbash-field:: volume.StructureItem id

.. kitbash-field:: volume.StructureItem role

.. kitbash-field:: volume.StructureItem structure_type

.. kitbash-field:: volume.StructureItem size

.. kitbash-field:: volume.StructureItem filesystem

.. kitbash-field:: volume.StructureItem filesystem_label
