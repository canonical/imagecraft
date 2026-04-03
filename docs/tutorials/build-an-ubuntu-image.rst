.. meta::
    :description: Learn how to build a basic Ubuntu image with Imagecraft.

.. _tutorial-build-an-ubuntu-image:

Build an Ubuntu image
=====================

In this tutorial, we'll build a basic Ubuntu image. We'll set up the project, define the
image's partitions and content, and run the image with QEMU.

You won't need to come prepared with an intimate understanding of software packaging or
disk images, but familiarity with Linux paradigms and terminal operations is required.

By the end of this tutorial, you'll have crafted an image that can serve as the basis
for future projects.


Lesson plan
-----------

This tutorial takes about 25 minutes to complete and works through the process of
building an image. You'll be shown how to:

* Set up an image project from scratch
* State the project's essential information
* Set up the image's partitions and root file system
* Add packages to the image
* Set a default user and password
* Package the image


What we'll work with
--------------------

The object of this tutorial is to build a minimal, pre-installed Ubuntu image for AMD64
machines.

The final image will be named ``disk.img``, and we'll end the tutorial by running and
testing it with QEMU.


What you'll need
----------------

For this tutorial, you'll need:

* An AMD64 machine running Ubuntu 24.04 LTS
* Super user privileges on your machine
* 10GiB of available storage


Install prerequisites
---------------------

To begin, we'll need to install the Imagecraft snap. Open a terminal and run:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: snap install imagecraft --channel=beta --classic
    :end-at: snap install imagecraft --channel=beta --classic

Let's also install Multipass, which will create the build environment when it comes
time to package our image.

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: snap install multipass
    :end-at: snap install multipass


Set up the project
------------------

We'll need a directory to hold our image project. Navigate to where you like to keep
software projects and create the new directory with:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: mkdir ubuntu-minimal
    :end-at: cd ubuntu-minimal


Images are built and configured through an ``imagecraft.yaml`` file, called the *project
file*. Let's create one in the new project directory with the ``init`` command.

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: imagecraft init
    :end-at: imagecraft init

The generated project file will be our focus for most of this tutorial. Open it in your
preferred text editor.


Describe the image
------------------

An image's project file starts with its most essential descriptors, such as its name,
version, and build environment. The comments in the template describe each of the keys.

The ``init`` command filled out these top-level keys but left out some project-specific
details. Let's update the ``summary`` and ``description`` keys to better reflect our new
project. Replace the first six keys with:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :start-at: name: ubuntu-minimal
    :end-at: Ubuntu 24.04 LTS, and it's booted with GRUB

The ``base`` key defines the foundation for the image's contents. In Imagecraft, this is
always an empty directory, known as the *bare* base.

The ``build-base`` key defines the system that's used to assemble the image. It does
*not* have any influence on the image's contents. It's best to build with the latest
Ubuntu LTS release in most cases, so we left this unchanged.

The ``summary`` and ``description`` keys tell consumers of our image a little more
about it. The summary is a one-line description, limited at 79 characters, while the
description is more open-ended and can span multiple lines. These were both placeholders
in the template project file, so we made them meaningful for our project.


.. Define the target platform
.. --------------------------

.. We need to tell Imagecraft what CPU architecture our image builds and runs on. This is
.. done with the ``platforms`` key.

.. An image's target architecture influences its structure and contents, so its project
.. file must be customized to each platform. Since we'll be building our image for AMD64
.. machines, and our project file already targets the AMD64 architecture, we'll leave the
.. ``platforms`` key as is.


Define the partitions
---------------------

Now that we've described our image and declared its essential build details, we need to
define its disk partitions. To do so, we'll customize the ``volumes`` key.

Our project file contains a single volume, named ``disk``. The ``schema`` key tells us
that the volume is partitioned with GPT, the only schema currently supported by
Imagecraft. We'll define individual partitions in the volume's ``structure`` key.

Our image will have two partitions: a root file system and an EFI system partition. The
first was created for us automatically. Before we go over its contents, let's also
define an EFI system partition for our image to boot from. Add the following highlighted
lines after the ``rootfs`` partition:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :class: no-copybutton
    :start-at: volumes:
    :end-at: size: 256M
    :emphasize-lines: 11-16

There's a lot to unpack here. Let's take a moment to go over each of the ``efi``
partition's keys and compare them to the ``rootfs`` partition.

We declared that this is the boot partition by setting the ``role`` key to
``system-boot``. The ``rootfs`` partition's ``role`` key was set to ``system-data``,
which tells Imagecraft that it contains the operating system.

