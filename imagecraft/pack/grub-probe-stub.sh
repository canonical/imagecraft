#!/bin/bash
# GRUB probe stub for containerized environments
# Returns device information based on the actual mounted filesystems

# First argument is the target, rest are additional options
TARGET="$1"
shift

# Extract the path argument (last argument)
PATH_ARG="$*"

# Try to read device UUID symlinks
get_uuid_from_device() {
    local device_path="$1"
    local uuid_link="/dev/disk/by-uuid/$device_path"

    # Check if the symlink exists
    if [ -L "$uuid_link" ]; then
        readlink -f "$uuid_link" 2>/dev/null || echo ""
    fi
}

# Try to read filesystem label
get_label_from_device() {
    local device_path="$1"
    local label_link="/dev/disk/by-label/$device_path"

    if [ -L "$label_link" ]; then
        readlink -f "$label_link" 2>/dev/null || echo ""
    fi
}

case "$TARGET" in
    --target=fs_uuid)
        # Try to get real UUID from /dev/disk/by-uuid/ symlinks
        # The path argument is the mountpoint
        if [ -n "$PATH_ARG" ]; then
            # Try to find the actual device by checking common mountpoints
            for mountpoint in /boot /boot/efi /; do
                if [ "$PATH_ARG" = "$mountpoint" ] || [[ "$PATH_ARG" == *"$mountpoint"* ]]; then
                    # Try to find a UUID symlink
                    for uuid_dir in /dev/disk/by-uuid/*; do
                        if [ -L "$uuid_dir" ]; then
                            uuid_link=$(readlink -f "$uuid_dir")
                            # Check if this device is mounted at our mountpoint
                            if grep -qs "$uuid_link" /proc/mounts 2>/dev/null; then
                                basename "$uuid_dir"
                                exit 0
                            fi
                        fi
                    done
                    break
                fi
            done
        fi
        # Fallback: no UUID found
        echo ""
        ;;
    --target=device)
        # Return the device path for the mountpoint
        # Try to find the actual device
        if [ -n "$PATH_ARG" ]; then
            for mountpoint in /boot /boot/efi /; do
                if [ "$PATH_ARG" = "$mountpoint" ] || [[ "$PATH_ARG" == *"$mountpoint"* ]]; then
                    # Try to find the device
                    for dev_path in /dev/sda* /dev/vda* /dev/loop* 2>/dev/null; do
                        if [ -b "$dev_path" ]; then
                            # Check if this device is mounted at our mountpoint
                            if grep -qs "$dev_path" /proc/mounts 2>/dev/null; then
                                echo "$dev_path"
                                exit 0
                            fi
                        fi
                    done
                fi
            done
        fi
        # Fallback: return empty
        echo ""
        ;;
    --target=disk)
        # Return the actual disk device path from environment
        echo "${DISK_IMAGE_PATH:-}"
        ;;
    --target=drive)
        # Return GRUB drive name
        echo "hd0"
        ;;
    --target=fs)
        # Return filesystem type based on device
        if [ -n "$PATH_ARG" ]; then
            for mountpoint in /boot /boot/efi /; do
                if [ "$PATH_ARG" = "$mountpoint" ] || [[ "$PATH_ARG" == *"$mountpoint"* ]]; then
                    # Check the fstab for this mountpoint
                    if grep -q "$mountpoint" /etc/fstab 2>/dev/null; then
                        fs_type=$(grep "$mountpoint" /etc/fstab | awk '{print $3}')
                        echo "$fs_type"
                        exit 0
                    fi
                fi
            done
        fi
        # Fallback: detect by checking mounted filesystems
        if mountpoint -q /boot; then
            fs_type=$(df -T /boot | tail -1 | awk '{print $2}')
            echo "$fs_type"
            exit 0
        fi
        if mountpoint -q /boot/efi; then
            fs_type=$(df -T /boot/efi | tail -1 | awk '{print $2}')
            echo "$fs_type"
            exit 0
        fi
        if mountpoint -q /; then
            fs_type=$(df -T / | tail -1 | awk '{print $2}')
            echo "$fs_type"
            exit 0
        fi
        echo ""
        ;;
    --target=fs_label)
        # Return filesystem label
        if [ -n "$PATH_ARG" ]; then
            for mountpoint in /boot /boot/efi /; do
                if [ "$PATH_ARG" = "$mountpoint" ] || [[ "$PATH_ARG" == *"$mountpoint"* ]]; then
                    # Try /dev/disk/by-label/
                    label=$(get_label_from_device "$(basename "$mountpoint")" 2>/dev/null)
                    if [ -n "$label" ]; then
                        echo "$label"
                        exit 0
                    fi
                    # Fallback: check /proc/mounts
                    mount_line=$(grep "$mountpoint" /proc/mounts 2>/dev/null | head -1)
                    if [ -n "$mount_line" ]; then
                        label=$(echo "$mount_line" | awk '{print $2}')
                        echo "$label"
                        exit 0
                    fi
                fi
            done
        fi
        echo ""
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