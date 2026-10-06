.. meta::
    :description: Release notes for Imagecraft 1.1.

.. _release-notes-imagecraft-1-1:

Imagecraft 1.1 release notes
============================

Learn about the new features, changes, and fixes introduced in Imagecraft 1.1.
For information about the Imagecraft release cycle, see the
:ref:`release_policy_and_schedule`.


Requirements and compatibility
------------------------------

To run Imagecraft, a system requires the following minimum hardware and
installed software. These requirements apply to local hosts as well as VMs and
container hosts.


Minimum hardware requirements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- AMD64, ARM64, RISC-V (RVA20), PPC64EL, or S390X-capable
  processor
- 2GB RAM
- 10GB available storage space
- Internet access for remote software sources and the Snap Store


Platform requirements
~~~~~~~~~~~~~~~~~~~~~

.. list-table::
  :header-rows: 1
  :widths: 1 3 3

  * - Platform
    - Version
    - Software requirements
  * - GNU/Linux
    - Popular distributions that ship with systemd and are `compatible with
      snapd <https://snapcraft.io/docs/installing-snapd>`_
    - systemd


What's new
----------

Imagecraft 1.1 brings the following features, integrations, and improvements.

Rootless partition management with :vale-ignore:`fusefile`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft now uses ``fusefile`` to create and access virtual partition block devices directly from
raw disk image files. This replaces the use of host loop devices (``losetup``) for partition operations,
enabling unprivileged and safer partition manipulation.

Metadata inside generated images
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generated images now include an ``.image/metadata.yaml`` file in the main volume.
This metadata documents the Imagecraft version, project name, architecture, and
generation timestamp, enabling inspection and traceability of packed image artifacts.

Direct bootloader configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Bootloader files and configuration are staged in the target partition filesystems before formatting. For BIOS
targets, boot code is installed after image assembly through a FUSE mount of the root partition.


Minor features
--------------

Imagecraft 1.1 brings the following minor changes.

Smarter repacking
~~~~~~~~~~~~~~~~~

Imagecraft will now skip re-packing the image if the project is unchanged.

Removal of deprecated ``spread.yaml`` fallback
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft no longer falls back to reading test project definitions from ``spread.yaml`` when
``imagecraft-test.yaml`` is absent. Projects must define their test configuration in ``imagecraft-test.yaml``.


Contributors
------------

We would like to express a big thank you to all the people who contributed to this release.

:literalref:`@bepri <https://github.com/bepri>`,
:literalref:`@cmatsuoka <https://github.com/cmatsuoka>`,
:literalref:`@gcomneno <https://github.com/gcomneno>`,
:literalref:`@jahn-junior <https://github.com/jahn-junior>`,
:literalref:`@lengau <https://github.com/lengau>`,
:literalref:`@mr-cal <https://github.com/mr-cal>`,
:literalref:`@nicolasbock-canonical <https://github.com/nicolasbock-canonical>`,
:literalref:`@smethnani <https://github.com/smethnani>`,
:literalref:`@steinbro <https://github.com/steinbro>`,
:literalref:`@tigarmo <https://github.com/tigarmo>`,
:literalref:`@upils <https://github.com/upils>`,
:literalref:`@vismaytiwari <https://github.com/vismaytiwari>`,
and :literalref:`@zhijie-yang <https://github.com/zhijie-yang>`.