We set the ``type`` key to the identifier for EFI system partitions in a GUID partition
table. The ``rootfs`` partition was generated with the identifier for Linux file
systems. The identifiers themselves come from the UEFI specification—don't worry about
memorizing them.

We set the ``filesystem`` key to ``vfat``, the most common file system for EFI system
partitions. Since the ``rootfs`` partition will be for general usage, it's using the
ext4 filesystem instead.

In both partitions, the ``filesystem-label`` key is set to a unique, human-readable
name. We'll use these labels when we set up the file system table later on.


Mount the partitions
--------------------

Our image's partitions are ready, but we haven't told Imagecraft where to mount them in
the image's file system. Let's shift our focus to the ``filesystems`` key.

The ``filesystems`` key maps the image's partitions to their mount points. It expects a
single file system, named ``default``, that mounts a partition to the root of the image.
The ``filesystems`` key in our project file already mounts the ``rootfs`` partition to the
image's root, but we'll still need to mount the EFI system partition.

Add the following highlighted lines to the end of the ``filesystems`` key:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :class: no-copybutton
    :start-at: filesystems:
    :end-at: mount: /boot/efi
    :emphasize-lines: 5, 6

With this entry, we mounted the EFI system partition to the /boot/efi/ directory in the
final image. Keep in mind that we'll need to create this directory ourselves when we set
up the image's root file system.


Set up the root file system
---------------------------

Because we're building our image on the bare base, its file system is currently an empty
directory. Let's start building our Ubuntu file system with the ``parts`` key.

*Parts* are the means by which we source packages for and manipulate the files in our
image. Most importantly, they give us access to the *overlay file system*, which is
where we'll manipulate our image's contents.

We'll create our file system with ``mmdebstrap``, a command-line tool for setting up
Debian root file systems. The part we create for it will use the ``mmdebstrap`` plugin,
which calls its primary command under the hood, and copy the resulting file system
into our image.

In the ``parts`` key, replace the template part with the following ``rootfs`` part:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :start-at: parts:
    :end-at: - apt

The ``plugin`` key specifies the build system needed to prepare the part. Here, we use
the ``mmdebstrap`` plugin, which handles the complexity of creating a root file system
for us.

The ``mmdebstrap-suite`` key specifies the package suite to bootstrap, ``noble`` (Ubuntu
24.04) in this case. The ``mmdebstrap-variant`` key sets the base package set to
``minbase``, providing a minimal system. We add ``apt`` to ``mmdebstrap-packages`` to
ensure package management is available.

By default, the plugin removes default source lists, which will only allow us to install
system packages from the ``noble`` suite's ``main`` component. We still need to replace
the source list to install a wider array of packages and to create the ``/boot/efi/``
directory to mount the ``efi`` partition to. We can tackle both of these items by adding
the following highlighted lines to the end of the ``override-build`` script:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :class: no-copybutton
    :lines: 39-55
    :emphasize-lines: 7-17

The ``craftctl default`` command runs the plugin's default build commands before our
custom script. We then create the ``/boot/efi/`` directory and write a custom sources
configuration that gives us access to the wider array of packages.

At this point, the file system only exists in the ``rootfs`` part. To get it into the
final image, we'll need to copy it into the overlay file system. We can do so with the
``organize`` key and the ``(overlay)/`` prefix. Add the following highlighted lines to
the ``rootfs`` key:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :class: no-copybutton
    :start-at: rootfs:
    :end-at: '*': (overlay)/
    :emphasize-lines: 18, 19

This copies the result of the part's build step to the root of the overlay file system,
thereby securing its place in the final image.


Add essential packages
----------------------

We'll need some additional packages for our image to be bootable. Let's define a new
part to source them. In this case, we don't need a build system, so we set the
``plugin`` key to ``nil``. Add the following ``packages`` part:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :lines: 59-67

With the exception of ``sl``, these packages add the system's essential components, such
as the kernel, core utilities, and boot loader.

We added the ``sl`` package to ensure that we can source packages from the extra
components of the ``noble`` suite we added in the ``rootfs`` part. This isn't essential,
but it's a fun way to test our image later.


Create the file system table
----------------------------

If we tried to boot our image, its partitions wouldn't be mounted. This is because
Imagecraft requires that we create our file system table manually. The content of this
table is similar to what we declared in the ``filesystems`` key, with some additional
configuration.

With how we set up our partitions and mount points, the table should read:

.. code-block:: text
    :class: no-copybutton

    LABEL=writable    /            ext4    discard,errors=remount-ro    0    1
    LABEL=UEFI        /boot/efi    vfat    umask=0077                   0    1

