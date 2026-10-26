# Burak Alpine 0.1 — BOOT and DATA flashing files

Prepared for the measured SM-J701F / j7velte on 2026-10-07. This is an experimental development system. The staged DATA installation and startup-file read-back passed, followed by a successful normal BOOT into Alpine on DATA. A read-only USB capture confirms BusyBox init as PID 1, the DATA root mounted writable and about 10.8 GiB available. See `build/phone-normal-boot.txt`. No physical partition was written while preparing them.

## Files

| File under `build/system/` | Contents and target |
| --- | --- |
| `boot.img` / `boot.tar` | Kernel and complete device-tree table from the working recovery, a small Linux loader initramfs, and BOOT's measured original header/load parameters. Targets BOOT only; image is 19,181,584 bytes, below its 32 MiB capacity. |
| `userdata.img` / `userdata.tar` | Android sparse ext4 image containing Alpine 3.24.0 and the touchscreen/USB terminal. Targets USERDATA (DATA) only. Samsung sparse file is 292,461,376 bytes; expands to 11,936,989,184 bytes, the full measured DATA capacity. |
| `burak-alpine.tar` | Combined Odin AP archive containing only `userdata.img` and `boot.img`, in that archive order. The automatic script uses separate archives for DATA-before-BOOT sequencing and supports a DATA-only trial. |
| `BOOT-restore.tar` | Exact live original 32 MiB BOOT partition backup, including its stock signing footer and padding. Targets BOOT only. Restoring BOOT does not restore overwritten Android DATA. |
| `manifest.json` | Sizes, SHA-256 checksums, filesystem UUID/features, measured MMC identity hash and test-status fields. |
| `userdata.ext4` | Host build/check source, a raw 11.1 GiB filesystem. Do not supply this raw file to Odin; use the sparse archive above. |

BOOT's original kernel and device trees are deliberately replaced with the unmodified known working recovery kernel/device trees. Load addresses, header command line, OS-version word and other unrelated BOOT header fields remain as observed; payload sizes and SHA-1 are updated. The original stock signing footer cannot authenticate modified contents and is not reused in the custom image. The custom image uses the same unsigned development trailer as the working custom recovery. No Samsung early bootloader or security-bypass code is supplied.

The firmware supplied in `tools/SAMFW.COM_SM-J701F_TUR_J701FXXUACUH1_fac/` maps `boot.img` to BOOT and `userdata.img` to USERDATA in its PIT; its AP archive also contains those filenames. The PIT is an inspection reference only, never a flash input. SYSFS confirms the target capacities. Download Mode model identity is not independently attested by this script: confirm the physical handset is SM-J701F and supply its current Odin-listed USB path.

## Failed first DATA trial and recovery

The first generic Android sparse DATA upload failed at `Close Connection` with `Fail request receive -1`. BOOT was never invoked. The phone displayed the software-update error screen and the recovery key combination returned there. The user successfully reflashed only the verified custom RECOVERY archive and confirmed that its terminal opens again.

A subsequent read-only USB check confirms BOOT's full SHA-256 still matches the original backup. DATA's initial bytes and superblock UUID region are zero; blkid reports no recognized filesystem. DATA was affected by the failed upload and cannot be treated as installed Alpine. See `build/phone-flash-failure-check.txt`.

The supplied J701F firmware's `userdata.img` has 32-byte sparse file headers, 16-byte chunk headers, a zero file-header extension, `0x55ca` chunk extensions, and only RAW/DONT_CARE chunks. The rejected image instead used generic 28/12 headers and FILL chunks. This is a plausible compatibility issue, not a proved sole cause of the hardware failure. The prepared DATA archive matches that measured firmware encoding. The subsequent staged trial is supported by a successful installed-root/startup-file read-back; normal BOOT subsequently passed as recorded in the current hardware report. Old rejected archives are preserved under `build/system/failed-generic-sparse/` and must not be retried.

