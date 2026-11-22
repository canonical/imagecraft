.. _reference-parts-and-steps:

.. include:: /common/craft-parts/reference/parts_steps.rst

.. include:: /common/craft-parts/reference/step_execution_environment.rst

Volume environment variables
----------------------------

Imagecraft makes each volume image and its partition devices available in the step
execution environment:

* ``CRAFT_VOLUME_<VOLUME>`` points to the volume's raw image file.
* ``CRAFT_VOLUME_<VOLUME>_<PARTITION>`` points to a partition's virtual device.

Volume and partition names are uppercase in the variable name. Imagecraft replaces
slashes and hyphens in those names with underscores. For example, a volume named
``pc`` and its ``rootfs`` partition are available as ``CRAFT_VOLUME_PC`` and
``CRAFT_VOLUME_PC_ROOTFS``.

.. include:: /common/craft-parts/reference/step_output_directories.rst

.. include:: /common/craft-parts/reference/partition_specific_output_directory_variables.rst
