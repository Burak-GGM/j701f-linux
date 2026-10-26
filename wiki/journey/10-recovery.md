# 10. A recovery of our own

**Goal:** a small second system on the phone that can repair the first one - by touch, without a computer if need be.

## Why the old safety net had to go

From chapter 5 on, the phone had two systems: the new one in the `BOOT` slot and Samsung's 3.18 kernel with a text terminal in the `RECOVERY` slot. Every kernel update went through that old system: restart into it, write `BOOT` from there, restart back. It worked, and it was the reason the project could afford mistakes.

It was also a dead end. It could not use the new drivers, its only interface was a text console, and anyone without the project's scripts on a computer could do nothing with it. The owner asked for what TWRP or OrangeFox is on Android: tiles on a screen, in English and Turkish.

## What it is made of

- The **same mainline kernel** as the main system. There is nothing separate to maintain.
- An **initramfs of a few megabytes**, the same one the main system boots through; started from the `RECOVERY` slot it stays in RAM instead of handing over.
- **One statically linked program** that draws the interface with the LVGL library, straight onto the framebuffer. No desktop, no display server.
- **Shell scripts** for everything that touches storage - writing `BOOT`, backing up, mounting - kept outside the interface so that they can be tested on image files on a computer.

It has to fit in 38 MiB and must need nothing from the installed system, because its whole purpose is to work when that system does not.

## The rule that shaped it

The owner set one rule early: functions that could erase the installed system or lose files may be written, but are never run or tried on this phone. The design follows from it.

- The installed system is mounted read-only - and that turned out to need more than the word "read-only". The kernel log showed ext4 quietly deleting an orphaned file during such a mount. The partition is now switched to read-only at the block-device level first, and the journal is not replayed.
- The writer can write the `BOOT` slot and nothing else. Partition table, bootloader, modem and the rest cannot even be selected.
- Before writing, it keeps the old contents; after writing, it reads back and compares; one tap rolls back.
- Backups go to the SD card only, and a restore only unpacks into an empty directory.
- If nobody touches it for four minutes, it starts the installed system by itself. A recovery that waits for ever is a phone that looks dead.

## Trials

It took eight images to get from "draws a screen" to "installed".

- **The console kept drawing over the interface.** The kernel's text console and the program both owned the framebuffer; the console has to be detached first.
- **Short taps vanished.** The library's touch reader reported only the state after it had emptied the event queue, so a quick press-and-release looked like nothing. The program now reads the touchscreen itself.
- **A refusal without a message.** Keeping the old 32 MiB `BOOT` contents for a rollback did not fit in the 8 MiB RAM disk. The writer refused before touching `BOOT` - the right behaviour - but said nothing.
- **Wi-Fi that "never connected".** The helper that asks for the connection state creates a socket in `/tmp`, which did not exist as a writable place.
- **The Home key did nothing.** The owner found that; on this board it reports itself as a key nobody expected.
- **The language did not survive a restart.** The recovery has no writable filesystem and may not write to the installed system, so it keeps its settings in one 512-byte block at the end of its own slot.

Wi-Fi deserves a note. The recovery has the Wi-Fi driver, but not the programs or the saved network: it **borrows** them, read-only, from the installed system. That keeps secrets out of the image. If the installed system's files are unreadable there is no Wi-Fi - and the USB serial shell, which depends on nothing, is still there.

## The moment of replacing the net

Replacing the fallback with something new is the one step where both could be lost. It was done in this order:

1. The new recovery ran from `BOOT` first, with the old system still in `RECOVERY`, until it had written, verified and rolled back a kernel image on the real phone.
2. The whole old `RECOVERY` slot was saved as a file, on the phone and on the computer, with a script that writes it back.
3. Only then was the new recovery written into `RECOVERY`.

Since then every kernel update goes through it: the computer stages an image, the phone restarts into the recovery, the recovery writes and verifies `BOOT`, the phone restarts into the new kernel. The same thing can be done with a finger.

## What to take from it

- Build the rescue system from the same parts as the main one. A second kernel is a second project.
- Put the dangerous operations in small scripts with refusals, and test the refusals on files.
- "Read-only" is a promise of the layer you asked, not of the layers below it.
- Do not remove the old safety net until the new one has caught you at least once.

Reference: [Graphical recovery](../reference/recovery.md).