The writer uses dumpe2fs's complete checked block allocation map, including uninitialized block groups. Every allocated block is RAW, including zero inode tables, journal and metadata. Only blocks explicitly free in ext4 are DONT_CARE. DONT_CARE does not promise to zero old physical contents, and this installation is not a secure erase. The expanded logical root size remains the full agreed DATA capacity. Generic sparse bundles are now rejected by the flasher's validator.

## Automatic flashing

The phone must already be in Download Mode. Use the working recovery's Power menu to select Download mode, then connect USB. Close other flashing/serial tools. Run from the repository root:

```sh
# Validate all files and preview the exact commands. Does not open USB.
./scripts/flash-system.sh

# Read the current Download Mode device path.
./tools/odin4 -l

# Replace BBB/DDD with the actual numeric path from that listing.
# Staged DATA installation, now followed by a passing hardware read-back.
./scripts/flash-system.sh --execute --device /dev/bus/usb/BBB/DDD --discard-existing-data --data-only

# After Odin reports success, enter the existing recovery with its key combination.
# Close serial terminals, then check the installed root without journal replay.
python3 tools/check-installed-system.py
```

**Execution replaces DATA, including Android app data and internal-storage files, then BOOT. This project has a verified original BOOT backup, not a DATA backup.** Preserve any wanted data before using the execution command. There is no extra interactive confirmation: `--execute`, the explicit device path and `--discard-existing-data` are the deliberate write request. `--reboot` is optional and applies only to the final BOOT operation; omit it to remain in Download Mode.

The DATA-only trial now has a passing read-back. BOOT-only installation and first normal boot have also passed. The command below documents that installation step; a working system does not need another flash. `--data-only` cannot be combined with `--reboot` or `--boot-only`; unchanged Android BOOT is not the installed Alpine loader. The full two-partition automatic path remains available by omitting `--data-only`, with optional `--reboot`, but is not the next staged trial.

The script revalidates files before each operation, checks that the selected device remains listed, and invokes only `odin4 -a <validated archive> -d <selected path>`. It never passes a PIT, erase/repartition request, BL/CP/CSC archive, or RECOVERY/SYSTEM image. DATA is written first. If that operation fails, BOOT is not attempted. If BOOT fails or the device re-enumerates after successful DATA flashing, reconnect/re-enter Download Mode, obtain the new path and resume:

```sh
./scripts/flash-system.sh --execute --device /dev/bus/usb/BBB/DDD --boot-only --reboot
```

Use `--boot-only` only after DATA succeeded. These operations are not atomic; a failed operation can leave its target partially written. Tool success alone is not a boot or read-back verification. The independent installed RECOVERY remains the rescue route; this script leaves it untouched. Host USB permissions must already allow Odin access, as with the existing recovery flasher.

The combined AP archive is provided for manual Odin users; an archive's member order is not a guarantee about every flashing tool's internal scheduling. The separate-archive script is the supported automated path.

## Startup behavior

The Linux loader waits briefly for the measured internal partition layout, checks DATA's project UUID and ext4 type, inspects the root with journal replay disabled, and verifies the project marker, matching system version and AArch64 BusyBox init. It then reopens the selected Linux filesystem writable with normal journal handling, moves virtual mounts and executes `switch_root` as PID 1. An invalid/missing root falls back to the embedded RAM rescue environment before handoff. Failures after a partial virtual-mount move or after entering the new init require the separate recovery route; automatic rollback is not promised.

Alpine's supplied OpenRC/virtual-console inittab is replaced with BusyBox init entries for the phone-specific startup script, framebuffer terminal/keyboard and independent USB shell. The local/USB shell includes `/usr/sbin:/usr/bin:/sbin:/bin` so `apk` is available. These are unauthenticated local development root shells, matching the existing development recovery.

The first normal boot is confirmed. The terminal can be checked with `cat /etc/alpine-release`, `uname -a`, `apk --version` and `ls`. USB access continues through `python3 tools/usb-console.py`. Logs are `/tmp/boot.log`, `/tmp/usb.log`, `/tmp/display.log` and the loader's layout log. Network connectivity and package installation have not been tested.

## Build and validation

