:orphan:

.. meta::
    :description: Learn about the new features, changes, and fixes introduced in Imagecraft 1.2.

.. _release-notes-imagecraft-1-2:

Imagecraft 1.2 release notes
============================

(Release date TBD)

Learn about the new features, changes, and fixes introduced in Imagecraft 1.2.
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

Imagecraft 1.2 brings the following features, integrations, and improvements.


BIOS fallback for EFI images
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On x86 targets (``build-for: amd64`` and ``build-for: i386``), Imagecraft now
installs the legacy BIOS (``i386-pc``) boot code into the image in addition to
the EFI bootloader, so images also boot on machines whose firmware lacks EFI
support. GPT-schema volumes need a BIOS Boot partition to embed the BIOS boot
code, and projects that install their own MBR boot code can opt out by
declaring a structure item with the ``mbr`` role in the volume definition.


Minor features
--------------

Imagecraft 1.2 brings the following minor changes.


<FEATURE A>
~~~~~~~~~~~

- <Add a short description of a minor change.>


Feature deprecations
--------------------

The following features are deprecated in Imagecraft 1.2.


<DEPRECATED FEATURE C>
~~~~~~~~~~~~~~~~~~~~~~

<Describe the deprecation status, alternatives, and migration guidance.>


Scheduled feature deprecations
------------------------------

The following features will be deprecated in Imagecraft <planned version>.


<FEATURE D>
~~~~~~~~~~~

<Describe planned deprecations that have been formally announced.>


Fixed bugs and issues
---------------------

The following issues have been resolved in Imagecraft 1.2.

- No entries yet.


Known issues
------------

The following issues were reported and are scheduled to be fixed in upcoming
patch releases.

See individual issue links for any mitigation.

- No entries yet.


Contributors
------------

We would like to express a big thank you to all the people who contributed to
this release.

Contributor list is pending.
