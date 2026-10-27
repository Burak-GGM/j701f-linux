# First Installation Plan: Stock Android SM-J701F to J701F Linux Distribution

**Status:** Read-only design and procedure specification (prepared 2026-10-27).  
**Target handset:** Samsung Galaxy J7 Neo / J7 Core / J7 Nxt — **SM-J701F (`samsung,j7velte`)** on Exynos 7870 (`S5E7870`) only.

> **Important status note:** An automated public stock-Android-to-Linux installer does **not** exist yet. The routes below describe the technical design, image contracts, and manual/host-prepared sequence required to transition a stock Android SM-J701F handset to this distribution. Neither route should be presented as a turnkey end-user installer until full hardware validation on a clean handset is completed and documented.

---

## 1. Scope and Safety Boundaries

This document specifies the guarded design for taking a stock Android **SM-J701F (`j7velte`)** handset to the project's mainline Linux distribution (**Linux 7.1.13 + U-Boot v2026.01 shim in `BOOT`**, **LVGL graphical RAM recovery in `RECOVERY`**, and **Alpine Linux 3.24 + KDE Plasma Mobile on `USERDATA`**).

### Why the `USERDATA` installers alone are not enough on stock Android

The project's `USERDATA` release installers (`scripts/install-release.py`, `scripts/install-release-on-recovery.sh`, and the TWRP/OrangeFox `recovery/installer/` ZIP) intentionally write **`USERDATA` (`mmcblk0p24`) only**. Before touching `USERDATA`, both `scripts/install-release-on-recovery.sh` and `recovery/installer/installer.sh` verify that `BOOT` (`mmcblk0p10`) already contains the string `bootcmd=j701f_ramboot`.

On a stock Android handset:
1. `BOOT` contains Samsung's 3.18 Android kernel/ramdisk (`bootcmd=j701f_ramboot` is absent), so the `USERDATA` installers immediately refuse to run.
2. Even if `USERDATA` were written first, stock Android `BOOT` cannot mount or `switch_root` into the project's unencrypted ext4 `USERDATA` root (`UUID=4ce26b55-8a59-4fb7-aad4-919a5c2cefeb`).
3. Therefore, a first-time transition from stock Android requires a **three-partition transition** restricted strictly to `RECOVERY`, `BOOT`, and `USERDATA`.

### Immutable safety rules (never violated)

- **Partitions permitted to be written:**
  - `RECOVERY` (`/dev/mmcblk0p11`, 77,824 sectors / 39,845,888 bytes)
  - `BOOT` (`/dev/mmcblk0p10`, 65,536 sectors / 33,554,432 bytes)
  - `USERDATA` (`/dev/mmcblk0p24`, 23,314,432 sectors / 11,936,989,184 bytes)
- **Partitions never written or repartitioned:** `PIT`, `BL` / `S-BOOT`, `EFS`, `CPEFS`, `PARAM`, `UP_PARAM`, `BOTA0`/`BOTA1`, `CM` / TrustZone, `RADIO` / `CP` (modem), `SYSTEM`, `CACHE`, `HIDDEN`, `ODM`, and `RPMB`.
- **Never read:** `EFS` / `CPEFS` (IMEI, factory MAC addresses, calibration secrets). Wi-Fi and Bluetooth on mainline use fixed locally administered MAC addresses (`02:70:1F:57:4C:01` and `02:70:1F:57:4C:02`) from the device tree.
- **No Odin erase or repartition flags:** Never pass `--nand-erase`, `--re-partition`, `-p` (PIT), `-b` (BL), `-c` (CP), or `-s` (CSC) to `odin4`. Only `-a <archive.tar>` and `-d </dev/bus/usb/BBB/DDD>` are used.
- **Data destruction warning:** Installing to `USERDATA` permanently destroys all Android user data, apps, accounts, and internal storage (`/sdcard` / `/data/media`).
- **Realistic backup and rollback prerequisite for `BOOT` and `RECOVERY`:**
  - Because an unrooted stock Android handset does not allow `dd` reading `/dev/mmcblk0p10` (`BOOT`) or `/dev/mmcblk0p11` (`RECOVERY`) before the first custom `RECOVERY` flash, **overwriting `RECOVERY` via Odin4 in Download Mode destroys the live contents of the `RECOVERY` slot before an on-device read-back of `RECOVERY` can be taken**.
  - Therefore, **before** flashing `RECOVERY` on a stock handset, the operator must have a verified external rollback image for `RECOVERY` on the host computer: either the matching stock Samsung `SM-J701F` firmware `AP` archive's `recovery.img` (matching the handset's installed `androidboot.bootloader` build, e.g. `J701FXXUACUH1`), or a known-working fallback recovery archive such as `build/OrangeFox-restore.tar` (verified by `python3 tools/recovery.py verify-tar build/OrangeFox-restore.tar --restore`, SHA-256 `5bbcb385a5b007a037713b169e69255534fbfb3527fa9ced63c61fe08b1eb68e`).
  - Once custom `RECOVERY` is booted in RAM (before `BOOT` or `USERDATA` is touched), the live stock `BOOT` partition (`/dev/mmcblk0p10`, 33,554,432 bytes) **can and must** be backed up on-device to the external SD card (`dd if=/dev/mmcblk0p10 ...`) and hash-verified before `BOOT` is modified.

