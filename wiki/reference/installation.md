# Installing a release

The release installer targets **Samsung SM-J701F (`j7velte`) only**. It puts an Alpine 3.24 filesystem on the 11.12 GiB `USERDATA` partition. The current mainline BOOT kernel and the project's RAM recovery remain in place. A stock Android phone needs those two compatible components installed first; this DATA installer alone cannot turn stock Android into this distribution.

!!! danger "USERDATA is completely erased"
    Installation destroys Android data, internal-storage files, the previous Linux installation, accounts and Wi-Fi settings. Keep a copy of anything needed elsewhere. Loss of power or a failed write can **brick normal boot** until the phone is repaired from recovery or Download Mode. Do not use these files on another J7 variant. The DATA installer never targets PIT, bootloaders, EFS, modem, BOOT or RECOVERY.

## Build the DATA payload

On a Linux computer with Docker and `e2fsprogs`, from the repository root:

```sh
python3 tools/build-release.py --development \
  --modules-dir build/release-scratch/modules
```

`--development` keeps the compiler, Git and diagnostic tools on the phone. The optional modules directory must contain modules built for the exact installed kernel; omit it for a public generic image. The build verifies the pinned, signed Alpine minirootfs, resolves AArch64 packages, provisions the phone-specific services and creates `build/release/userdata.ext4.gz`, two SHA-256 files and `release.json`. The ZIP path is described in [graphical recovery](recovery.md) once it has been validated on the handset.

The compressed payload must remain below FAT32's 4 GiB single-file limit. The full ext4 image has exactly 23,314,432 sectors and the UUID expected by the existing BOOT handoff. The build does not copy saved Wi-Fi networks, SSH keys or passwords. A fresh installation initially boots offline; set up networking on the phone afterward.

## Graphical host installer

On a Linux computer with Python's Tk support, start `python3 tools/installer-gui.py` from the repository. It detects a connected phone by the project's USB serial ID `j701f-diagnostic`; a generic Samsung or unrelated serial device is not accepted. The first button is **Dry run / inspect**, and writing is disabled on opening the window.

The three pages cover different parts of installation:

| Page | Dry run | Write step |
| --- | --- | --- |
| Reinstall release | Verify the release and print the plan with `scripts/install-release.py`. | Back up USERDATA on the external SD when selected (the default), then install through the project's held RAM recovery. `--from-recovery` resumes an already staged release; otherwise supply the running phone's IPv4 address and pinned SSH key. |
| First-install SD staging | Verify the BOOT/RECOVERY bundle, release and optional FAT32 microSD using `scripts/first-install.py`. | Copy the release, scripts and BOOT image to the microSD and read them back. The printed Odin and recovery steps remain manual. |
| TWRP / OrangeFox ZIP | Check ZIP builder inputs and show the planned command. | Build a ZIP on the computer with `tools/build-recovery-zip.py`; optionally embed the release. Installation of the ZIP in a compatible recovery remains manual and has not been hardware tested. |

For any write step, enable **Enable writing for one step**, choose **Run write step**, and approve that step's dialog and exact confirmation phrase. The switch resets after each run. Reinstallation requires a connected diagnostic serial device and the phrase `ERASE USERDATA`; the optional reboot and running without a backup each require their own approval. SD staging requires `STAGE SD`. Replacing an existing ZIP requires `REPLACE ZIP`. Keep the window open during a release install: its recovery job can continue after a USB disconnect even if the host can no longer display progress. The GUI does not run Odin or flash BOOT, RECOVERY, or protected partitions.

## Automatic reinstall from a working J701F Linux system

This route requires the phone to be running this project's Linux, reachable through its pinned SSH host key, with an external SD card inserted and USB connected. It is meant for reinstalling an already prepared handset. Supply its address with `--phone-ip` (or `J701F_PHONE_IP`) and keep its verified SSH key in `build/phone-ssh-known-hosts` (or pass `--known-hosts`). First inspect the plan:

```sh
python3 scripts/install-release.py --release build/release
```

To perform the wipe, use both explicit switches:

```sh
python3 scripts/install-release.py --release build/release --phone-ip PHONE_IP \
  --execute --erase-userdata --backup-userdata --reboot
```

The tool checks the image, copies it to the SD card, verifies the SD copy, enters the RAM recovery, checks the model and partition geometry, verifies the complete decompressed image **before** changing storage, writes only `USERDATA`, and compares a SHA-256 read from the **entire** partition with the built image. `--backup-userdata` first saves and verifies a complete copy of the old partition in 1 GB pieces on the SD card; it needs about 12 GiB of additional free space. Those pieces contain the old data in plain form: keep the card private and remove them when the rollback window is over. The recovery stays open if a check fails. `--reboot` asks it to boot the new system only after the read-back succeeds. Keep USB and power connected throughout.

