.. meta::
    :description: Learn about the new features, changes, and fixes introduced in Imagecraft 1.0.

.. _release-notes-imagecraft-1-0:

Imagecraft 1.0 release notes
============================

9 September 2026

Learn about the new features, changes, and fixes introduced in Imagecraft 1.0.
For information about the Imagecraft release policy, see the
:ref:`release_policy_and_schedule`.


Requirements and compatibility
------------------------------

To run Imagecraft, a system requires the following minimum hardware and installed
software. These requirements apply to local hosts as well as virtual machines and
container hosts.


System  requirements
~~~~~~~~~~~~~~~~~~~~~

- AMD64, ARM64, RISC-V 64-bit, PowerPC 64-bit little-endian, or S390x
  processor
- 2GB RAM
- 10GB available storage space
- Internet access for remote software sources and the Snap Store

Core features
-------------

Imagecraft 1.0 provides a declarative workflow for creating Ubuntu bootable images.
Project files define the image contents, partition layout, target platforms, and build
steps in one place.

Declarative image definitions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Images and their build environments are configured in a project file named ``imagecraft.yaml``.
This is where all of the image's essential details are declared, including its top-level descriptors,
compatible platforms, structure, and content. Images can include package repositories, custom files,
and cloud-init configuration. These features support repeatable setup of software, files, users, and
other instance settings when an image starts.


GPT and MBR partition layouts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Imagecraft supports GUID Partition Table (GPT) and :vale-ignore:`Master Boot Record` (MBR) volume schemas.
Partition definitions can specify filesystems, labels, sizes, roles, identifiers,
and explicit GPT partition numbers.


Filesystem and image preparation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The mmdebstrap plugin creates a Debian-based root file system and installs packages into
the image.

Snap preparation
~~~~~~~~~~~~~~~~

The Snap-preseed plugin prepares snaps for classic images. The UC-prepare plugin prepares
Ubuntu Core seed directories from model assertions and can preseed snaps before the first
boot.
