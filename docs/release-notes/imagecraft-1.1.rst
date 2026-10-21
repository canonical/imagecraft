.. meta::
    :description: Release notes for Imagecraft 1.1.

.. _release-notes-imagecraft-1-1:

Imagecraft 1.1 release notes
============================

21 October 2026

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

LXD build provider
~~~~~~~~~~~~~~~~~~

By default, Imagecraft 1.1 now builds in LXD containers instead of Multipass virtual machines.

If you previously chose a provider, clear the setting to return to the LXD default:

.. code-block:: bash

    snap unset imagecraft provider

To build with Multipass by default, run:

.. terminal::

    snap set imagecraft provider=multipass

You can also select a build provider for individual runs with the ``CRAFT_BUILD_ENVIRONMENT`` environment variable.

.. terminal::

    CRAFT_BUILD_ENVIRONMENT=multipass imagecraft pack


Rootless partition management with FUSE
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Imagecraft now exposes image partitions with FUSE instead of loop devices. Partitions
now show up as regular files instead of block devices, which could affect override
scripts that rely on the previous behavior.

Metadata inside generated images
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generated images now include an ``.image/metadata.yaml`` file in the main volume.
This metadata documents the Imagecraft version and the image's name, architecture, and
generation timestamp.

``canonical/craft-actions/imagecraft/pack`` GitHub action
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There is now a dedicated GitHub Action for packing images with Imagecraft. The
action installs and configures LXD and Imagecraft, packs the image at the root of the
repository, and exposes the packed images, the Imagecraft revision, and the LXD revision as outputs.

Add the action to a workflow with:

.. code-block:: yaml

    - name: Pack an image with Imagecraft
      uses: canonical/craft-actions/imagecraft/pack@v1

For all supported inputs and outputs, see the `action's README
<https://github.com/canonical/craft-actions/blob/main/imagecraft/pack/README.md>`_.


Minor features
--------------

Imagecraft 1.1 brings the following minor changes.

Smarter repacking
~~~~~~~~~~~~~~~~~

Imagecraft will now skip re-packing the image if the project is unchanged.

Experimental ``test`` command changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The experimental ``test`` command no longer falls back to reading test configuration
from ``spread.yaml`` when ``imagecraft-test.yaml`` is absent. Projects must define
their test configuration in ``imagecraft-test.yaml``.


Contributors
------------

We would like to express a big thank you to all the people who contributed to this release.

:literalref:`@bepri <https://github.com/bepri>`,
:literalref:`@cmatsuoka <https://github.com/cmatsuoka>`,
:literalref:`@gcomneno <https://github.com/gcomneno>`,
:literalref:`@jahn-junior <https://github.com/jahn-junior>`,
:literalref:`@lengau <https://github.com/lengau>`,
:literalref:`@medubelko <https://github.com/medubelko>`,
:literalref:`@mr-cal <https://github.com/mr-cal>`,
:literalref:`@nicolasbock-canonical <https://github.com/nicolasbock-canonical>`,
:literalref:`@smethnani <https://github.com/smethnani>`,
:literalref:`@steinbro <https://github.com/steinbro>`,
:literalref:`@tigarmo <https://github.com/tigarmo>`,
:literalref:`@upils <https://github.com/upils>`,
:literalref:`@vismaytiwari <https://github.com/vismaytiwari>`,
and :literalref:`@zhijie-yang <https://github.com/zhijie-yang>`.
