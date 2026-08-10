# TODO: Replicating `grub-install` using `grub-mkimage` & Manual GRUB Deployment (EFI Devices)

This document outlines all technical steps, module dependencies, file operations, and platform-specific logic required to replace high-level `grub-install` invocations in `imagecraft` with `grub-mkimage` and direct file/sector installation for **Ubuntu** image builds on **EFI-capable devices** across supported architectures (`amd64`, `arm64`, `armhf`, and `riscv64`).

---

## 1. Overview & Context

Currently, `imagecraft` invokes `grub-install` inside a chroot environment (see [`imagecraft/pack/grubutil.py`](file:///home/lengau/Work/Code/imagecraft/imagecraft/pack/grubutil.py#L45-L118)).

Replacing `grub-install` with `grub-mkimage` and direct asset deployment tailored for EFI devices offers several advantages:

- Bypasses the need for full chroot mount setups (`/dev`, `/proc`, `/sys`, `/run`).
- Enables cross-architecture bootloader generation directly on the host.
- Provides fine-grained control over embedded modules and configuration stubs.

---

## 2. Shared / Prerequisites Stage: GRUB Asset Deployment

Before generating boot executables or embedding core images, GRUB runtime assets must be placed on the target root/boot filesystem.

- [ ] **Create Directory Structure**
    - Path: `/boot/grub/<target>/`
        - `amd64` $\rightarrow$ `/boot/grub/x86_64-efi/` (or `/boot/grub/i386-pc/` for BIOS fallback)
        - `arm64` $\rightarrow$ `/boot/grub/arm64-efi/`
        - `armhf` $\rightarrow$ `/boot/grub/arm-efi/`
        - `riscv64` $\rightarrow$ `/boot/grub/riscv64-efi/`
    - Path: `/boot/grub/fonts/`
    - Path: `/boot/grub/locale/`

- [ ] **Copy GRUB Modules (`*.mod`)**
    - Source: `/usr/lib/grub/<target>/*.mod`
    - Destination: `/boot/grub/<target>/`
    - Purpose: Dynamic module loading during system boot.

- [ ] **Copy GRUB Metadata & Lookup Lists (`*.lst`)**
    - Source files:
        - `moddep.lst` (Module dependency map)
        - `fs.lst` (Supported filesystems list)
        - `partmap.lst` (Supported partition schemes list)
        - `parttool.lst`, `command.lst`, `terminal.lst`, `crypto.lst`, `video.lst`
    - Destination: `/boot/grub/<target>/`

- [ ] **Copy Fonts & Locales**
    - Copy font file (`unicode.pf2`) from `/usr/share/grub/` to `/boot/grub/fonts/`.
    - Copy translation catalogs (`*.mo`) from `/usr/share/locale/*/LC_MESSAGES/grub.mo` to `/boot/grub/locale/<lang>/`.

---

## 3. Ubuntu UEFI Deployment Tasks (`amd64`, `arm64`, `armhf`, `riscv64`)

In Ubuntu, the vendor boot directory on the EFI System Partition (ESP) is fixed to `/boot/efi/EFI/ubuntu/`.

### 3.1 Unsigned / Standard UEFI (via `grub-mkimage`)

- [ ] **Build Standalone EFI Binary with `grub-mkimage`**
    - **amd64 (`x86_64-efi`)**:
        ```bash
        grub-mkimage \
          -d /usr/lib/grub/x86_64-efi \
          -o /tmp/grubx64.efi \
          -O x86_64-efi \
          -p /boot/grub \
          part_gpt part_msdos fat ext2 btrfs xfs normal search search_fs_uuid search_label search_fs_file boot linux configfile echo loadenv test efi_gop gfxterm font
        ```
    - **arm64 (`arm64-efi`)**:
        ```bash
        grub-mkimage \
          -d /usr/lib/grub/arm64-efi \
          -o /tmp/grubaa64.efi \
          -O arm64-efi \
          -p /boot/grub \
          part_gpt part_msdos fat ext2 btrfs xfs normal search search_fs_uuid search_label search_fs_file boot linux configfile echo loadenv test efi_gop gfxterm font devicetree acpi
        ```
    - **armhf (`arm-efi`)**:
        ```bash
        grub-mkimage \
          -d /usr/lib/grub/arm-efi \
          -o /tmp/grubarm.efi \
          -O arm-efi \
          -p /boot/grub \
          part_gpt part_msdos fat ext2 btrfs xfs normal search search_fs_uuid search_label search_fs_file boot linux configfile echo loadenv test efi_gop gfxterm font devicetree
        ```
    - **riscv64 (`riscv64-efi`)**:
        ```bash
        grub-mkimage \
          -d /usr/lib/grub/riscv64-efi \
          -o /tmp/grubriscv64.efi \
          -O riscv64-efi \
          -p /boot/grub \
          part_gpt part_msdos fat ext2 btrfs xfs normal search search_fs_uuid search_label search_fs_file boot linux configfile echo loadenv test efi_gop gfxterm font devicetree
        ```

- [ ] **Deploy EFI Binary to EFI System Partition (ESP)**
    - **amd64 Target Paths**:
        - Vendor path: `/boot/efi/EFI/ubuntu/grubx64.efi`
        - Fallback / Removable path: `/boot/efi/EFI/BOOT/BOOTX64.EFI`
    - **arm64 Target Paths**:
        - Vendor path: `/boot/efi/EFI/ubuntu/grubaa64.efi`
        - Fallback / Removable path: `/boot/efi/EFI/BOOT/BOOTAA64.EFI`
    - **armhf Target Paths**:
        - Vendor path: `/boot/efi/EFI/ubuntu/grubarm.efi`
        - Fallback / Removable path: `/boot/efi/EFI/BOOT/BOOTARM.EFI`
    - **riscv64 Target Paths**:
        - Vendor path: `/boot/efi/EFI/ubuntu/grubriscv64.efi`
        - Fallback / Removable path: `/boot/efi/EFI/BOOT/BOOTRISCV64.EFI`

---

### 3.2 Secure Boot UEFI (Pre-Signed Canonical Shim + Signed GRUB)

- [ ] **Copy Pre-Signed Binaries from Ubuntu Packages**
    - Do **not** use `grub-mkimage` (custom-built binaries will fail Secure Boot signature verification).
    - **amd64 Signed Binaries** (from `shim-signed` & `grub-efi-amd64-signed`):
        - Source: `/usr/lib/shim/shimx64.efi.signed` $\rightarrow$ `/boot/efi/EFI/ubuntu/shimx64.efi` (and `/boot/efi/EFI/BOOT/BOOTX64.EFI`)
        - Source: `/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed` $\rightarrow$ `/boot/efi/EFI/ubuntu/grubx64.efi`
        - Support files: `/usr/lib/shim/mmx64.efi` & `/usr/lib/shim/fbx64.efi` $\rightarrow$ `/boot/efi/EFI/ubuntu/`
    - **arm64 Signed Binaries** (from `shim-signed` & `grub-efi-arm64-signed`):
        - Source: `/usr/lib/shim/shimaa64.efi.signed` $\rightarrow$ `/boot/efi/EFI/ubuntu/shimaa64.efi` (and `/boot/efi/EFI/BOOT/BOOTAA64.EFI`)
        - Source: `/usr/lib/grub/arm64-efi-signed/grubaa64.efi.signed` $\rightarrow$ `/boot/efi/EFI/ubuntu/grubaa64.efi`
        - Support files: `/usr/lib/shim/mmaa64.efi` & `/usr/lib/shim/fbaa64.efi` $\rightarrow$ `/boot/efi/EFI/ubuntu/`
    - **armhf and riscv64**:
        - _N/A_: Secure Boot is **not supported** for `armhf` or `riscv64` in Ubuntu. Builds always use unsigned binaries generated via `grub-mkimage`.

- [ ] **Generate Ubuntu ESP Early Load Stub (`/boot/efi/EFI/ubuntu/grub.cfg`)**
    - Place Ubuntu's standard 3-line loader config on the ESP alongside the GRUB binary:
        ```grub
        search.fs_uuid <BOOT_OR_ROOT_PARTITION_UUID> root hd0,gpt2
        set prefix=($root)'/boot/grub'
        configfile $prefix/grub.cfg
        ```

---

## 4. Legacy BIOS / MBR (`i386-pc`) Deployment Tasks (amd64 Legacy Devices)

- [ ] **Build `core.img` via `grub-mkimage`**
    - Command template:
        ```bash
        grub-mkimage \
          -d /usr/lib/grub/i386-pc \
          -o /boot/grub/i386-pc/core.img \
          -O i386-pc \
          -p /boot/grub \
          biosdisk part_msdos part_gpt ext2 fat normal search search_fs_uuid boot linux configfile
        ```

- [ ] **Copy Stage 1 Boot Sector (`boot.img`)**
    - Source: `/usr/lib/grub/i386-pc/boot.img`
    - Destination: `/boot/grub/i386-pc/boot.img`

- [ ] **Install Boot Sector & Sector-Patch `core.img` using `grub-bios-setup`**
    - Execute `grub-bios-setup` directly against the loop device without chroot:
        ```bash
        grub-bios-setup \
          --directory=/mountpoint/boot/grub/i386-pc \
          --device-map=/tmp/device.map \
          /dev/loopX
        ```
    - _Note_: Ensure the loop device is attached with partition scanning enabled (`losetup -P`).

---

## 5. Configuration & Cleanup Tasks

- [ ] **Generate Main Config (`/boot/grub/grub.cfg`)**
    - Run `update-grub` / `grub-mkconfig` or generate Ubuntu's standard `grub.cfg` template with kernel command-line arguments and initrd options.

- [ ] **Refactor `imagecraft/pack/grubutil.py`**
    - Remove chroot dependency for GRUB installation on EFI targets.
    - Implement architecture dispatcher routing `amd64` (`x86_64-efi`), `arm64` (`arm64-efi`), `armhf` (`arm-efi`), and `riscv64` (`riscv64-efi`) to their respective EFI bootloader binary generation and asset deployment strategies.