---

## 2. Model, Hardware, and Partition Verification Contract

Every stage of the first-install flow must enforce the exact hardware and partition geometry of the SM-J701F before writing a single byte.

| Check | Expected Value | Where Checked |
| --- | --- | --- |
| Bootloader model prefix | `androidboot.bootloader=J701F*` (e.g. `J701FXXUACUH1`) | `/proc/cmdline` in recovery / Download Mode visual check |
| Board / product name | `j7velte` (`samsung,j7velte`, `samsung,exynos7870`) | U-Boot `board` env, `/proc/device-tree/compatible`, recovery `ro.product.device` |
| Hardware revision | `androidboot.revision=3` (`hw_rev = 3`) | U-Boot `exynos_board_info` (`match_min_rev=3`, `match_max_rev=3`) |
| SoC & DRAM banks | Exynos 7870; Bank 0: `0x40000000` (`0x3e400000` bytes), Bank 1: `0x80000000` (`0x40000000` bytes) | U-Boot `do_j701f_ramboot()` and `tools/build-j701f-dtb.py` |
| Internal eMMC device | `/dev/mmcblk0`, `device/type = MMC`, `removable = 0` | `/sys/class/block/mmcblk0/` |
| `BOOT` partition | `/dev/mmcblk0p10` (`PARTNAME=BOOT`, `259:2` / `103:2`), **65,536 sectors** (**33,554,432 bytes** / 32 MiB) | `/sys/class/block/mmcblk0p10/{uevent,size}`, `/dev/block/platform/13540000.dwmmc0/by-name/BOOT` |
| `RECOVERY` partition | `/dev/mmcblk0p11` (`PARTNAME=RECOVERY`, `259:3` / `103:3`), **77,824 sectors** (**39,845,888 bytes** / 38 MiB) | `/sys/class/block/mmcblk0p11/{uevent,size}`, `/dev/block/platform/13540000.dwmmc0/by-name/RECOVERY` |
| `USERDATA` partition | `/dev/mmcblk0p24` (`PARTNAME=USERDATA`), **23,314,432 sectors** (**11,936,989,184 bytes** / ~11.12 GiB) | `/sys/class/block/mmcblk0p24/{uevent,size}`, `blockdev --getsize64` |
| External SD card (when used) | `/dev/mmcblk[12]`, `/sys/class/block/mmcblkN/device/type = SD` | `recovery/scripts/storage.sh`, `scripts/install-release-on-recovery.sh` |

> **Note on eMMC CID:** Scripts generated for the development handset (`tools/prepare-boot-update.py`, `tools/prepare-mainline-recovery-trial.py`) pin `mmc_cid_sha256 = 5f11bab3df157120ec79e64c3f41227e3ea91f2273fa1ba277d4cf7e7468097d` (unique to that physical eMMC chip). On any other SM-J701F handset, `recovery/scripts/flash-boot.sh`, `scripts/install-release-on-recovery.sh`, and `recovery/installer/installer.sh` rely on the model/partition/geometry checks above rather than the single-handset CID hash.

---

## 3. Separation of Generic vs. Handset-Private Firmware and Kernel-Matched Modules

A clean first installation has two distinct classes of optional inputs that must not be conflated:

### 3.1 Handset-Private Proprietary Firmware (Redistribution Boundary)

 proprietary firmware blobs from a phone are **not** tracked in git and must **not** be uploaded in public release artifacts (`release.json` sets `"redistributable": false` whenever they are included):

1. **In the `BOOT` / `RECOVERY` initramfs (`tools/build-mainline-image.sh`):**
   - `tools/build-mainline-image.sh` copies `brcmfmac43430-sdio.bin`, `brcmfmac43430-sdio.clm_blob`, `brcmfmac43430-sdio.txt`, and `BCM43430A1.hcd` from `build/kernel/j701f-wifi/firmware/` into `/lib/firmware/brcm/` inside the initramfs so the built-in `brcmfmac` and `hci_bcm` drivers can initialize during early boot and in the graphical recovery.
   - A user building `BOOT` or `RECOVERY` from a fresh git clone must first extract those four files from their own SM-J701F handset (or stock Samsung SM-J701F firmware package) into `build/kernel/j701f-wifi/firmware/`.
