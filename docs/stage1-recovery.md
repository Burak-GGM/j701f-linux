# Stage 1: the RAM-only recovery userspace (historical)

This was the project's README until 2026-10-26. It describes the first stage of the work, a small
BusyBox userspace repacked into the OrangeFox recovery image, and the status at that time. It is kept
because `make test` and the scripts it names still build and check that stage. The current state of
the port is in the [repository README](../README.md) and the [wiki](../wiki/index.md).

Reproducing this stage needs the user-supplied OrangeFox image in `original/` and Samsung's `odin4`
in `tools/`; neither is part of the repository.

This project started by replacing OrangeFox's userspace with a small, RAM-only Linux userspace for **Samsung SM-J701F / j7velte / Exynos 7870**. Normal BOOT retains the supplied working kernel and Alpine on DATA. RECOVERY has been restored to the verified working rescue after the third failed diagnostic trial. Normal Alpine and SSH are reachable at **192.168.1.145** after the subsequent terminal UI installation. See [kernel builds and the Panfrost route](kernel-build.md) and the [J701F diagnostic trial](j701f-mainline.md).

**Latest trial:** A changed Linux 6.15 diagnostic with embedded FIT, empty Android ramdisk, stub DTBH and corrected U-Boot BSS layout was flashed to RECOVERY and fully read-back verified. The phone stayed at the Samsung logo and exposed no diagnostic USB in 180 seconds. After the user entered Download Mode, the current new UI rescue was restored; full BOOT/RECOVERY/CID and UI binary checks passed. Normal Alpine, the new UI, Wi-Fi and pinned-key SSH returned at **192.168.1.145**. [Third-trial evidence](j701f-mainline.md#third-candidate-embedded-fit-and-corrected-loader-layout).

**Remote development:** The one accepted unattended attempt has been consumed. Physical Download Mode access has now been demonstrated again, and the working rescue is restored. All three rejected unchanged candidates remain excluded from another trial. None produced verified mainline execution. [Packaging and recovery assessment](j701f-mainline.md#remote-investigation-and-smaller-offline-preview).

**Terminal UI installed:** Normal Alpine and RECOVERY now run the new C terminal with clock/IP/PTY status, three swipeable shell sessions, scrollback and staggered keyboard. Both boot paths passed; the user confirmed typing, session switching and scrolling. A queued-input/timestamp refinement is installed for the reported rapid-tap issue; physical confirmation is pending. Wi-Fi/SSH are reachable at **192.168.1.145**. A full hash-verified backup of this new rescue is saved. [Controls and evidence](ondevice-terminal.md).

**Last verified normal-system status:** Alpine 3.24.0 boots persistently from DATA with the existing kernel/BOOT loader. Touchscreen terminal, corrected screen colors, Wi-Fi and key-based SSH work. The Qt GUI is responsive overall; a further renderer revision reduces measured offscreen terminal latency from 78.5 to 16.3 ms and is installed for the next manual trial. Physical typing response still needs confirmation. The saved recovery has a long-Power menu whose layout/buttons passed a dry run; actual action destinations need separate checks. See [hardware observations](hardware-status.md) and the [current roadmap](next-goals.md). BOOT holds kernel/loader, DATA holds Linux and SYSTEM stays untouched. Mainline boot and GPU acceleration remain unverified.

## Build and verify

Run from the repository root:

```sh
make test
```

This checks tools, imports and inspects the known-good image, verifies an identical original round-trip, prepares static BusyBox, builds the initramfs and recovery image, creates recovery-only Odin archives, and runs regression checks. It does **not** contact or write the phone. After the initial BusyBox download, the build works offline. Use `make` for the build/verification chain without the regression suite.

On Arch, install missing host tools (these modify only host packages, not the phone):

```sh
sudo pacman -S --needed python make bash curl clang lld linux-api-headers
# Optional execution tests and inspection tools:
sudo pacman -S --needed qemu-user binutils cpio
# Optional for working OrangeFox / future Stage 2:
sudo pacman -S --needed android-tools
```

Clang and LLD cross-compile the small framebuffer helper to static AArch64 without libc. Linux UAPI headers come from `linux-api-headers`. No root access, host device nodes, loop devices, or host mounts are needed for the build. Python's standard library supplies newc CPIO, LZMA, gzip, SHA checks, ELF inspection, and USTAR. The optional [qemu-user](https://archlinux.org/packages/extra/x86_64/qemu-user/) package supplies AArch64 userspace emulation; [android-tools](https://archlinux.org/packages/extra/x86_64/android-tools/) supplies ADB. `scripts/check-tools.sh` reports available tools. The user's existing `tools/odin4` is used only by an explicit flash invocation; Thor is left unused.

BusyBox is pinned to Alpine's [busybox-static 1.36.1-r31 for AArch64](https://pkgs.alpinelinux.org/package/v3.20/main/aarch64/busybox-static). Its APK is downloaded over HTTPS and checked against the SHA-256 in `tools/recovery.py` before extracting one regular file. This pin was recorded from the downloaded package; the APK signature was not independently verified. See [third-party.md](third-party.md) for source/licensing and provenance. OrangeFox's original BusyBox is dynamically linked and cannot serve as this stand-alone binary.

## Outputs and source files

| File or directory | Role |
| --- | --- |
| `Makefile` | Ordered build, verification, tests, and non-writing flash-plan targets; no automatic flash target. |
| `tools/recovery.py` | Strict parser/repacker for the inspected baseline; preserves raw header bytes and payloads; creates/verifies initramfs and Odin archives. Refuses other baseline images. |
| `tools/downloads/*.apk` | Cached, checksum-pinned BusyBox package. |
| `tools/busybox-provenance.json` | Package URL, package/binary hashes, architecture and linking information. |
| `original/OrangeFox-recovery.img` | Known-good image copy; checked by SHA-256 on every build. Original files under `tools/` stay intact. |
| `extracted/kernel` | Original ARM64 kernel Image, unchanged. |
| `extracted/dtb` | Entire original Samsung `DTBH` table, including all embedded device trees; never replaced by one guessed DTB. |
| `extracted/second` | Empty original second-stage payload; original address still preserved. |
| `extracted/ramdisk.cpio.lzma` | Original OrangeFox compressed ramdisk. |
| `extracted/boot-metadata/metadata.json` | Extracted addresses, sizes, file offsets, command line, trailer, and hashes. |
| `extracted/boot-metadata/header.bin`, `trailer.bin` | Original raw header page and Samsung trailer. |
| `extracted/boot-metadata/kernel.config` | Kernel configuration recovered from embedded IKCONFIG. |
| `extracted/boot-metadata/original-ramdisk-inventory.json` | Original CPIO paths, modes, sizes, and hashes, read without creating its files/device nodes. |
| `extracted/reference/` | Original init/USB `.rc`, fstab and property files for later investigation; not run or included in Stage 1. |
| `ramdisk/init` | Your editable PID 1 script: virtual mounts, greeting, RAM logs, independent USB/display startup, and console shell. |
| `ramdisk/bin/boot-manager` | Read-only partition discovery and explicit DATA candidate-root inspection; no installation or handoff in v0.1. |
| `ramdisk/bin/usb-debug`, `usb-shell` | Discover/configure legacy ACM gadget and supervise an interactive root shell after the host presses Enter. |
| `ramdisk/bin/display-status`, `fb-heartbeat` | Discover framebuffer/backlight devices and draw text with a changing heartbeat. |
| `ramdisk/etc/usb-baseline.conf` | USB vendor/product IDs extracted from the original OrangeFox USB configuration. |
| `tools/fb-heartbeat.c`, `scripts/build-helpers.sh` | Source and reproducible static AArch64 build for the display helper. |
| `tools/usb-console.py` | Host USB terminal with automatic device identification; Ctrl+] exits. |
| `ramdisk/bin/busybox` | Static AArch64 executable. |
| `ramdisk/dev`, `proc`, `sys`, `tmp` | Layout directories; the CPIO builder supplies exact modes and early device nodes without root. |
| `scripts/unpack.sh` | Imports/inspects the baseline and prepares its restore archive. |
| `scripts/prepare-busybox.sh` | Downloads when absent, then verifies/extracts the pinned binary. |
| `scripts/build-initramfs.sh` | Builds deterministic CPIO plus LZMA and gzip variants. |
| `scripts/repack.sh` | Replaces only the ramdisk, refreshes its size and image ID, and builds `recovery.tar`. |
| `scripts/check-tools.sh`, `test-busybox.sh`, `test-display.sh` | Tool detection, AArch64 execution checks, framebuffer safety tests, and render preview. |
| `scripts/flash.sh` | Validates a recovery-only archive; prints a plan by default; explicit execution requires a USB path and typed confirmation. |
| `tests/test_recovery.py` | Regression tests for corrupted images, altered addresses/payloads, wrong binaries, unsafe archives and flash guards. |
| `tests/test_diagnostics.py`, `fb_heartbeat_test.c`, `fb_runtime_test.c`, `terminal_test.c` | USB/getty fixtures, host port discovery, framebuffer bounds/color, terminal parsing, touch events, partial repaint and real PTY shell checks. |
| `build/ramdisk.cpio`, `.cpio.lzma`, `.cpio.gz` | Identical userspace in raw and compressed formats. **The image uses LZMA**, matching OrangeFox; gzip is also supplied as requested. |
| `build/recovery.img`, `build/recovery.tar` | New Stage 1 image and single-member Odin USTAR archive. |
| `build/original-roundtrip.img` | Exact original image reconstructed from its components. |
| `build/OrangeFox-restore.tar` | Recovery-only restore archive containing the exact original image. |
| `build/build-report.json`, `SHA256SUMS` | Original/new metadata comparison, preservation evidence, and output checksums. |
| `build/verification.log`, `reproducibility.json` | Saved checks from this initial delivery, including two identical builds; these snapshots are not automatically refreshed by later builds. |
| `docs/boot-chain.md` | Boot responsibilities, storage safety policy and later stages. |
| `docs/recovery-image-format.md` | Actual inspected format, extracted values and repacking rules. |
| `docs/debugging.md` | What can be observed, failure diagnosis, verification commands and restore path. |
| `docs/usb-console.md` | Expected screen, host connection command and diagnostic commands for this build. |
| `build/display-preview.ppm` | Host-rendered example of the expected screen; not a phone screenshot. |
| `build/stage1-before-usb/` | Saved previous console-only image and reports; the standard flash helper validates the current build. |
| `tools/reference/` | Downloaded source references used to inspect legacy ACM behavior; not compiled into the image. |
| `docs/third-party.md` | BusyBox provenance, upstream references, and source/licensing notes. |
| `.gitignore` | Excludes firmware, downloaded binaries, generated files and existing stock firmware bundles from source control. |

The archive is built from an explicit allowlist: `/init`, BusyBox, diagnostic scripts/helper, extracted USB configuration, selected applet symlinks, directories, and standard character devices. Dropping extra files into `ramdisk/` does not silently include them. Change the builder intentionally when extending Stage 1. BusyBox contains other applets internally; the shell is root and is **not** a sandbox. The automatic startup script does not mount or write any eMMC partition.

Edit `ramdisk/init`, then run `make test` again. CPIO timestamps/owners/order and tar metadata are fixed. Same inputs, Python/liblzma, Clang/LLD and Linux UAPI header versions should produce identical outputs; package and baseline checksums are fixed. There is no claim of a source-rebuilt or universally bit-identical toolchain.

## RECOVERY-only flash and restore

Keep the original OrangeFox image, its restore tar, and a working Download Mode route available. Confirm the physical model is **SM-J701F**. Live read-only discovery measured RECOVERY at 38 MiB and BOOT at 32 MiB; see the internal layout document. The new image must be no larger than the known-good image; the builder retains this conservative bound in addition to the measured capacity.

Inspect the build and list Download Mode devices (read-only):

```sh
make test
./tools/odin4 -l
./scripts/flash.sh
```

The script's last command only prints a plan. The following command **overwrites RECOVERY only**, using a tar whose sole member is `recovery.img`. It leaves BOOT, SYSTEM, DATA, PIT, BL/sboot, EFS, TrustZone, modem and RPMB-related areas out of the requested operation. Replace `BBB/DDD` with the actual USB path printed by Odin; the placeholder deliberately cannot pass the script's path check.

```sh
./scripts/flash.sh --device /dev/bus/usb/BBB/DDD --execute
```

If USB access requires root on this host, use `sudo` for that same script invocation. The script explains the target again, requires `FLASH RECOVERY`, verifies the archive again, and calls only `tools/odin4 -a <validated-recovery.tar> -d <explicit-USB-path>`. It passes no erase, repartition, bootloader, CP, CSC, or reboot flags. No writes are performed unless that explicit execution path is selected and confirmed.

After Odin reports success, use the device's established hardware-button route directly into recovery. Do not interpret another stock Android bootloop as a Stage 1 result. This project does not repair stock Android. Keeping early boot partitions untouched preserves the intended Download Mode route, but host packaging checks cannot guarantee device behavior or recover from unrelated hardware/bootloader faults.

To return to OrangeFox, enter Download Mode and list the USB path again. First inspect the restore plan:

```sh
./scripts/flash.sh --restore
```

The next command **overwrites RECOVERY only with the exact known-good OrangeFox image**; it does not restore or modify BOOT, SYSTEM, DATA or any other partition:

```sh
./scripts/flash.sh --restore --device /dev/bus/usb/BBB/DDD --execute
```

The nearby stock AP/BL/CP/CSC bundles are never selected by any script. Do not substitute them for these single-member archives. Do not add `-e` or other Odin options. Download Mode is the intended fallback, not a target for modification.

## Alpine RAM compatibility trial

The selected Alpine 3.24.0 AArch64 minirootfs runs on the phone's current recovery kernel in a temporary RAM chroot. Repeat the verified, bounded trial with `python3 tools/alpine-ram-test.py` after closing other serial terminals. Use `--prepare-only` to verify the download without opening USB. No BOOT/SYSTEM/DATA partition is mounted or changed. This tests the base userspace; full system init and boot handoff remain separate work. See [verification, observed results and limits](alpine-ram-trial.md).

## Alpine BOOT/DATA system

The first normal Alpine 3.24.0 boot is confirmed on the SM-J701F. BOOT starts the Linux loader with the known recovery kernel/DTBH; DATA supplies the writable ext4 root. BusyBox runs as PID 1, and the USB shell works. The phone reports about 10.8 GiB free. Evidence is in `build/phone-normal-boot.txt` and [hardware status](hardware-status.md). RECOVERY remains the independent rescue environment and SYSTEM stays outside the installer.

Prepared files are under `build/system/`; `./scripts/flash-system.sh` verifies and previews the installer by default. A staged DATA-only installation, read-only startup-file check and BOOT-only step are documented in [system-flashing.md](system-flashing.md). Installation replaces Android DATA/internal-storage files and BOOT. The original BOOT restore archive is available; no original DATA backup was made. A working system does not need another flash.

This is an experimental development system. Repeat-reboot persistence, networking/package installation and normal-system Power menu destinations remain separate checks. Rebuild with `./scripts/build-system.sh`; hardware evidence for the existing files does not automatically validate a rebuilt image.

## Wiki

A readable account of the whole port (tutorial chapters plus reference pages, English and Turkish) is in `wiki/`; build it with MkDocs Material as described in `wiki/maintaining.md`. Changes to the project are expected to be reflected there.
