.. meta::
    :description: How to automate the configuration of new instances with cloud-init.

.. _configure-instances-with-cloud-init:

Configure instances with cloud-init
===================================

Automating routine system setup, such as network configuration and user account
creation, cuts down on drudgery and ensures instances of your image are consistent. By
embedding a cloud-init configuration into your image, you can automatically set up new
instances whether they're running in the cloud, a local virtual machine, or bare metal.


Set up cloud init
-----------------

First, install cloud-init in your image as an overlay package. This is best done by
declaring a new part in your project file, similar to the following:

.. code-block:: yaml
    :caption: imagecraft.yaml

    parts:
    packages:
        plugin: nil
        overlay-packages:
        # ...
        - cloud-init

.. admonition:: Installing overlay packages
    :class: note

    To install overlay packages, you must first install a package manager within the
    overlay file system, such as APT with the :ref:`reference-mmdebstrap-plugin`.

In the directory containing your project file, create a directory to hold the cloud-init
configuration files

.. code-block:: bash

    mkdir cloud-init

In this directory, create a file named ``meta-data``. This file configures cloud-init
itself. In the file, paste the following content, replacing ``<id>`` with a meaningful
identifier for your image:

.. code-block:: yaml
    :caption: cloud-init/meta-data

    dsmode: local
    instance_id: <id>

The ``dsmode`` key is set to local because the configuration is being sourced locally,
not hosted on a network.


Declare which tasks to perform
------------------------------

Cloud-init sets up instances based on a file named ``user-data``. The individual tasks
performed during setup are determined by the modules declared in this file.

The `cloud-config module reference
<https://docs.cloud-init.io/en/latest/reference/modules.html>`__ contains a complete
list of the available modules, with descriptions and examples for each. Using this
reference, declare any modules necessary to set up your image.

The following example uses the `Users and Groups
<https://docs.cloud-init.io/en/latest/reference/modules.html#users-and-groups>`__ and
`Set Passwords
<https://docs.cloud-init.io/en/latest/reference/modules.html#set-passwords>`__ modules
to create a
new user account, change the default user's password to ``default-pw``, and require
passwords to be reset when the user first logs in:

.. code-block:: yaml
    :caption: cloud-init/user-data

    #cloud-config
    users:
    - default
    - {name: user}
    password: default-pw
    chpasswd:
    expire: true
    users:
        - name: user
        password: passw0rd
        type: text

Once you've written the file, validate it by installing cloud-init onto your local
machine and running the ``schema`` command:

.. code-block:: bash

    sudo apt install cloud-init
    cloud-init schema --config-file user-data --annotate

If any errors are listed in the output, resolve them before proceeding.


Copy cloud-init files
---------------------

Copy the cloud-init files from your project directory to the image with a new part that
uses the :ref:`craft_parts_dump_plugin` and the :ref:`PartSpec.organize_files` key. It
should be processed after your root file system and system packages are in place.

In our example image, it's written like this:

.. code-block:: yaml
    :caption: imagecraft.yaml

    parts:
    cloud-init:
        after: [rootfs, packages]
        plugin: dump
        source: cloud-init/
        organize:
        "*": /var/lib/cloud/seed/nocloud/

Now, any instances created from your image will be set up identically.
