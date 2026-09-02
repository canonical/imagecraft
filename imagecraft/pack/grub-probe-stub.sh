#!/bin/bash
# GRUB probe stub for containerized environments
# Returns fake but consistent device information for GRUB tools

case "$*" in
    --target=fs_uuid)
        # Return a consistent UUID for the root filesystem
        echo "1234-5678-90AB-CDEF"
        ;;
    --target=device)
        # Return the device path for the mountpoint
        if [[ "$*" == *"boot"* ]]; then
            echo "/dev/sda1"
        elif [[ "$*" == *"efi"* ]]; then
            echo "/dev/sda2"
        else
            echo "/dev/sda2"
        fi
        ;;
    --target=disk)
        # Return the disk device
        echo "/dev/sda"
        ;;
    --target=drive)
        # Return GRUB drive name
        echo "hd0"
        ;;
    --target=fs)
        # Return filesystem type
        if [[ "$*" == *"vfat"* ]] || [[ "$*" == *"fat"* ]]; then
            echo "fat"
        else
            echo "ext2"
        fi
        ;;
    --target=fs_label)
        # Return filesystem label
        if [[ "$*" == *"efi"* ]]; then
            echo "EFI"
        else
            echo "writable"
        fi
        ;;
    --target=partmap)
        # Return partition map type
        echo "gpt"
        ;;
    --target=abstraction)
        # Return abstraction modules
        echo "lvm"
        ;;
    *)
        echo "unknown" >&2
        exit 1
        ;;
esac