.. meta::
    :description: Learn about the new features, changes, and fixes introduced in Imagecraft 1.0.

.. _release-notes-imagecraft-1-0:

Imagecraft 1.0 release notes
============================

10 September 2026

Learn about the new features, changes, and fixes introduced in Imagecraft 1.0.
For information about the Imagecraft release policy, see the
:ref:`release_policy_and_schedule`.


Requirements and compatibility
------------------------------

To run Imagecraft, a system requires the following minimum hardware and installed
software. These requirements apply to local hosts as well as virtual machines and
container hosts.


- AMD64, ARM64, RISC-V 64-bit, PowerPC 64-bit little-endian, or S390x
  processor
- 2GB RAM
- 10GB available storage space
- Internet access for remote software sources and the Snap Store

Core features
-------------

Imagecraft 1.0 provides a declarative workflow for creating Ubuntu bootable images.

Declarative image definitions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Images and their build environments are configured in a project file named ``imagecraft.yaml``.
This is where all of the image's essential details are declared, including its top-level descriptors,
compatible platforms, structure, and content.


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

Imagecraft ships with two plugins for pre-installing snaps and reducing the initial boot time of the resulting images:
Snap-preseed and UC-Prepare. The Snap-preseed plugin builds the scaffolding of any listed snaps directly into classic
images. Similarly, the UC-prepare plugin prepares the seed directory for Ubuntu Core images by installing the snaps
listed in the provided model assertion.