For a faster copy on a host with MTP/FUSE, mount the phone's USB MTP storage and pass the **external SD storage directory** as `--mtp-sd /path/to/SD-card`. The installer still verifies every file through the phone's physical SD mount before rebooting. Without `--mtp-sd`, it stages files over SSH. The long backup and write run in a separate recovery session; a transient USB serial disconnect does not cancel the in-progress block write.

For example, on a Linux host with `jmtpfs`, create a mount point on a native Linux filesystem and run `jmtpfs "$HOME/j701f-mtp"` after `mkdir -p "$HOME/j701f-mtp"`. Use `--mtp-sd "$HOME/j701f-mtp/SD-card"` in the installation command. The installer unmounts the host MTP view before the phone changes USB mode. The phone's USB MTP service must be running and the external SD card inserted.

The fresh local account has no password or saved SSH credentials. Automatic screen locking is initially disabled so it cannot trap you at an unlock prompt. Set a password on the device, then enable screen locking in System Settings. The image used for this phone's hardware trial includes local firmware and is marked nonredistributable; publish only a generic image or instructions for extracting firmware from each owner's own handset.

## Step-by-step SD installation

This route is useful when the normal Linux system is unavailable but the project's recovery and USB serial console work.

1. Copy `userdata.ext4.gz`, `userdata.ext4.gz.sha256`, `userdata.ext4.sha256`, `release.json` and `scripts/install-release-on-recovery.sh` to `j701f-release/` on an external SD card.
2. Boot the project's recovery, connect USB, and open `python3 tools/usb-console.py` on the computer. Keep the recovery open with `: > /run/recovery-state/stay`.
3. Mount the SD card with `sh /recovery/scripts/storage.sh mount-sd`. Stop the recovery's MTP and Wi-Fi helpers with `sh /recovery/scripts/mtp.sh down` and `sh /recovery/scripts/wifi.sh down`. USB may reconnect after MTP is stopped. Unmount the old DATA with `umount /mnt/root` if mounted.
4. Check everything before the wipe: `sh /mnt/sd/j701f-release/install-release-on-recovery.sh --erase-userdata`. It must end in `DRY RUN ONLY`.
5. Write and verify: `sh /mnt/sd/j701f-release/install-release-on-recovery.sh --execute --erase-userdata`. Wait for `WRITTEN AND VERIFIED` and `PASS` in `/mnt/sd/j701f-release/install.status`. Then choose **Reboot system** in the recovery.

If the write fails, leave the phone in recovery and inspect the visible error plus `install.status`. Do not assume an incomplete DATA partition can boot. The steps above have guards for the exact J701F device tree, the compatible BOOT handoff, the `USERDATA` partition name and size, an unmounted target, gzip integrity and SHA-256 checks.

## Restore a pre-installation DATA backup

When installation used `--backup-userdata`, the external SD contains `j701f-backups/preinstall-userdata-YYYYMMDD-HHMMSS.part.aa` through `.al` and a matching `.sha256`. To restore that **entire previous USERDATA partition**, boot the project's RAM recovery, keep it open, mount the physical SD card, stop MTP and Wi-Fi, and unmount `/mnt/root` as described above. The restore script was copied to `j701f-release/` on the SD card.

First verify all 12 chunks and their full-partition checksum without writing:

```sh
sh /mnt/sd/j701f-release/restore-userdata-on-recovery.sh \
  --backup-id preinstall-userdata-YYYYMMDD-HHMMSS --restore-userdata
```

Replace the timestamp with the actual backup name. To write the old partition back, repeat with `--execute`; this **erases the current USERDATA**. The tool checks the phone and target geometry, rejects mounted DATA, reads and verifies every backup chunk before writing, then hashes the entire restored partition. Wait for `RESTORED AND VERIFIED` and `PASS` in the matching `.restore.status` file before rebooting. A failed restore leaves the recovery available for inspection.

**First hardware run (2026-10-27): the automatic reinstall works.** On the project's own phone `scripts/install-release.py --execute --erase-userdata --backup-userdata --reboot` took a verified 12-chunk backup of the old USERDATA, wrote the release in about five minutes, read the whole partition back with a matching SHA-256 and booted the new system, which logs into Plasma Mobile by itself on the native display. Four faults found on the way are fixed (the recovery's USB serial port was not recognised, stopping MTP cut the USB connection, a password-age field blocked autologin, and an SD check parsed the serial output wrongly); if the first contact with the recovery is lost, `--from-recovery` continues without copying the release again. The recovery ZIP and the first installation from stock Android have not been run on hardware yet.