2. **In the `USERDATA` rootfs (`tools/build-release.py`):**
   - **Public / redistributable build** (omitting `--wifi-firmware-dir` and `--mfc-firmware-file`): installs Alpine's generic `linux-firmware-brcm` and `linux-firmware-s5p-mfc` packages (`"redistributable": true`). As noted in `wiki/reference/release-build.md`, generic Alpine firmware uses compressed files and a generic NVRAM profile, so Wi-Fi/video-decoder behavior on a fresh generic rootfs is not guaranteed without the board files.
   - **Personal local build** (passing `--wifi-firmware-dir PATH` and `--mfc-firmware-file FILE`): installs the handset's exact uncompressed `brcmfmac43430-sdio.{bin,clm_blob,txt}`, optional `BCM43430A1.hcd`, and `s5p-mfc-v10.fw` (`mfc_fw.bin`). Such an image is marked `"redistributable": false` and must stay on the owner's machine/phone.

### 3.2 Exact Kernel-Matched Out-of-Tree Modules (`--modules-dir`)

- The normal mainline `BOOT` image (`cam5`, Linux 7.1.13, `Image` SHA-256 `2eabbca3de877c1d2daa3a21fcbcffab68723c5995d2e9fb6e6cd08b663c078e`, GNU build ID `1950147e…`) has core storage (eMMC, SD), USB gadget, touchscreen, GPIO keys, simpledrm framebuffer, Panfrost GPU, and Wi-Fi built into the kernel/initramfs.
- Additional hardware features are provided by kernel modules loaded from `/home/burak-alpine/j701f/modules/` on `USERDATA`:
  - Audio (`snd-soc-*`, `s2mpu05-codec`, etc.),
  - Video codec (`s5p-mfc`),
  - Charger / ADC / power-domain helpers (`s2mu005_charger`, `j701f_adc`, `j701f_cam_pd`),
  - Camera (`j701f_camera`, `udmabuf`),
  - Native DECON + DSIM + EA8061S panel display switch (`ea8061s` + runtime overlay). `tools/build-release.py` writes `/etc/j701f-display-native` = `always` only when `--modules-dir` supplies `display/*.ko` together with `display/kernel-notes.sha256` that pins the kernel they were built for; otherwise the release stays on `simpledrm`. `system/display-native/switch.sh` also compares the running kernel with that identity at every boot and falls back harmlessly if it differs.
- **Strict matching rule:** Every `.ko` passed via `--modules-dir PATH` to `tools/build-release.py` **must** be compiled against the exact Linux kernel tree and `.config` that produced the `Image` inside `BOOT`. Note that `tools/build-release.py` automatically strips any `mfc/mfc_fw.bin` found inside `--modules-dir` so phone-extracted firmware is never slipped in via `--modules-dir`.
- **USB MTP and the SD card:** the release mounts the microSD card at `/media/sdcard` (`/etc/fstab`, mounted through `localmount`, which `j701f-display` requires) and starts the MTP layer from `/etc/local.d/j701f-usb-mtp.start`. The MTP server itself, uMTP-Responder (`/usr/local/bin/umtprd`, GPL-3.0-or-later), is not packaged by Alpine; it is included only when `--umtprd-binary FILE` is given. Without it the starter exits quietly and the phone offers no MTP storage.
- **Behavior without `--modules-dir`:** If `--modules-dir` is omitted, the system still boots into Plasma Mobile on the bootloader framebuffer (`simpledrm`) with Panfrost GPU acceleration, touch, USB, and storage, but sound, hardware video decoding, camera, battery thermistor ADC, and native panel switching will be unavailable until matching modules are installed.

---

## 4. BOOT and RECOVERY Image Sources and Architecture

Both the mainline `BOOT` image and the project's graphical `RECOVERY` image share the same Samsung `ANDROID!` container structure, U-Boot shim, and Linux 7.1.13 kernel, differing only in their initramfs mode and top device tree.

### 4.1 Container and Header Baseline (`tools/recovery.py`, `tools/package-embedded-mainline-diagnostic.py`)

Samsung's untouched `S-BOOT` bootloader requires a legacy Android boot image header (`ANDROID!` magic at byte 0, `page_size = 2048`, and legacy `dt_size` at byte 40) plus a valid `DTBH` table and a 16-byte `SEANDROIDENFORCE` trailer.

