.. meta::
    :description: Imagecraft is the command-line tool for building bootable,
                  pre-installed disk images.

Imagecraft
==========

**Imagecraft** is the command-line tool for building bootable, pre-installed disk
images.

The tool builds images from a declarative project file written with the shared syntax of
the craft apps. Builds take place in an isolated environment and follow a series of
consistent, reproducible steps that can be adjusted for individual images.

Imagecraft simplifies image customization and maintenance by keeping the image's
essential details in one place. Work that normally requires disparate tools and manual
adjustments can be done by editing the project file and rebuilding your image.

Imagecraft is for DevOps and platform engineers, systems administrators, and hobbyists
who create and maintain images for embedded, IoT, and cloud systems.


In this documentation
---------------------

.. list-table::
    :widths: 35 65
    :header-rows: 0

    * - **Tutorial**
      - :ref:`tutorial-describe-the-image` • :ref:`tutorial-define-the-partitions` •
        :ref:`tutorial-set-up-the-root-file-system` •
        :ref:`tutorial-add-essential-packages` • :ref:`tutorial-pack-the-image`
    * - **Vocabulary and syntax**
      - :ref:`commands` • :ref:`reference-imagecraft-yaml` •
        :ref:`reference-platform-grammar`


How this documentation is organized
-----------------------------------

The Imagecraft documentation embodies the `Diátaxis framework <https://diataxis.fr/>`__.

* The :ref:`tutorial <tutorials>` is a lesson that works through the process of building
  an image.
* :ref:`References <reference>` describe the structure and function of the individual components in
  Imagecraft.
* :ref:`Explanations <explanation>` aid in understanding the concepts and relationships
  of Imagecraft as a system.


Project and community
---------------------

Imagecraft is a member of the Canonical family. It's an open source project that warmly
welcomes community projects, contributions, suggestions, fixes, and constructive
feedback.


Get involved
~~~~~~~~~~~~

* `Starcraft Development Matrix space <https://matrix.to/#/#starcraft-development:ubuntu.com>`__
* `Contribute to Imagecraft development <https://github.com/canonical/snapcraft/blob/main/CONTRIBUTING.md>`__
* :ref:`contribute-to-this-documentation`


Governance and policies
~~~~~~~~~~~~~~~~~~~~~~~

* `Ubuntu Code of Conduct <https://ubuntu.com/community/docs/ethos/code-of-conduct>`__
* `Canonical Contributor License Agreement
  <https://ubuntu.com/legal/contributors>`__


.. toctree::
    :hidden:

    tutorials/index
    reference/index
    explanation/index

.. toctree::
    :hidden:

    contribute-to-this-documentation
