Ubuntu Bootstrap plugin
=======================

The Ubuntu Bootstrap plugin can be used to build define needed information to build a rootfs via ubuntu-image.

Keywords
--------

This plugin uses the common :ref:`plugin <part-properties-plugin>` keywords.

Additionally, this plugin provides the plugin-specific keywords defined in the
following sections.

ubuntu_bootstrap_pocket
~~~~~~~~~~~~~~~~~~~~~~~
**Type:** string

**Default value:** "updates"

Pocket to use when configuring the sources list.


ubuntu_bootstrap_extra_snaps
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Type:** list of strings

List of snaps to add to the resulting image.


ubuntu_bootstrap_extra_packages
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
**Type:** list of strings

List of packages to add to the resulting image.

ubuntu_bootstrap_kernel
~~~~~~~~~~~~~~~~~~~~~~~
**Type:** string


Kernel package to install explicitly.


ubuntu_bootstrap_germinate
~~~~~~~~~~~~~~~~~~~~~~~~~~
**Type:** GerminateProperties


GerminateProperties
*******************

urls
++++

**Type:** list of unique URLs

branch
++++++

**Type:** string

names
+++++

**Type:** list of unique strings

vcs
+++

**Type:** boolean


Dependencies
------------

This plugin relies on ``ubuntu-image``. This dependency will be installed with the snap.


Example
-------

.. code-block:: yaml
    
  rootfs:
    plugin: ubuntu-bootstrap
    ubuntu-bootstrap-pocket: updates
    ubuntu-bootstrap-germinate:
      urls:
        - "git://git.launchpad.net/~ubuntu-core-dev/ubuntu-seeds/+git/"
      branch: jammy
      vcs: true
      names:
        - server
        - minimal
        - standard
    ubuntu-bootstrap-kernel: linux-image-generic
    ubuntu-bootstrap-extra-snaps: [core20, snapd]
    ubuntu-bootstrap-extra-packages: [hello-ubuntu-image-public]