The project constructs both `BOOT` and `RECOVERY` containers from the verified baseline header template (`original/OrangeFox-recovery.img`, SHA-256 `5bbcb385a5b007a037713b169e69255534fbfb3527fa9ced63c61fe08b1eb68e`, which matches the measured stock `BOOT` load addresses):
- **`kernel` slot (offset 2048):** Replaced with `u-boot.bin` (patched U-Boot v2026.01 with the embedded FIT payload).
- **`ramdisk` slot:** **Empty (`0` bytes)**. S-BOOT requires a valid header layout, while the actual initramfs is carried inside the U-Boot embedded FIT image.
- **`second` slot:** Empty (`0` bytes).
- **`dt` slot (`dt_size` at offset 40):** Replaced with `build/kernel/sboot-stub/stub-dtbh.img` (8,192 bytes, SHA-256 `4a58e660fec63dfce5abca17dffe3166b6ca63ccf6b6eb69849d7969c870bd41`), built by `tools/prepare-sboot-stub.py` from `extracted/dtb` (SHA-256 `afbf297a9ea000c596d68471852b16678251b61e21eb088040510a11714e8191`). It preserves the three DTBH v2 selection keys `(chip=7870, platform=0x50a6, subtype=0x217584da, rev 0..0, 1..2, 3..255)` with empty `/chosen` and zero-size memory placeholders.
- **Load addresses & fields preserved byte-for-byte:** `kernel_addr = 0x10008000`, `ramdisk_addr = 0x11000000`, `second_addr = 0x10f00000`, `tags_addr = 0x10000100`, `page_size = 2048`, `os_version_raw = 0x2004063c`, `cmdline = "buildvariant=eng"`, and trailing `SEANDROIDENFORCE`.
- **Header digest:** 20-byte SHA-1 at header bytes `576..595` recomputed over `(kernel, size, ramdisk, size, second, size, dt, size)`.

### 4.2 U-Boot Shim and Handoff Contract (`tools/build-j701f-uboot.py`, `kernel/diagnostic/j701f-embedded-ramboot.c`)

- **Source:** Official U-Boot `v2026.01` (`127a42c7257a6ffbbd1575ed1cbaa8f5408a44b3`, SHA-256 `74cc33ec34d48a7376771336ae5c8c3cd1ded9eb53137c7797d926660c2c0001`), patched with:
  1. `kernel/patches/uboot-j701f-diagnostic.patch` — registers the `j7velte` board entry matching `J701F` and hardware revision `3..3`.
  2. `kernel/patches/uboot-aarch64-lld-bss.patch` — fixes `.bss` `NOLOAD` alignment so LLD does not overlap `.bss` with the relocated image/embedded FIT.
- **Locked environment (`kernel/diagnostic/uboot.env`):**
  ```text
  stdin=nulldev
  stdout=nulldev
  stderr=nulldev
  bootdelay=0
  bootcmd=j701f_ramboot
  ```
  `tools/build-j701f-uboot.py` verifies `include/generated/environment.h` to guarantee `bootcmd=j701f_ramboot` is embedded in `u-boot.bin` (which is also the exact marker checked in `BOOT` by `scripts/install-release-on-recovery.sh` and `recovery/installer/installer.sh`).
- **Runtime guards in `do_j701f_ramboot()`:**
  1. `env_get("board")` must equal `"j7velte"` (requires `S-BOOT` command line `J701F` + rev 3).
  2. DRAM banks must equal `0x40000000..0x7e400000` and `0x80000000..0xc0000000`.
  3. U-Boot relocation address `gd->relocaddr` must lie in upper RAM (`0xb8400000..0xc0000000`).
  4. Previous bootloader FDT (`get_prev_bl_fdt_addr()`) must be 8-byte aligned, within measured RAM, valid FDT header (`<= 2 MiB`), and contain `/chosen`.
  5. Embedded FIT (`j701f_embedded_fit`..`j701f_embedded_fit_end`) must be 8-byte aligned, match `J701F_FIT_BYTES`, reside inside the relocated U-Boot monitor allocation above `0xb8400000`, pass `fdt_check_header()` and `fit_check_format()`, and match `j701f_fit_sha256`.
  6. Sets `verify=yes`, `fdt_high=ffffffffffffffff`, `initrd_high=ffffffffffffffff`, and `bootargs`:
     ```text
     rdinit=/init console=tty0 console=ttySAC2,115200n8 loglevel=8 ignore_loglevel clk_ignore_unused regulator_ignore_unused panic=10 s3c2410_wdt.tmr_atboot=1 s3c2410_wdt.keep_on_shutdown=1
     ```
  7. Boots `bootm <addr>#conf-j701f-diagnostic` with no storage scan or fallback.