The first three columns should look familiar—these are the labels, mount points, and
file system types we declared for our partitions. The last three columns declare each
partition's active mount options, whether we want to dump the partition's utility
backup, and the file system check order.

Let's create a part that writes this to the ``/etc/fstab/`` directory in the overlay
file system. Add the following ``fstab`` part:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :lines: 69-76

Here, we used the ``overlay-script`` key to write the table to the overlay file system,
which is referenced through the ``$CRAFT_OVERLAY`` environment variable. Keep in mind
that this environment variable is only available in parts that include, or depend on
another part that includes, overlay keys.

The partitions will now be mounted automatically every time the system boots.


Set the default user
--------------------

To interact with the system after we boot the image, we'll need to set the default user
and password.

For the purposes of this tutorial, we'll set up a ``login`` part that runs the
``chpasswd`` command in the overlay file system. This should *not* be done in images
built for production environments. In such cases, you should use a secure method that
fits your image's application.

Add the following ``login`` part:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :start-at: login:
    :end-at: echo "root:password" | chpasswd --root "${CRAFT_OVERLAY}"

When we run our image later, this will allow us to log in with the username ``root`` and
the password ``password``.

Our project file now contains everything we need to pack a complete, bootable image.
Save and close the ``imagecraft.yaml`` file.


Pack the image
--------------

To isolate the image build from your machine, we'll pack the image in a Multipass VM.
Once you're ready, open a new terminal in the ``ubuntu-minimal/`` project directory and
run:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: snap set imagecraft provider=multipass
    :end-at: imagecraft pack

The packing process takes around ten minutes. When your terminal shows the following
line, the build is complete:

.. terminal::
    :output-only:

    Packed disk.img

Congratulations on building your first image! Before you start celebrating, let's run
the image to make sure everything is working as expected.


Run and test the image
----------------------

We'll run our image with QEMU, a common choice for full-system emulation. In your
terminal, install it by running:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: apt install qemu-system-x86
    :end-at: apt install qemu-system-x86

We'll also need UEFI firmware. One of the most popular choices for QEMU is OVMF. Install
it with:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: apt install ovmf
    :end-at: apt install ovmf

Before we run our image, let's copy the UEFI variables into a temporary directory so we
don't compromise the originals:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/OVMF_VARS_4M.fd
    :end-at: cp /usr/share/OVMF/OVMF_VARS_4M.fd /tmp/OVMF_VARS_4M.fd

You'll need to repeat this step if you reboot your machine between runs.

With no further ado, let's run the image with QEMU:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: qemu-system-x86_64 \
    :end-at: -drive file=disk.img,format=raw,index=0,media=disk

This will open QEMU in a separate window. After about a minute, it'll display the
following login prompt:

.. terminal::
    :output-only:

    imagecraft-ubuntu-minimal-amd64-49807517 login:

As you may recall from the ``login`` part, the default username is ``root`` and the password
is ``password``. Enter these into the QEMU shell now.

By booting and logging in to the image, we've verified the presence of its essential
packages. To show that the non-essential packages are in place, let's run the ``sl``
command in the QEMU shell.

.. terminal::
    :output-only:

          ====        ________                ___________
      _D _|  |_______/        \__I_I_____===__|_________|
       |(_)---  |   H\________/ |   |        =|___ ___|       _________________
       /     |  |   H  |  |     |   |         ||_| |_||      _|                \\_____A
      |      |  |   H  |__--------------------| [___] |    =|                        |
      | ________|___H__/__|_____/[][]~\_______|       |    -|                        |
      |/ |   |-----------I_____I [][] []  D   |=======|__ __|________________________|_
    __/ =| o |=-~~\  /~~\  /~~\  /~~\ ____Y___________|__ |__________________________|_
     |/-=|___|=    ||    ||    ||    |_____/~\___/           |_D__D__D_|  |_D__D__D_|
      \_/      \O=====O=====O=====O_/      \_/                \_/   \_/    \_/   \_/

Review the project file
-----------------------

Here's the complete project file for the ubuntu-minimal image. Yours should look similar
to it.

.. dropdown:: imagecraft.yaml for ubuntu-minimal

    .. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
        :language: yaml


Conclusion
----------

This marks the end of this image's journey. If you'd like to develop your crafting
skills further, you can customize the ubuntu-minimal image or even build a new one
from scratch.

If you create an image for a new system or architecture, we encourage you to share it
with us on `Matrix <https://matrix.to/#/#starcraft-development:ubuntu.com>`__. We'd love
to see what you come up with.

If you'd like to share any feedback on Imagecraft or this tutorial, please `open an
issue <https://github.com/canonical/imagecraft/issues/new/choose>`__. We appreciate your
input.
