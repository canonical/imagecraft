.. meta::
    :description: Add custom package repositories to an image.

.. _add-package-repositories:

Add package repositories
========================

Before you can install packages into your image, either through the overlay file system
or after first boot, you'll need to add the corresponding package repositories. This is
done by defining the repository sources on your local machine and copying them to the
image with a part.

Define the repository sources
-----------------------------

In your project directory, create a directory to hold the repository sources:

.. code-block:: bash

   mkdir apt-config

In this directory, create a ``.sources`` file for each desired repository using the
DEB822 format. In each file, define the following fields:

.. list-table::
   :header-rows: 1

   * - Field
     - Value
   * - Types
     - ``deb`` for package binaries or ``deb-src`` for package sources
   * - URIs
     - The package repository's URIs
   * - Suites
     - The codenames for the desired distributions
   * - Components
     - The repository sections to include (e.g. ``main``, ``universe``)
   * - Signed-By
     - The path to the repository's signing key in the image

For example, the ``.sources`` file for the Fish shell PPA would contain:

.. code-block:: text

   Types: deb
   URIs: https://ppa.launchpadcontent.net/fish-shell/release-4/ubuntu
   Suites: noble
   Components: main
   Signed-By: /etc/apt/keyrings/fish-ppa.gpg

When setting the ``Signed-By`` path, consider where you'll store the signing key in the
final image. When you copy the key to the image later on, this path will need to match
its destination.

While most ``.sources`` files will closely resemble the previous example, the patterns
for your repository may differ. In such cases, refer to the `sources.list
<https://manpages.ubuntu.com/manpages/resolute/man5/sources.list.html#deb822-style-format>`_,
which contains a complete reference of the DEB822 format.

Download the signing key
------------------------

To download the repository's signing key, you'll need its fingerprint. If your PPA is on
Launchpad, copy its fingerprint from the "Technical details about this PPA" section.

Next, create another directory to hold the signing key:

.. code-block:: bash

   mkdir apt-config/keyrings


Then, download the signing key. To download the signing key for the Fish PPA, you'd run:

.. code-block:: bash

   FINGERPRINT=88421E703EDC7AF54967DED473C9FCC9E2BB48DA
   KEY_URL=”https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$FINGERPRINT”
   curl -fsSL $KEY_URL | gpg --dearmor > apt-config/keyrings/fish-ppa.gpg

Replace the fingerprint and destination file name with the values for your desired
repository.

Copy the sources to the image
-----------------------------

Copy the files you created to the image with a new part that uses the :ref:`dump plugin
<craft_parts_dump_plugin>` and the :ref:`organize <PartSpec.organize_files>` key. The
part for our Fish example is defined as:

.. code-block:: yaml

   parts:
     apt-config:
       plugin: dump
       source: apt-config/
       organize:
         fish-ppa.sources: (overlay)/etc/apt/sources.list.d/fish-ppa.sources
         keyrings/fish-ppa.gpg: (overlay)/etc/apt/keyrings/fish-ppa.gpg

Packages from the added repository can now be installed into the overlay file system
with subsequent parts or after booting the image.