### 4.3 FIT Payload (`tools/build-mainline-fit.py`)

Contains three SHA-256-verified nodes under `/images/{kernel,fdt,initramfs}` placed into lower RAM below firmware reservations (`0x46000000`):
- **`kernel`:** gzip-compressed Linux 7.1.13 `Image` (`build/kernel/panfrost/Image`), loaded at `0x40000000 + text_offset`.
- **`fdt`:** compiled board DTB (`exynos7870-j7velte-diagnostic.dtb` from the chosen stage DTS), 2 MiB-aligned after kernel memory reservation.
- **`initramfs`:** `initramfs.cpio.gz` built by `tools/build-mainline-initramfs.py`.

### 4.4 Initramfs Handoff Conditions (`kernel/diagnostic/init`, `alpine-handoff`, `recovery-main`)

When Linux 7.1.13 starts `/init` (static AArch64 BusyBox `1.36.1-r31`, SHA-256 `ebd2865edcab0b590c7d0edb70d3e782cbfb541e518a390ced3a3e186509bc7f`):
1. Mounts `/dev` (`devtmpfs`), `/proc`, `/sys`, `/run` (`8m`), `/tmp` (`16m`), `/dev/pts`.
2. Arms a 90-second fallback timer: if handoff does not complete and `/run/stay` is not created, runs `/bin/reboot-recovery` and reboots into `RECOVERY`.
3. Runs `/bin/muic-usb-path` (`CTRL1=0x13`, `SW_CTRL=0x24`) and starts `/bin/usb-configfs` (`04e8:6860`, serial ACM `ttyGS0`).
4. **Branch A — Graphical Recovery image (`RECOVERY` slot, built with `J701F_RECOVERY_UI`):**
   - Contains `/bin/recovery-ui`, `/bin/recovery-main`, and `/recovery/scripts/*.sh`.
   - `recovery_main` creates `/run/stay`, unbinds `vtcon` from the framebuffer, mounts an 80 MiB tmpfs at `/run/recovery-state`, starts the USB serial root shell on `ttyGS0`, starts `/bin/recovery-ui`, and after 8 s starts optional read-only Wi-Fi and MTP helpers.
   - Stays in RAM recovery until the user taps **Boot system**, or `RECOVERY_AUTOBOOT` (240 s) elapses without touch/stay markers, or `/run/recovery-state/reboot` is created.
5. **Branch B — Normal Mainline Boot image (`BOOT` slot, built without `J701F_RECOVERY_UI`):**
   - Contains `/bin/alpine-handoff` and **omits** `/bin/recovery-ui` so it boots straight into the installed system.
   - `alpine_handoff` locates the unique `PARTNAME=USERDATA` block device (`/dev/mmcblk0p24`), verifies `UUID="4ce26b55-8a59-4fb7-aad4-919a5c2cefeb"` and `TYPE="ext4"`, mounts it `ro,noload` to check `/etc/j701f-system-version == BURAK_ALPINE_0_1` and required init paths, runs `e2fsck -p`, remounts `rw`, moves virtual mounts, and runs `switch_root /newroot /sbin/init`.

### 4.5 Current Image Artifacts in the Repository

| Component | Build Command / Source | Current Artifact & Identity |
| --- | --- | --- |
| **Kernel** | `python3 tools/build-kernel.py panfrost --jobs "$(nproc)"` | Linux 7.1.13 (`build/kernel/panfrost/Image`, SHA-256 `2eabbca3de877c1d2daa3a21fcbcffab68723c5995d2e9fb6e6cd08b663c078e`) |
| **`BOOT` Image** | `tools/build-mainline-image.sh cam5 kernel/dts/exynos7870-j7velte-camera.dts "--allow-audio --allow-sd --allow-mfc"` | `build/kernel/boot-update-cam5/boot-mainline.img` (14,346,256 bytes, SHA-256 `f2e232a89294ffe5a106d75499b5d37596aaf7b401ce7ef1740cface5ad5877f`) |
| **`RECOVERY` Image** | `J701F_RECOVERY_UI=build/recovery-ui/phone/recovery-ui tools/build-mainline-image.sh rec8 kernel/dts/exynos7870-j7velte-fbmem.dts "--allow-audio --allow-sd --allow-mfc"` | `build/kernel/boot-update-rec8/boot-mainline.img` (15,878,160 bytes, SHA-256 `d439dfaec0c1da2ec25311941721f0baf4910bbeeeb139284bacf1309db1b124`) |
| **First-Install Odin Bundle** | `python3 tools/prepare-first-install.py` | `build/first-install/BOOT-j701f-mainline.tar` (`boot.img`), `build/first-install/RECOVERY-j701f-mainline.tar` (`recovery.img`), `manifest.json` |
| **`USERDATA` Release** | `python3 tools/build-release.py [--development] [...]` | `build/release/userdata.ext4.gz` + `.sha256` + `userdata.ext4.sha256` + `release.json` (23,314,432 sectors, `UUID=4ce26b55-8a59-4fb7-aad4-919a5c2cefeb`, `BURAK_ALPINE_0_1`) |
| **TWRP/OrangeFox ZIP** | `python3 tools/build-recovery-zip.py build/release/j701f-linux-release.zip` | `META-INF/com/google/android/{update-binary,updater-script}`, `j701f/{installer.sh,busybox}`, plus embedded or side-by-side `j701f-release/` |

