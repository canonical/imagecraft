|Release| |Documentation| |test|

.. |Release| image:: https://github.com/canonical/imagecraft/actions/workflows/release-publish.yaml/badge.svg?branch=main&event=push
   :target: https://github.com/canonical/imagecraft/actions/workflows/release-publish.yaml
.. |Documentation| image:: https://github.com/canonical/imagecraft/actions/workflows/docs.yaml/badge.svg?branch=main&event=push
   :target: https://github.com/canonical/imagecraft/actions/workflows/docs.yaml
.. |test| image:: https://github.com/canonical/imagecraft/actions/workflows/tests.yaml/badge.svg?branch=main&event=push
   :target: https://github.com/canonical/imagecraft/actions/workflows/tests.yaml
.. |coverageBadge| image:: https://codecov.io/gh/canonical/imagecraft/branch/main/graph/badge.svg?token=dZifVsQDUG
   :target: https://codecov.io/gh/canonical/imagecraft

**********
imagecraft
**********

The base repository for Imagecraft projects.

Description
-----------
Imagecraft is a craft tool used to create Ubuntu bootable images. It follows
the same principles as Snapcraft, but is focused on creating bootable images
instead.

Documentation
-------------

Imagecraft documentation is built from reStructuredText (``.rst``) files, most
of them under the ``docs/`` folder in the source tree. `Build and browse the
documentation locally`_ if you prefer, although the `product website`_ is
recommended.

Build and browse the documentation locally
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Clone the official source tree from GitHub into your computer's home directory.
Its default location will then be ``~/imagecraft/``. (You may clone the
`Imagecraft repository`_ directly. However, it's protected: if you plan on
`contributing to the project <#project-and-community>`_, consider forking it to
your own GitHub account then cloning that instead.)

Install the documentation tools:

.. code-block:: bash

   make setup-docs

Build and serve the documentation:

.. code-block:: bash

   make docs-auto

Point your web browser to address ``127.0.0.1:8080``.


.. LINKS
.. _Imagecraft repository: https://github.com/canonical/imagecraft
.. _product website: https://canonical-imagecraft.readthedocs-hosted.com
