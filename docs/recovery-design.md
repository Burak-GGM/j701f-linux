# Graphical recovery: design (roadmap stage R.1)

Written by Claude on 2026-10-10. Status: steps 1-3 reached (trial image `rec1` booted once from BOOT); RECOVERY not written yet.
The owner's rule for this stage is in `docs/roadmap.md`: functions that erase
the installed system or lose files may be written but are never run or tested
on this phone.

## What exists today

| Slot | Size | Holds | Role |
| --- | --- | --- | --- |
| BOOT (mmcblk0p10) | 32 MiB | mainline image (U-Boot loader + FIT: kernel, device tree, small initramfs), about 14 MiB | daily system; its initramfs only checks and mounts USERDATA and hands over |
| RECOVERY (mmcblk0p11) | 38 MiB | vendor 3.18 kernel with the same hand-over initramfs | "the fallback": boots the *same* Alpine root filesystem on the old kernel |

Consequences of that layout:

- The fallback is not a recovery. If the root filesystem is damaged or full,
  neither slot gets as far as a shell on the screen.
- Every kernel update goes through it: reboot into 3.18, copy the image over
  Wi-Fi, write BOOT, reboot. That needs Wi-Fi, SSH and a healthy root.
- Nothing on the phone itself can show which kernel is installed or switch back
  to the previous one without a computer.

An earlier stage of the project had a self-contained rescue initramfs (BusyBox,
an on-screen terminal, a USB shell, a boot menu; `tools/recovery.py`,
`docs/ondevice-terminal.md`). The pieces are still in the repository and are
the starting point.

## Target

A self-contained image in RECOVERY that depends on nothing in USERDATA:

- **Kernel:** a frozen, known-good build of the project's mainline kernel with
  the same boot chain as BOOT. Reasons: touch, display, eMMC, SD card, USB
  gadget and Wi-Fi all work on it, and its image format and tooling exist.
  The vendor 3.18 image is kept as a file (on the computer and in
  `/var/lib/j701f-recovery/` on the root filesystem) and can be written back to
  RECOVERY from the menu or from the running system.
- **Userland:** an initramfs of a few MiB: static BusyBox, `e2fsprogs`
  (`e2fsck`), `dropbear` or the existing USB shell, the UI program, the flashing
  and backup scripts. It never mounts USERDATA read-write unless an action that
  needs it is confirmed on screen.
- **UI:** one statically linked C program using LVGL (MIT licence), drawing to
  the DRM device that simpledrm provides and reading the touchscreen and keys
  through evdev. No GPU, no compositor, no Qt: it has to work when everything
  else is broken. Hardware keys always work as a fallback (volume = move,
  power = select).
- **Always on, with no interaction:** the USB serial shell as today, and USB
  networking with an SSH server, so that the recovery can be driven from the
  computer even if the screen shows nothing.

Budget: kernel 14 MiB + initramfs under 8 MiB, against 38 MiB.

## Screens

| Screen | Contents | Roadmap item |
| --- | --- | --- |
| Home | large tiles: Boot system, Kernel, Files, Terminal, Backup, Maintenance, Power | R.1 |
| Terminal | VT-style terminal with an on-screen keyboard; the same shell is reachable over USB | R.2 |
| Kernel | what is in BOOT (name, kernel version, build date, SHA-256, taken from a small manifest stored inside each image), the previous image kept for rollback, battery, storage, the main system's last kernel log from pstore | R.3 |
| Flash kernel | pick an image file from the root filesystem, the SD card or a USB upload; verify container and hash; write BOOT; read back and compare; keep the old image as "previous"; one tap to roll back | R.4 |
| Files | two-pane browser: root filesystem (read-only until confirmed), SD card, USB storage; copy, view text | R.5 |
| Backup | archive chosen directories and `/etc` to SD card or over USB; verify the archive; restore into a scratch directory | R.6 |
| Maintenance | filesystem check (read-only first), reboot to system / recovery / download mode, power off | R.7 |

Destructive entries (format, wipe, restore over live data) sit in a separate
"Danger" sub-menu, need a typed confirmation, and carry the label "untested on
this phone". Their code is exercised only against image files and loop devices
on the computer (`tests/`), never here.

The partitions the recovery is allowed to write are a fixed allow-list in the
program: BOOT, RECOVERY, and files inside USERDATA or on removable storage.
PIT, bootloader, EFS, TrustZone, modem and RPMB devices are not in the list and
cannot be selected.

## How to get there without losing the way back

1. **On the computer:** the UI runs against a framebuffer in a window (LVGL has
   an SDL back-end), so layout and logic are developed and unit-tested without
   the phone. Flashing, backup and destructive code is tested on image files.
2. **As a program on the running phone:** stop the desktop session, run the UI
   on the real screen and touch panel, restart the session. No slot is written.
3. **In BOOT, as a trial:** flash the recovery image to BOOT through the
   existing 3.18 flow and boot it as if it were the system. From there the way
   back is the same flow in reverse; RECOVERY is untouched, so today's fallback
   still exists.
4. **In RECOVERY:** only after step 3 has shown that the recovery can write
   BOOT and read it back, and that its USB shell and SSH work with a blank
   screen. From then on the two slots can each rewrite the other; Download Mode
   with the owner at the phone remains the last resort, as today.
5. **Update flow:** `tools/run-boot-update.sh` learns the new path (reboot to
   recovery, send image over USB networking, write, verify) and keeps the old
   Wi-Fi path while the vendor image still exists.

Each step is recorded in the wiki when it is reached; the wiki gets a
"Recovery" page (English and Turkish) at step 3.

## Owner's decisions (2026-10-10)

1. The recovery replaces the vendor 3.18 fallback in RECOVERY once step 3 has
   passed. The vendor image is kept as a file and can be written back.
2. The UI is in English and Turkish, switchable on the phone; English is the
   default.
3. The recovery should be able to use Wi-Fi (it reads the saved network from
   the root filesystem, read-only); USB stays the path that always works.

## Not in scope

Android-style "install zip", decryption of Android data, anything touching the
modem, EFS or the bootloader.