---

## 5. Odin4 `.tar` Package Contract and `tools/prepare-first-install.py`

When flashing `BOOT` or `RECOVERY` from Samsung Download Mode using `tools/odin4`, archives must obey the strict single-partition USTAR contract:

1. **Archive format:** Uncompressed POSIX `USTAR` (`tarfile.USTAR_FORMAT`). No `.tar.md5` suffix is required by `odin4 -a`.
2. **Exact single member per archive (mapped by the phone's factory PIT):**
   - To flash `BOOT` (`/dev/mmcblk0p10`): archive must contain **only** `boot.img` (`uid=0`, `gid=0`, `uname=""`, `gname=""`, `mode=0644`, `mtime=0`, size `<= 33,554,432` bytes), and the inner initramfs must contain `bin/alpine-handoff` and **not** `bin/recovery-ui`.
   - To flash `RECOVERY` (`/dev/mmcblk0p11`): archive must contain **only** `recovery.img` (`uid=0`, `gid=0`, `uname=""`, `gname=""`, `mode=0644`, `mtime=0`, size `<= 39,845,888` bytes), and the inner initramfs must contain `bin/recovery-ui`, `bin/recovery-main`, and `recovery/scripts/flash-boot.sh`.
   - *(Note on `tools/recovery.py verify-tar <ARCHIVE> [--restore]`:* `tools/recovery.py verify-tar` is specific to Stage 1 `recovery.img` archives that preserve the original 3.18 kernel and LZMA ramdisk—for example `python3 tools/recovery.py verify-tar build/recovery.tar` or `python3 tools/recovery.py verify-tar build/OrangeFox-restore.tar --restore`. For mainline U-Boot+FIT `BOOT` and `RECOVERY` Odin archives, `tools/prepare-first-install.py` performs the container, U-Boot `bootcmd=j701f_ramboot`, stub `DTBH`, embedded FIT, initramfs role, and canonical single-member USTAR verification.)*
3. **Canonical byte verification:** No symlinks, hardlinks, device nodes, directory entries, extra files, or trailing non-zero bytes after the USTAR end-of-archive markers.
4. **Host preparation command (never touches USB or the phone):**
   ```sh
   python3 tools/prepare-first-install.py \
     --boot-image build/kernel/boot-update-cam5/boot-mainline.img \
     --recovery-image build/kernel/boot-update-rec8/boot-mainline.img \
     --output-dir build/first-install
   ```
   To verify an existing single-member Odin archive on the host:
   ```sh
   python3 tools/prepare-first-install.py --verify-tar build/first-install/BOOT-j701f-mainline.tar --role boot
   python3 tools/prepare-first-install.py --verify-tar build/first-install/RECOVERY-j701f-mainline.tar --role recovery
   ```

---

## 6. Candidate First-Installation Procedures (Design Specification)

Two candidate manual procedures are defined below. Neither is automated: `scripts/first-install.py` only checks the host side (the Odin archives, the release, and with `--sd` the microSD card mounted on the computer: a removable vfat disk with enough room), prints Route A with the Odin commands written out, and with `--stage` copies the release, the recovery-side scripts and the BOOT image to `SD/j701f-release/`, reading each file back. It never runs Odin, opens USB or talks to the phone.

### Common Prerequisites (Both Candidates)

1. **Rollback files verified on the host PC before touching the phone:**
   - Have the matching stock Samsung `SM-J701F` firmware package (specifically its stock `recovery.img` and `boot.img`) or the verified fallback recovery archive `build/OrangeFox-restore.tar` (`python3 tools/recovery.py verify-tar build/OrangeFox-restore.tar --restore`) ready on the computer, because flashing `RECOVERY` via Odin4 overwrites the phone's existing `RECOVERY` partition before an on-device backup of `RECOVERY` can be read.
2. **User preparation on the stock Android phone:**
   - Back up all personal photos, files, and accounts off the phone (`USERDATA` will be completely erased).
   - In Android **Settings → About phone → Software information**, confirm **Model number** is `SM-J701F` and **Build number / Baseband** starts with `J701F`.
   - In **Settings → Developer options**, enable **OEM unlocking** (required so S-BOOT accepts custom `RECOVERY` and `BOOT` images).
   - If building a personal image with handset-local firmware (Section 3.1), pull `/system/etc/wifi/brcmfmac43430-sdio.*`, `/system/vendor/firmware/BCM43430A1.hcd`, and `/system/vendor/firmware/s5p-mfc-v10.fw` (or `mfc_fw.bin`) read-only over `adb` before leaving Android. Never read `/efs`.
   - Charge the battery to **at least 50 %** and use a reliable data USB cable and a FAT32-formatted microSD card (at least 16 GB; 32 GB if saving full partition backups).
3. **Prepare the host artifacts and FAT32 microSD card:**
   - Run `python3 tools/prepare-first-install.py` to produce and verify `build/first-install/BOOT-j701f-mainline.tar` and `build/first-install/RECOVERY-j701f-mainline.tar`.
   - Build the release payload with `python3 tools/build-release.py` (see Section 3 for generic vs. personal firmware and `--modules-dir` requirements).
   - Copy onto the FAT32 microSD card under `/j701f-release/`:
     - `userdata.ext4.gz`, `userdata.ext4.gz.sha256`, `userdata.ext4.sha256`, `release.json`
     - `scripts/install-release-on-recovery.sh`
     - `boot-mainline.img` (copied from `build/first-install/boot.img`)

---

### Candidate Route A: Via Project Graphical Recovery (`RECOVERY` via Odin4, then `BOOT` + `USERDATA` from Recovery)

#### Step A1 — Flash `RECOVERY` in Download Mode and boot straight into Recovery
1. Power off the phone. Hold **Volume Down + Home + Power** to enter Download Mode, then press **Volume Up**.
2. Connect USB and list the exact Odin device path:
   ```sh
   tools/odin4 -l
   ```
3. Verify and flash `RECOVERY-j701f-mainline.tar` (`RECOVERY` only):
   ```sh
   python3 tools/prepare-first-install.py --verify-tar build/first-install/RECOVERY-j701f-mainline.tar --role recovery
   tools/odin4 -a build/first-install/RECOVERY-j701f-mainline.tar -d /dev/bus/usb/BBB/DDD
   ```
4. **Immediate key transition:** As the phone resets after Odin finishes, immediately hold **Volume Up + Home + Power** so S-BOOT boots directly into the new `RECOVERY` slot before stock Android can boot and overwrite `RECOVERY`.

#### Step A2 — Connect USB Serial Console, Hold Recovery, and Back Up Stock `BOOT`
1. Once the graphical recovery screen appears, connect over the USB serial console from the host:
   ```sh
   python3 tools/usb-console.py
   ```
2. Hold the recovery open, mount the external SD card, and stop background helpers that might touch storage:
   ```sh
   : > /run/recovery-state/stay
   sh /recovery/scripts/storage.sh mount-sd
   sh /recovery/scripts/mtp.sh down
   sh /recovery/scripts/wifi.sh down
   umount /mnt/root 2>/dev/null || true
   ```
3. Save a full 32 MiB read-only backup of the live stock Android `BOOT` partition (`/dev/mmcblk0p10`) onto the SD card and verify its SHA-256 before modifying `BOOT`:
   ```sh
   mkdir -p /mnt/sd/j701f-backups
   dd if=/dev/mmcblk0p10 of=/mnt/sd/j701f-backups/boot-stock-backup.img bs=1048576
   sync
   sha256sum /dev/mmcblk0p10 /mnt/sd/j701f-backups/boot-stock-backup.img
   ```

#### Step A3 — Write and Verify Mainline `BOOT` via `flash-boot.sh`
Write mainline `BOOT` using the recovery's guarded writer (`recovery/scripts/flash-boot.sh`):
```sh
J701F_RECOVERY_STATE=/run/recovery-state \
  sh /recovery/scripts/flash-boot.sh write \
  /mnt/sd/j701f-release/boot-mainline.img \
  f2e232a89294ffe5a106d75499b5d37596aaf7b401ce7ef1740cface5ad5877f
```
Wait for `WRITTEN AND VERIFIED: boot-mainline.img`.

#### Step A4 — Dry-Run, Write, and Full Read-Back Verify `USERDATA`
1. Run the preflight dry-run of `install-release-on-recovery.sh`:
   ```sh
   sh /mnt/sd/j701f-release/install-release-on-recovery.sh \
     --source /mnt/sd/j701f-release --erase-userdata
   ```
   Confirm it ends with `DRY RUN ONLY`.
2. Execute the installation:
   ```sh
   sh /mnt/sd/j701f-release/install-release-on-recovery.sh \
     --source /mnt/sd/j701f-release --execute --erase-userdata
   ```
   Wait for `WRITTEN AND VERIFIED` and `PASS` in `/mnt/sd/j701f-release/install.status`, then choose **Boot system**.

---

### Candidate Route B: Via TWRP / OrangeFox Recovery ZIP + Mainline `BOOT`

1. **Prerequisite backup and Mainline `BOOT` installation:**
   - In TWRP/OrangeFox (or before flashing), back up stock `Boot` (and `Recovery` if desired) to the external MicroSD card.
   - Because `recovery/installer/installer.sh` checks that `/dev/block/platform/13540000.dwmmc0/by-name/BOOT` already contains `bootcmd=j701f_ramboot` before allowing `USERDATA` to be erased, install mainline `BOOT` first:
     - Either flash `build/first-install/BOOT-j701f-mainline.tar` in Download Mode (`tools/odin4 -a build/first-install/BOOT-j701f-mainline.tar -d /dev/bus/usb/BBB/DDD`) and hold **Volume Up + Home + Power** to re-enter TWRP/OrangeFox,
     - Or in TWRP/OrangeFox use **Install → Install Image** to write `boot-mainline.img` to the **Boot** partition.
2. **Run the Recovery Installer ZIP (`j701f-linux-installer.zip`) from the MicroSD card:**
   - Disable MTP and unmount `Data` in TWRP/OrangeFox.
   - Select `j701f-linux-installer.zip` on the MicroSD card (with `j701f-release/` beside it or embedded).
   - Confirm with **Volume UP** within 60 seconds when prompted, wait for the full 11.9 GiB SHA-256 read-back verification (`DONE: USERDATA written and verified`), and reboot to system.
3. **Installing the project's graphical recovery (`RECOVERY`):**
   - Flash `build/first-install/RECOVERY-j701f-mainline.tar` via Odin4 (or `tools/install-recovery.sh rec8` once SSH is configured on the booted Linux system) so `RECOVERY` holds the project's mainline graphical recovery.

---

## 7. Post-Install First Boot and Rollback / Rescue Path

- **First boot:** The one-shot OpenRC service `j701f-release-setup` rebuilds the machine-local caches that cross-architecture package installation could not (machine id, certificates, GLib schemas, GIO modules, pixbuf loaders, GTK input methods, MIME database, AppStream catalogue, fonts, udev hwdb and an input re-trigger, icon caches) before D-Bus and SDDM start. Each step keeps its own stamp; a step that fails is retried on at most three boots and then skipped with a warning in `/var/log/j701f-release-firstboot.log`.
- **Account and lock screen:** `burak-alpine` starts with an **empty password** (`pam_unix nullok`), so the Plasma Mobile lock screen opens without one; `kscreenlockerrc` starts with `Autolock`, `LockOnResume` and `LockOnStart` off and `RequirePassword=false`. `/etc/shadow` is `root:shadow` 640 so that the lock screen can check a password once one is set. Anyone holding the phone can use it until the owner runs `passwd` and switches the screen lock on again in the settings. Whether the mobile shell honours these settings on the power key has to be checked on the device.
- **Network and SSH:** No Wi-Fi credentials, SSH keys or host keys are preinstalled. NetworkManager runs persistently so Wi-Fi can be set up from the Plasma settings; SSH accepts public keys only (`PasswordAuthentication no`) and creates its host keys on first start, so `~/.ssh/authorized_keys` for `burak-alpine` has to be added before SSH is usable.
- **If `USERDATA` write is interrupted:** `BOOT` and `RECOVERY` remain intact; stay in recovery, inspect `install.status`, and re-run the `USERDATA` step.
- **If `BOOT` fails to hand off after 90 seconds:** Initramfs automatically executes `/bin/reboot-recovery` to enter `RECOVERY`.
- **Returning to stock Android:** Restore `boot-stock-backup.img` (or flash stock `BOOT`, `RECOVERY`, and `USERDATA`/`AP` archives via Odin4 in Download Mode).

**None of the automation in this plan has been run on hardware yet.**
