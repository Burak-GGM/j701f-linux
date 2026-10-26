# Internal BOOT/DATA layout

Status: the selected BOOT/DATA layout is installed and its first normal Alpine 3.24.0 boot is confirmed. BOOT holds the known recovery kernel/DTBH and Linux loader; DATA is mounted writable as the Alpine root; RECOVERY remains the rescue environment. SYSTEM is outside the installer. Read-only USB evidence is `build/phone-normal-boot.txt`; see [system-flashing.md](system-flashing.md).

## Measured partition map

Read from the running phone's `/sys/class/block/*/uevent`, `size` and `dev`, and cross-checked against `/proc/partitions`. The report is `build/phone-internal-layout.txt`. Sysfs `size` uses 512-byte sectors. No block partition was mounted or written. The recovery has no populated by-name directory, so future code must discover `PARTNAME` through sysfs rather than depend on those symlinks.

| Partition | Observed device | Capacity | Proposed role |
| --- | --- | --- | --- |
| BOOT | mmcblk0p10, 259:2 | 65,536 sectors = 32 MiB | Linux kernel, Samsung DTBH/DTB and a small initramfs containing our early userspace loader. |
| RECOVERY | mmcblk0p11, 259:3 | 77,824 sectors = 38 MiB | Independent working recovery terminal, touchscreen keyboard, USB shell and power menu. |
| SYSTEM | mmcblk0p18, 259:10 | 6,291,456 sectors = 3 GiB | Keep its current contents; no Linux root here in this layout. |
| USERDATA (Android DATA) | mmcblk0p24, 259:16 | 23,314,432 sectors = 11.1171875 GiB | Dedicated ext4 Alpine root filesystem in a later installation. Replaces existing Android data and internal-storage files. Usable filesystem space will be lower. |

Device numbers are observations, not permanent identifiers to embed in a writer. Identify the internal MMC parent, exact partition names, capacities and current device numbers on each run; ambiguous or mismatching identities must fail closed. Keep the existing partition table. No repartitioning or Samsung early bootloader replacement is proposed.

The recovery image built for this milestone is 19,179,536 bytes, below both measured BOOT and RECOVERY capacities. This establishes room for a similarly sized image; it does not establish that Samsung will accept this recovery kernel/image through the normal BOOT path. BOOT's current image, header, command line and boot-route behavior still need inspection before building a BOOT artifact. The existing recovery-only packer and flash helper must not be repurposed to write BOOT by merely renaming their output.

## Loader approach

```text
Existing Samsung BootROM and early bootloader
  -> BOOT: Linux kernel + device trees + our initramfs
  -> /init: identify and validate USERDATA
  -> mount USERDATA as the Linux root
  -> switch_root and execute the system's /sbin/init as PID 1
  -> Alpine userspace

Recovery boot route
  -> RECOVERY: existing working Linux rescue environment
```

This is a Linux early userspace loader. It keeps the running kernel when starting the system; it is not U-Boot, a firmware replacement or a loader for arbitrary new kernels. The extracted kernel configuration has no enabled KEXEC option, and the running phone exposes no kexec status interfaces. Do not assume a second-kernel handoff exists. A U-Boot-style loader would require a separate feasibility milestone covering an actual launch mechanism and the device's memory map.

The current kernel enables ext4 directly. Overlayfs and SquashFS are disabled, so the proposed first system uses a plain ext4 root rather than requiring those features. Basic Alpine userspace compatibility with this 3.18 kernel is confirmed by the RAM trial; full init/boot and application compatibility still need testing before installation; the selected Alpine archive is not a kernel or a complete configured phone OS.

## Implemented loader and prepared files

`boot-manager inspect` verifies the internal partition names, common MMC parent and capacities. `boot-manager check` inspects DATA read-only with journal replay disabled; `validate-root /absolute/path` checks an already-mounted candidate. v0.2 uses private RAM device nodes under `/dev`, because `/tmp` is mounted `nodev`.

BOOT's separate PID 1 loader implements UUID/version validation, read-only inspection, normal writable reopening and `switch_root`, with an embedded RAM rescue environment for failures before handoff. The phone-specific Alpine init, touchscreen and USB service configuration are prepared. An isolated RAM-backed ext4 handoff trial passed on hardware and cleaned up afterward. The installed DATA startup-file read-back and first normal BOOT route have since passed.

The prepared files and automated DATA-then-BOOT installer are documented in [system-flashing.md](system-flashing.md). No physical partition was written during preparation. Installing them later replaces DATA and BOOT; SYSTEM, RECOVERY and the early Samsung boot chain remain outside the installer. The live original BOOT is backed up and checksum-verified; no DATA backup has been made by this project.

## Current DATA observation and validation evidence

The first DATA-signature probe used a temporary block node under `/tmp`, whose `nodev` mount option prevented device access. Its unrecognized-signature result was not evidence of encryption or corruption. A corrected probe using a RAM node under `/dev` identified DATA as ext4, UUID `57f8f4bc-abf4-655f-bf67-946fc0f9f25b`; see `build/phone-boot-header.txt`. The Linux image uses a different pinned project UUID to avoid mistaking the existing Android filesystem for Linux. Existing file contents were not inspected.

The supplied OrangeFox fstab allows encryption, but that configuration alone does not establish the current encryption state. No unlock, repair or physical DATA mount was attempted during preparation. The loader discovery, RAM Alpine trial, isolated PID 1 handoff and host image checks are documented separately; a live normal BOOT/startup and flash read-back remain the next hardware checks.

After the first failed generic sparse upload, the DATA start and superblock UUID bytes are zero and no filesystem signature is recognized. This supersedes the earlier Android ext4 observation above. The recovered rescue environment and unchanged BOOT were checked read-only; `build/phone-flash-failure-check.txt` records the result.

The first normal Alpine boot now has a USB capture showing BusyBox init as PID 1 and DATA mounted as writable ext4 at `/`, with about 10.8 GiB available. This supersedes the historical invalid DATA state from the failed first upload. Reboot persistence and additional services remain separate checks.
