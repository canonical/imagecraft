.. imagecraft documentation root file

Imagecraft
==========

**Imagecraft is a tool for creating bootable Ubuntu images.** It is a craft tool, which means it is based on the `Snapcraft framework`_.

Imagecraft assembles bootable images of Ubuntu for various deployments. It simplifies and standardises the image-building process and reduces duplicated ways of building Ubuntu images.

Imagecraft can be used for operating-system testing, as well as for creating custom Ubuntu images for specific use cases.

Its users include the Canonical Public Cloud team, distribution maintainers using the ``livecd-rootfs`` build system, and system administrators.

.. important:: ``imagecraft`` is **not production ready**. Please only use it to experiment building images and provide feedback.

.. toctree::
   :maxdepth: 1
   :hidden:

   tutorials/index
   howto/index
   reference/index
   explanation/index

.. grid:: 1 1 2 2

   .. grid-item-card:: :ref:`Tutorials <tutorials>`
       :link: tutorials/index
       :link-type: doc

       **Get started** with a hands-on introduction to Imagecraft

   .. grid-item-card:: :ref:`How-to guides <howto>`
       :link: howto/index
       :link-type: doc

       **Step-by-step guides** covering key operations and common tasks

.. grid:: 1 1 2 2
   :reverse:

   .. grid-item-card:: :ref:`Reference <reference>`
       :link: reference/index
       :link-type: doc

       **Technical information** about Imagecraft

   .. grid-item-card:: :ref:`Explanation <explanation>`
       :link: explanation/index
       :link-type: doc

       **Discussion and clarification** of key topics

Project and community
---------------------

Imagecraft is a member of the Canonical family. It's an open source project that warmly welcomes community projects, contributions, suggestions, fixes and constructive feedback.

Get started:
  * Read our `Code of Conduct`_

Discuss:
  * Discourse: `Ubuntu Foundations`_

..   * IRC: `Libera.Chat`_, the *#ubuntu-server* channel

Contribute:
  * `Contribution guidelines`_ on GitHub
  * `Issue tracker`_ on GitHub

.. Links:
.. _Code of Conduct: https://ubuntu.com/community/ethos/code-of-conduct
.. _Ubuntu Foundations: https://discourse.ubuntu.com/c/foundations/
.. _Libera.Chat: https://libera.chat/
.. _Contribution guidelines: https://github.com/canonical/imagecraft/blob/main/HACKING.rst
.. _Issue tracker: https://github.com/canonical/imagecraft/issues/
.. _Snapcraft framework: https://snapcraft.io/
