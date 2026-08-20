.. meta::
    :description: Release notes for Imagecraft 0.2.

.. _release-0.2:

Imagecraft 0.2 release notes
============================

11 August 2026

Learn about the new features, changes, and fixes introduced in Imagecraft 0.2.


Requirements and compatibility
------------------------------

To run Imagecraft, a system requires the following minimum hardware and installed
software. These requirements apply to local hosts as well as VMs and container
hosts.


Minimum hardware requirements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- AMD64 or ARM64 processor
- 2GB RAM
- 10GB available storage space
- Internet access for remote software sources


Platform requirements
~~~~~~~~~~~~~~~~~~~~~

.. list-table::
  :header-rows: 1
  :widths: 1 3 3

  * - Platform
    - Version
    - Software requirements
  * - GNU/Linux
    - Popular distributions that ship with systemd and are compatible with
      snapd
    - systemd


Backwards-incompatible changes
------------------------------

The following changes are incompatible with previous versions of Imagecraft.


Disabled untested plugins
~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now disables untested plugins by default. If you need a plugin from
another craft, please request it as a feature request.


What's new
----------

Support for MBR volume schemas
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now accepts ``mbr`` volume schemas. MBR images are now supported on x86,
and Imagecraft generates the GRUB assets needed for them.


New plugins
~~~~~~~~~~~


Support for snap prepare-image plugins
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Imagecraft now includes ``snap-preseed`` and ``uc-prepare`` plugins for core and
classic images. See :ref:`reference-snap-preseed-plugin` and
:ref:`reference-uc-prepare-plugin` for the full plugin reference.


Support for the mmdebstrap plugin
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Imagecraft now includes an ``mmdebstrap`` plugin for building Debian-derived root
filesystems. See :ref:`reference-mmdebstrap-plugin` for the full plugin reference.


Improved boot image generation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now uses ``grub-mkimage`` asset generation instead of mounting the target
root filesystem and running ``grub-install``. This makes boot asset generation more
reliable during packing.

Support for writing to specific sectors
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now writes volume data to temporary image files during lifecycle commands,
which lets it place data in specific sectors of the final output image.


Support for Ubuntu 26.04 as a build base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now accepts ``ubuntu@26.04`` as a build base.


Improved overlay handling
~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now enables ``override-overlay`` for image builds. See
:ref:`explanation-overlay-step` for more details.

Contributors
------------

We would like to express a big thank you to all the people who contributed to this
release.

:literalref:`@Aeonoi <https://github.com/Aeonoi>`,
:literalref:`@asanvaq <https://github.com/asanvaq>`,
:literalref:`@atandrewlee <https://github.com/atandrewlee>`,
:literalref:`@bepri <https://github.com/bepri>`,
:literalref:`@canon-cat <https://github.com/canon-cat>`,
:literalref:`@clay-lake <https://github.com/clay-lake>`,
:literalref:`@cmatsuoka <https://github.com/cmatsuoka>`,
:literalref:`@EddyPronk <https://github.com/EddyPronk>`,
:literalref:`@EdmilsonRodrigues <https://github.com/EdmilsonRodrigues>`,
:literalref:`@ethandcosta <https://github.com/ethandcosta>`,
:literalref:`@FinnRG <https://github.com/FinnRG>`,
:literalref:`@gcomneno <https://github.com/gcomneno>`,
:literalref:`@Guillaumebeuzeboc <https://github.com/Guillaumebeuzeboc>`,
:literalref:`@HamdaanAliQuatil <https://github.com/HamdaanAliQuatil>`,
:literalref:`@jahn-junior <https://github.com/jahn-junior>`,
:literalref:`@lengau <https://github.com/lengau>`,
:literalref:`@mateusrodrigues <https://github.com/mateusrodrigues>`,
:literalref:`@medubelko <https://github.com/medubelko>`,
:literalref:`@mr-cal <https://github.com/mr-cal>`,
:literalref:`@mwhudson <https://github.com/mwhudson>`,
:literalref:`@PraaneshSelvaraj <https://github.com/PraaneshSelvaraj>`,
:literalref:`@smethnani <https://github.com/smethnani>`,
:literalref:`@Spilsed <https://github.com/Spilsed>`,
:literalref:`@steinbro <https://github.com/steinbro>`,
and :literalref:`@tigarmo <https://github.com/tigarmo>`.
