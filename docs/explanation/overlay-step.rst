.. _overlays:

Overlay step
============

Images are built in a sequence of five separate steps: pull, overlay,
build, stage and prime.

The overlay step is configured with overlay parameters.
To learn more about pull, build, stage and prime see
:doc:`/common/craft-parts/reference/part_properties`

The overlay step provides the means to refine the content of an image parts
after parts. ``overlay-script`` will run the provided script in this step.
The location of the overlay is made available in the ${CRAFT_OVERLAY}
environment variable. ``overlay`` can be used to specify which files will be
migrated to the next steps, and when omitted its default value will be ``"*"``.

.. Include a section about overlay parameters from the Craft Parts documentation.
.. include:: /common/craft-parts/explanation/overlay_parameters.rst
