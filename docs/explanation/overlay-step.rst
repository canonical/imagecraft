.. _overlays:

Overlay step
============

Images are built in a sequence of :doc:`five separate steps
</reference/part-lifecycle-details>` -- pull, overlay, build, stage, and prime.

The overlay step in each part provides the means to refine the contents of the
image. ``overlay-script`` will run the provided script in this step.
The location of the default overlay is made available in the ``${CRAFT_OVERLAY}``
environment variable.
The location of the partition-specific overlays is made available in the
``${CRAFT_<partition>_OVERLAY}`` environment variables.
``overlay`` can be used to specify which files will be
migrated to the next steps, and when omitted its default value will be ``"*"``.

.. Include a section about overlay parameters from the Craft Parts documentation.
.. include:: /common/craft-parts/explanation/overlay_parameters.rst