```sh
./scripts/build-system.sh
python3 tools/build-system.py verify
```

Requires host Python, Clang/LLD, GNU make, curl/GPG for input verification, fakeroot, e2fsprogs (`mkfs.ext4`, `e2fsck`), and `dumpe2fs`/`debugfs` from e2fsprogs. DATA encoding is implemented directly from the measured Samsung sparse format, with no img2simg dependency. About 12 GiB of host disk space is needed for the raw filesystem and outputs. No host root privilege or physical-device formatting is needed. Formatting is confined to the explicitly created regular host image file.

The official Alpine minirootfs checksum/signature are pinned and verified; archive traversal and device entries are rejected before extraction. Signed archive modes are restored explicitly and fakeroot supplies root ownership to the image builder. Read-only `e2fsck` passes. Android sparse bounds and ext4 UUID, capacity and legacy feature masks are checked; decoded sparse bytes were compared exactly against the host raw image. The filesystem excludes 64bit/metadata_csum/orphan-file/encryption and other newer features. Every tar has an exact filename allowlist, canonical USTAR encoding and verified hashes.

`build/backups/boot-original.img` and its JSON record are a checksum-matched read-only live BOOT backup. `python3 tools/backup-boot.py` is the standalone acquisition tool and refuses to overwrite an existing backup. Temporary block nodes use RAM `/dev`; `/tmp` is mounted `nodev` and cannot be used for those nodes.

All 58 Python tests and native sanitizer/AArch64 execution checks passed. `build/phone-system-handoff.txt` records an isolated mount/PID/UTS namespace trial: a 64 MiB RAM-backed ext4 root with the same feature set and startup code passed read-only validation, reopened writable, received the virtual mounts, executed Alpine BusyBox `/sbin/init` as PID 1, and ran APK successfully. Test getty/display services were replaced by a proof task to preserve the live recovery's screen and USB; the actual touchscreen/USB components have their existing separate hardware evidence. The test namespace, loop device and RAM mounts were removed, leaving only the original virtual/RAM mounts.

The first namespace trial passed handoff but its harness used a missing `/proc/.../children` interface and stalled during process discovery. It was safely stopped and cleaned, then the corrected harness identified its namespace by a private RAM token and completed automatically. Both the successful handoff and cleanup are confirmed in the final report. Repeat with `python3 tools/test-system-handoff.py` only from the working recovery; it performs no physical partition write.

Filesystem build timestamps and directory hash seeds are not normalized, so a rebuild can have different output hashes. The manifest identifies the actual prepared files rather than promising byte-identical filesystem rebuilds.

The current host checks also cover Samsung header/chunk extensions, rejection of FILL chunks in this profile, allocation-map completeness/counts/bounds, explicit RAW transmission of allocated zero metadata, and DATA-only failure/reboot restrictions. The larger corrected sparse file still decodes exactly to the unchanged raw ext4 host image and passes read-only e2fsck.

The USB read-back checker validates internal MMC identity, measured partition layout, DATA's project UUID/type, root/init structure and SHA-256 of 14 startup files (including BusyBox, APK, musl, display/USB helpers and init configuration). Expected file hashes are extracted from the host raw filesystem during packaging and recorded in the bundle manifest. The candidate is mounted `ro,noload,nosuid,nodev,noexec`; no root executable is run and no repair is attempted. Mount and RAM device nodes are removed afterward. This check does not compare every partition byte or establish normal BOOT behavior.

The checker was exercised on the recovered phone before the new DATA trial: it correctly rejected DATA with `DATA_UUID_MISMATCH` and reported `READBACK_RAM_CLEANUP_OK`. The subsequent positive installed-system check passed the project UUID/root structure and all 14 startup-file hashes, with cleanup confirmed. See `build/phone-installed-system-check.txt`.

Current normal-boot evidence confirms the mounted DATA root and USB shell. Repeat-reboot persistence, normal-system Power menu destinations, networking and package installation remain separate checks. Hardware status applies to the current prepared images, not automatically to future rebuilds.
