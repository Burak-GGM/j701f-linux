# 4. First mainline boot

**Goal:** start a modern, unmodified-as-possible Linux kernel on the phone and reach the installed Alpine system with it.

## Why "mainline"

"Mainline" means the Linux kernel as published on kernel.org, as opposed to the heavily modified copy a phone vendor ships once and never updates. The vendor's 3.18 kernel works, but it can only do what Samsung built it to do. A mainline kernel brings the open GPU driver (Panfrost), current Wi-Fi and graphics stacks, and security fixes.

The Exynos 7870 is not a blank page upstream. A community project, **exynos7870-mainline**, has contributed the basics — clocks, pin control, the PMIC, USB, and device trees for a few sibling phones (Galaxy J6, J7 2016, A2 Core, On7). Our phone, the J701F, was not among them. So the task was: write a device tree for this phone, and find out what else is missing.

## Problem one: the bootloader will not start it

S-BOOT expects a kernel packaged in Samsung's way, with Samsung's device-tree table, and it passes information in a form a mainline kernel does not understand. Rather than fight that, the project put a small, well-understood program in between:

```text
S-BOOT → Android boot image → U-Boot → Linux
```

**U-Boot** is an open-source bootloader. Here it is not installed as the phone's bootloader — S-BOOT stays untouched. U-Boot is simply the "kernel" inside the Android image. S-BOOT starts it like any kernel; U-Boot then loads the real Linux kernel, device tree and initramfs from a bundle (a *FIT image*) embedded in its own binary, sets the kernel command line, and jumps.

The U-Boot build is patched for this phone (`kernel/diagnostic/j701f-embedded-ramboot.c`), and before any image is allowed near the phone it is run in the QEMU emulator to check that it really reaches the point where it hands over to Linux. Fifteen deliberately broken images are also tested to make sure the loader refuses them.

## Problem two: knowing what happened

A kernel that fails early prints its complaints to a serial port the phone does not expose. For a while every failed attempt looked the same: a black screen. Two things changed that:

- A **simple framebuffer** entry in the device tree. The bootloader leaves the display on and pointing at a region of memory (`0x67000000`, 720×1280). Telling the kernel about it gives a text console on the screen from the first second — the penguins and scrolling messages that later became a familiar sight.
- **ramoops**: a reserved piece of RAM where the kernel writes its log so the next boot can read it.

All these experiments were done in the `RECOVERY` slot while `BOOT` kept the working system from chapter 3.

## Problem three: USB did not appear

The kernel booted, but the PC saw no USB device. The cause was not in the USB driver at all. Between the SoC and the USB connector sits a small chip, the **S2MU005 MUIC**, that switches the data lines between USB, a factory UART and charger detection. The vendor kernel programs it; mainline has no driver for it, so the switch stayed open.

The fix was to do from a tiny program what the vendor driver does: write two registers over I²C (`CTRL1 = 0x13`, `SW_CTRL = 0x24`) from the initramfs before bringing up USB. The values were read from the phone under the vendor kernel first. After that the gadget appeared and the serial shell worked on the new kernel.

!!! tip "The lesson"
    When a mainline driver is "missing", it is often enough to find the two or three register writes that matter and do them by hand. A proper driver can come later.

## Storage and the handoff

Enabling the eMMC controller in the device tree made the phone's storage visible. The initramfs then repeated the loader logic from chapter 3: find `USERDATA` by its filesystem UUID, mount it, `switch_root`.

For the first time, `uname -r` inside the installed Alpine system reported a modern version instead of 3.18. The same root filesystem could now be started by either kernel: the vendor one from `BOOT`, the mainline one from `RECOVERY`.

## Trials, counted

It took nine numbered attempts in this stage, each photographed or logged, each changing one thing. Failed ones are recorded in `kernel/rejected-trials.json` with the reason. That file is as valuable as the working code: it stops the same dead end from being explored twice.

!!! info "Details in the repository"
    `docs/j701f-mainline.md` is the long-form log of this stage and every later one.
