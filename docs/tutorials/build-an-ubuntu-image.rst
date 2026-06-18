.. meta::
    :description: Learn how to build a custom Ubuntu image with Imagecraft.


.. _tutorial-build-an-ubuntu-image:

Build an Ubuntu image
=====================

In this tutorial, we'll build a custom Ubuntu image for AMD64 machines. We'll work
through everything from the initial project setup to the image's first boot.

The tutorial takes about 25 minutes to complete. It doesn't require an intimate
understanding of disk images, but you'll need to be familiar with Linux paradigms and
using the terminal.


What we'll build
----------------

After installing the necessary tools, we'll start building a custom Ubuntu image from
the ground up.

We'll define the image's structure and content step by step. The image will be based on
the suite of packages from Ubuntu 24.04 LTS, with some additional software that caters
it to the tutorial.

We'll end the tutorial by packaging the complete image and running it with QEMU, a
popular machine emulator.

Once you've completed the tutorial, you'll have practical experience with Imagecraft and
a custom image you can add software to or model your next image from.


What you'll need
----------------

For this tutorial, you'll need:

* An AMD64 machine running Ubuntu 24.04 LTS
* Super user privileges on your machine
* 10GiB of available storage


Install prerequisites
---------------------

To begin, let's install the Imagecraft snap. Open a terminal and run:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: snap install imagecraft --beta --classic
    :end-at: snap install imagecraft --beta --classic

Next, let's install Multipass, which will create the build environment when it comes
time to package the image:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: snap install multipass
    :end-at: snap install multipass

We'll run our image with QEMU. Install it with:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: sudo apt install qemu-system-x86
    :end-at: sudo apt install qemu-system-x86

Lastly, we'll need UEFI firmware to pass to QEMU. One of the most popular choices is
OVMF. Install it with:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: sudo apt install ovmf
    :end-at: sudo apt install ovmf


Set up the project
------------------

We'll need a directory to hold the project. Create a directory wherever you like to keep
your software projects:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: mkdir ubuntu-minimal
    :end-at: cd ubuntu-minimal

Images are built and configured through an ``imagecraft.yaml`` file, called the *project
file*. Let's create one in the new project directory with the ``init`` command:

.. literalinclude:: code/build-an-ubuntu-image/task.yaml
    :language: bash
    :dedent: 2
    :start-at: imagecraft init
    :end-at: imagecraft init

Open the generated project file in your preferred text editor. This is where most of the
tutorial will take place.


.. _tutorial-describe-the-image:

Describe the image
------------------

An image's project file starts with details like its name, version, and build
environment. Imagecraft initialized these keys with generic values. Let's update the
``summary`` and ``description`` keys to better reflect the new project. Replace the
first six keys with:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :start-at: name: ubuntu-minimal
    :end-at: and it's booted with GRUB.

The ``base`` key defines the files that make up the foundation of the image. We're
starting with an empty directory, known as the *bare* base, and building it up from
scratch.

The ``build-base`` key defines the operating system that's used to assemble the image.
It does *not* affect the image's contents. It's best to build with the latest Ubuntu LTS
release in most cases, so we left this unchanged.

The ``summary`` and ``description`` keys tell consumers of the image a little more
about it. The summary is a one-line description, limited at 79 characters, while the
description is more open-ended and can span multiple lines. These were both placeholders
in the template project file, so we made them meaningful for this project.


.. _tutorial-define-the-partitions:

Define the partitions
---------------------

Now that we've described the image and declared its build details, we need to define its
partitions. To do so, we'll customize the ``volumes`` key.

The ``volumes`` key contains a single entry, named ``disk``. The ``schema`` key tells us
that ``disk`` is partitioned with GPT, which is the recommended schema for most modern
installations. Imagecraft also supports Master Boot Record (MBR) and hybrid MBR/GPT
partitioning schemas. We'll define individual partitions with entries in the entry's
``structure`` key.

The image will have two partitions: a root file system and an EFI system partition. Each
will need their own entry in the ``structure`` key. The first was defined for us
automatically. Before we go over it, let's define the EFI system partition the image
will boot from. Add the following highlighted lines after the ``rootfs`` partition:

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
systems. The identifiers themselves come from the UEFI specification---don't worry about
memorizing them.

We set the ``filesystem`` key to ``vfat`` for its compatibility with EFI system
partitions. Since the ``rootfs`` partition will be for general usage, it uses the ext4
filesystem instead.

In both partitions, the ``filesystem-label`` key is set to a unique, human-readable
name. This is for the benefit of you and anyone else who might work with the packaged
image later on.


Mount the partitions
--------------------

The image's partitions are ready, but we haven't told Imagecraft where to mount them in
the image's file system. Let's shift our focus to the ``filesystems`` key.

The ``filesystems`` key maps the image's partitions to their mount points. It expects a
single file system, named ``default``, that mounts a partition to the root of the image.
The ``filesystems`` key in the project file already mounts the ``rootfs`` partition to the
image's root, but we'll still need to mount the EFI system partition.

Add the following highlighted lines to the end of the ``filesystems`` key:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :class: no-copybutton
    :start-at: filesystems:
    :end-at: mount: /boot/efi/
    :emphasize-lines: 5, 6

With this entry, we mounted the EFI system partition to the /boot/efi/ directory in the
final image. We'll create this directory shortly.


.. _tutorial-set-up-the-root-file-system:

Set up the root file system
---------------------------

Because we're building the image on the bare base, its file system is currently an empty
directory. Let's start building it up with the ``parts`` key.

*Parts* are the means by which we source packages for and manipulate the files in the
image. They're the primary way we interact with the *overlay file system*, which is
where we'll build up the image.

We'll create the file system with a part that uses the mmdebstrap plugin.

In the ``parts`` key, replace the template part with a new part named ``rootfs``,
defined as follows:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :start-at: parts:
    :end-at: noble

The ``mmdebstrap-suite`` key is specific to the mmdebstrap plugin and specifies the
package suite to bootstrap. To get the packages that are shipped with Ubuntu 24.04 LTS,
we set the suite to ``noble``.

The plugin removes the default sources configuration files, which limit us to the system
packages from the ``noble`` suite's ``main`` component. If we want to install anything
more than essential system packages, we'll need to add a new sources configuration file.
We also still need to create the /boot/efi/ directory we mounted the ``efi`` partition
to.

Add the following ``override-build`` key to the part:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :class: no-copybutton
    :lines: 39-51
    :emphasize-lines: 4-13

The ``override-build`` key replaces the plugin's default behavior. Since we want to
extend the part's build instead of overriding it, we started the script with ``craftctl
default``, which runs the plugin's default commands.

Now, when we install packages into the image, we'll be able to access the other
components in the ``noble`` suite.

At this point, the file system only exists in the ``rootfs`` part. To get it into the
final image, we'll need to copy it into the overlay file system. We can do so with the
``organize`` key and the ``(overlay)/`` prefix. Add the following highlighted lines to
the ``rootfs`` key:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :class: no-copybutton
    :start-at: rootfs:
    :end-at: '*': (overlay)/
    :emphasize-lines: 14, 15

This copies the result of the part's build step to the root of the overlay file system,
thereby securing its place in the final image.


.. _tutorial-add-essential-packages:

Add essential packages
----------------------

We'll need some additional packages for the image to be bootable. Let's define a new
part to source them. In this case, we don't need any special behavior, so we'll set the
``plugin`` key to ``nil``. Add a new part named ``packages``, defined as follows:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :lines: 55-64

With the exception of ``sl``, these packages add system essentials such as the kernel,
core utilities, and boot loader. You won't need to worry about ``sl`` until we run the
image later on.


Create the file system table
----------------------------

If we tried to boot the image now, its partitions wouldn't be mounted. This is because
Imagecraft requires that we create our file system table manually. The content of this
table is similar to what we declared in the ``filesystems`` key, with some additional
configuration.

With how we set up the partitions and mount points, the table will read:

.. code-block:: text
    :class: no-copybutton

    LABEL=root        /            ext4    discard,errors=remount-ro    0    1
    LABEL=uefi        /boot/efi/   vfat    umask=0077                   0    1

The first three columns should look familiar—these are the labels, mount points, and
file system types we declared for our partitions. The last three columns declare each
partition's active mount options, whether we want to dump the partition's utility
backup, and the file system check order.

Let's create a part that writes this to the ``/etc/fstab/`` directory in the overlay
file system. Add a new part named ``fstab``, defined as follows:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :lines: 65-72

Here, we used the ``overlay-script`` key to write the table to the overlay file system,
which is referenced through the ``$CRAFT_OVERLAY`` environment variable. Keep in mind
that this environment variable is only available in parts that include, or depend on
another part that includes, overlay keys.

The partitions will now be mounted automatically when the system boots.


Set the default user
--------------------

To interact with the system after we boot the image, we'll need to set the default user
and password.

For the purposes of this tutorial, we'll set up a ``login`` part that runs the
``chpasswd`` command in the overlay file system. This should *not* be done in images
built for production environments.

Add a new part named ``login``, defined as follows:

.. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
    :language: yaml
    :start-at: login:
    :end-at: echo "root:password" | chpasswd --root "${CRAFT_OVERLAY}"

When we run our image later, we'll log in with the username ``root`` and the password
``password``.

Our project file now contains everything we need to pack a complete, bootable image.
Save and close the ``imagecraft.yaml`` file.


.. _tutorial-pack-the-image:

Pack the image
--------------

To isolate the image build from your machine, we'll pack the image in a Multipass VM.
Open a new terminal in the ``ubuntu-minimal/`` project directory and run:

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


.. _tutorial-run-and-test-the-image:

Run and test the image
----------------------

Before we run our image with QEMU, let's copy the UEFI variables from OVMF into a
temporary directory so we don't compromise the originals:

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
packages. To ensure the packages from the extra components of the ``noble`` suite are in
place, let's run the ``sl`` command in the QEMU shell.

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

Here's the complete project file for the image. Yours should look similar to it.

.. dropdown:: imagecraft.yaml for ubuntu-minimal

    .. literalinclude:: code/build-an-ubuntu-image/imagecraft.yaml
        :language: yaml


Conclusion
----------

This marks the end of this image's journey. If you'd like to develop your crafting
skills further, you can customize the image or even build a new one from scratch.

If you create an image for a new system or architecture, we encourage you to share it
with us on `Matrix <https://matrix.to/#/#starcraft-development:ubuntu.com>`__. We'd love
to see what you come up with.

If you'd like to share any feedback on Imagecraft or this tutorial, please `open an
issue <https://github.com/canonical/imagecraft/issues/new/choose>`__. We appreciate your
input.
