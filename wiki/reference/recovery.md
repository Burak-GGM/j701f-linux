# Graphical recovery

!!! success "Status: installed (2026-10-10)"
    The RECOVERY slot holds this recovery. The vendor 3.18 fallback it replaced is kept as a file.

## What it is

A small self-contained system for the 38 MiB RECOVERY slot, in the spirit of TWRP or OrangeFox but for this Linux installation: the project's mainline kernel, an initramfs of a few megabytes, and one statically linked program that draws the user interface. It needs nothing from the installed system, so it still works when that system does not start.

The owner's decisions (2026-10-10): it will replace the vendor fallback in RECOVERY once it has proved itself; it should be able to use Wi-Fi; the interface is in English and Turkish, English by default.

## Screens

| Tile | What it does | State |
| --- | --- | --- |
| Boot system | hands over to the installed Alpine | works (tried on the phone) |
| Kernel | shows the running kernel, the BOOT slot and its hash, battery, memory; writes an image file to BOOT with read-back, keeps the old one, rolls back | works on the phone, also by tapping: write and rollback each verified |
| Files | browses the recovery, the installed system (mounted read-only) and the SD card; shows a file as text; copies a file to the SD card | works on the phone by tapping: browse, select, copy |
| Terminal | a shell with an on-screen keyboard | works on the phone screen |
| Backup | archives `/etc` and the user's settings to the SD card, verifies the newest archive | works on the phone (28 MB in 17 s) |
| Maintenance | read-only filesystem check, kernel log and crash log, Wi-Fi and SSH on/off | works on the phone |
| Power | reboot to system, recovery or download mode; power off | reboot to system works on the phone; the other three not exercised |

The button at the top right switches between English and Turkish. Since `rec8` the choice survives a restart: the recovery keeps its settings in one 512-byte block near the end of its own slot (`recovery/scripts/settings.sh`), because it has no writable filesystem and never writes to the installed system.

A USB serial shell runs the whole time, whatever the screen shows. Since `rec7` the computer also sees the phone as an MTP device ("SM-J701F Recovery") with two storages: the installed system's home directory, read-only, and the SD card, read-write.

## Safety rules built in

- The installed system is mounted **read-only without replaying its journal** (`ro,noload`), and its partition is switched to read-only at the block-device level first. The second part was added after the kernel log showed ext4 deleting an orphaned inode during a "read-only" mount: on a writable device it does that. The recovery unmounts it again before handing over; if that fails it reboots instead of starting a system on a half-shared mount.
- The flashing script writes the BOOT slot and nothing else. PIT, bootloader, EFS, TrustZone, modem and RPMB cannot be selected.
- The SD card is the only place the Backup and Files pages write to, and nothing there is overwritten.
- Restoring a backup only unpacks into an empty directory.
- Trial safety: if nobody touches the screen or uses the USB shell for 240 seconds, the recovery boots the installed system by itself.
- Functions that could erase the installed system are not run or tested on this phone (owner's rule). Their code is exercised on image files on the computer (`tests/test_recovery_*.py`).

## Where things are

| Path | Contents |
| --- | --- |
| `docs/recovery-design.md` | design, the five-step path, the owner's decisions |
| `recovery/ui/main.c` | the interface (LVGL 9.2, MIT licence) |
| `recovery/ui/gen-tr-font.py`, `font_tr.c` | the twelve Turkish letters LVGL's built-in font lacks, generated from the same Montserrat file |
| `recovery/scripts/` | `sysinfo.sh`, `flash-boot.sh`, `backup.sh`, `storage.sh`, `wifi.sh`, `power.sh` — everything that touches storage, kept outside the interface so that it can be tested |
| `kernel/diagnostic/recovery-main` | recovery mode of the initramfs `/init` |
| `tests/test_recovery_flash.py`, `tests/test_recovery_backup.py` | tests on temporary files |

## Building and trying

```bash
make -C recovery/ui
```

builds the computer version, which draws any screen into a picture without a display:

```bash
J701F_RECOVERY_LANG=tr build/recovery-ui/host/recovery-ui --snapshot /tmp/home.ppm
```

The phone version is built on the phone itself (`make TARGET=phone`, static binary) and goes into an image with

```bash
J701F_RECOVERY_UI=build/recovery-ui/phone/recovery-ui tools/build-mainline-image.sh NAME kernel/dts/exynos7870-j7velte-fbmem.dts "--allow-audio --allow-sd --allow-mfc"
```

## What the first trial taught

- The text console keeps drawing on the framebuffer after the interface has painted its first frame; the recovery has to unbind it first.
- LVGL's own touch reader only reports the state left after it has emptied the event queue, so a short tap can vanish. The interface now reads the touchscreen itself and stops at every press and release.
- After the recovery had handed over, the installed system's USB shell did not answer; the update script needs the reboot to be requested over SSH in that case.

## Wi-Fi and SSH

The Wi-Fi driver and its firmware are part of the recovery. The programs that make a connection (`wpa_supplicant`, `udhcpc`, `sshd`), the saved network and the SSH host keys are **borrowed from the installed system**, which is mounted read-only for this, with small RAM filesystems over its `/run` and `/tmp`. The recovery tries this by itself a few seconds after it starts; the Maintenance page can switch it off and on.

An SSH login therefore lands in the installed system's files (read-only) but on the recovery's kernel. If the installed system's files cannot be read, there is no Wi-Fi — the USB shell is the path that never depends on them.

## What the second trial taught

- `/run` in the initramfs is 8 MiB; keeping the previous 32 MiB BOOT contents for a rollback needs its own RAM filesystem. The writer refused before touching BOOT, which is the behaviour wanted, but it did so without a message.
- `wpa_cli` creates its reply socket in `/tmp`; on a read-only system that fails and looks like "never associated".
- The SD card is `mmcblk2` on the mainline kernel and `mmcblk1` on the vendor one; the script now asks each device for its type.
- `e2fsck` is not statically linked in Alpine: the image carries it with its libraries and the C library's loader in `/recovery/lib`.

## What the third trial showed

- Wi-Fi and SSH came up by themselves after boot; the whole write / roll back / write sequence was driven over SSH with no cable needed.
- During a write two copies of the 32 MiB slot exist for a moment (the one kept for rollback and the new one being taken), so the state area is 80 MiB.
- Hardware keys work: volume down twice and power opened the Kernel page. The Home key selects as well (it reports `KEY_LEFTMETA` on this board; fixed in `rec6` after the owner found it dead).
- An SSH login has its own `/run`; to keep the recovery from booting the system after 240 seconds, create `/run/recovery-state/stay`.

## Installed

Since 2026-10-10 the RECOVERY slot holds this recovery (image `rec8` since the same evening; `tools/install-recovery.sh` writes a new one). It is started with the recovery key combination or from the system with `~/j701f/boot-swap/reboot-recovery.sh --execute`, which shuts the filesystems down cleanly first (the bare `reboot-recovery` helper does not). If nobody touches the screen, presses a key or sets the stay marker for 240 seconds, it boots the installed system.

Kernel updates go through it: `tools/run-recovery-update.sh NAME` stages the image, reboots into the recovery, has it write and verify BOOT over SSH, and reboots. The older `tools/run-boot-update.sh` needed the vendor system in RECOVERY and now stops with a pointer to the new tool.

The vendor 3.18 system that used to be in the slot is kept whole (38 MiB) on the phone and on the computer; `tools/restore-vendor-recovery.sh` writes it back. That script has not been run.
