.. meta::
    :description: Configure an amd64 Imagecraft project to use a BIOS boot partition on a GPT partition table for legacy BIOS boot.


.. _how-to-enable-bios-boot:

Enable legacy BIOS boot on a GPT schema volume
==============================================

You can configure an ``amd64`` Imagecraft project to boot from a GPT partition table
using legacy BIOS firmware and GRUB. This works both for BIOS-only images and as a BIOS
fallback alongside UEFI.


Add a BIOS boot partition
-------------------------

Add a ``2M`` raw partition with the GPT BIOS boot GUID
(``21686148-6449-6E6F-744E-656564454649``) to the ``structure`` key under
``volumes``:

.. code-block:: yaml
    :caption: imagecraft.yaml
    :emphasize-lines: 5-7

    volumes:
      pc:
        schema: gpt
        structure:
          - name: biosboot
            type: 21686148-6449-6E6F-744E-656564454649
            size: 2M
          - name: rootfs
            type: 0FC63DAF-8483-4772-8E79-3D69D8477DE4
            filesystem: ext4
            filesystem-label: writable
            role: system-data
            size: 3G

The root partition (with the ``system-data`` role) must use an ``ext3`` or ``ext4`` file
system. If you omit an EFI System Partition from the ``structure`` key, Imagecraft
installs only the BIOS bootloader.


Add bootloader packages
-----------------------

Include grub-pc-bin (alongside grub2-common and a kernel) using the
``overlay-packages`` key:

.. code-block:: yaml
    :caption: imagecraft.yaml

    parts:
      bootloader:
        plugin: nil
        after: [rootfs]
        overlay-packages:
          - grub2-common
          - grub-pc-bin
          - linux-image-generic

Keep shim-signed and grub-efi-amd64 if your volume also includes an EFI System
Partition.


Pack and verify the image
-------------------------

Run ``imagecraft pack`` in your project directory to build the disk image:

.. code-block:: bash

    imagecraft pack

To verify that the image boots in legacy BIOS mode, run it with QEMU using its default
SeaBIOS firmware. Do not pass UEFI firmware drives:

.. code-block:: bash

    qemu-system-x86_64 \
      -accel kvm -accel tcg,thread=multi \
      -nographic \
      -m 1G \
      -drive file=pc.img,format=raw,index=0,if=virtio
