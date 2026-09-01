#! /bin/bash
# grub-probe replacement used inside imagecraft's chroot during update-grub.
# The real grub-probe resolves /proc/self/mounts to find the canonical
# block device of a mountpoint, then answers questions from it. Inside
# our FUSE chroot no block device exists and probe exits with "cannot
# find canonical path of <mountpoint>". update-grub's dispatcher
# scripts only need the answers below — values computed beforehand
# and passed as environment.
device="" target=""
while [ $# -gt 0 ]; do
    case "$1" in
        --version)   ;;
        --device) shift; device="$1";;
        --device=*) device="${1#--device=}";;
        --target) shift; target="$1";;
        --target=*) target="${1#--target=}";;
        --help) echo >&2 "imagecraft grub-probe stub"; exit 0;;
    esac 2>/dev/null
    shift
done
case "$device" in
    "" | /) uuid="$IMAGECRAFT_ROOT_UUID";;
    /boot | /boot/efi | /boot/efi/) uuid="$IMAGECRAFT_BOOT_UUID";;
    *) uuid="" ;;
esac
case "$target" in
    fs_uuid) echo "$uuid";;
    fs) echo "ext2";;
    partmap) echo "gpt";;
    abstraction) ;;
    hints_string) ;;
    compatibility_hint) ;;
    cryptodisk_uuid) ;;
    device) ;;
    *) ;;
esac
exit 0
