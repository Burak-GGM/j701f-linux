# 2. Linux in the recovery slot

**Goal:** make the phone run a program we wrote, and talk to it.

## An Android boot image is just three files glued together

The `RECOVERY` partition holds an *Android boot image*: a small header, a Linux kernel, a compressed **initramfs** (a tiny root filesystem that lives in RAM), and on this phone a table of device trees. The bootloader loads all of it into memory and jumps to the kernel. The kernel unpacks the initramfs and runs the file `/init` from it as the first process.

That gives the easiest possible entry point: **keep the kernel and device trees exactly as they are, and replace only the initramfs.** The kernel already knows how to drive this phone; we only change what it runs.

The project's first tools do exactly that. `tools/recovery.py` parses the OrangeFox image (its layout is documented in `docs/recovery-image-format.md`), and the build puts in a new initramfs that contains:

- a static **BusyBox** binary (one file that provides a shell and a hundred small Unix tools),
- an `/init` shell script that mounts `/proc`, `/sys` and `/dev`,
- and one line of text of our own.

The image is written to `RECOVERY` with Odin, the phone is started with Power + Home + Volume Up, and the kernel log says:

```text
HELLO FROM BURAK'S J701F LINUX RECOVERY
```

That line is the whole first milestone. It proves the chain works: our build, the flashing tool, the bootloader's acceptance of the image, and the kernel running our `/init`.

## Getting a shell over USB

A greeting nobody can see is not much use — the screen was still black. The quickest way to talk to the phone is to make it pretend to be a USB serial adapter. The vendor kernel supports Android's USB gadget framework, so `/init` enables an **ACM** function and starts a shell on it. On the PC a new device `/dev/ttyACM0` appears, and `tools/usb-console.py` opens it:

```text
$ uname -a
Linux (none) 3.18.140-SIMPLE-KERNEL_V1.0 ... aarch64
```

From this moment the phone can be explored from the inside: partition sizes, the kernel configuration, the live device tree, GPU voltages. Much of what later stages needed was collected through this shell.

## Making the screen work

The display turned out to be harder than the shell. The kernel offered a framebuffer, `/dev/fb0`, but drawing into it showed nothing. The investigation is a good example of how this project works:

1. Ask the phone what the framebuffer looks like (720×1280, 32 bits per pixel, a particular channel order) instead of assuming.
2. Notice that every call *succeeds* and the panel stays black — success codes are not proof.
3. Read the related vendor display driver, then test reapplying the current mode with `FBIOPUT_VSCREENINFO`. The driver normalised its metadata and the owner confirmed visible output.

Once the mode was activated, pixels appeared. A separate test exchanged red and blue in the renderer: the owner saw the intended blue/green bar instead of orange/green. On top of that the project built a small on-screen terminal with a touch keyboard, so the phone could be used without a PC, plus a power menu (reboot, Download Mode, power off).

## What this stage gave us

- A rescue environment that stays useful for the rest of the project.
- A safe way to look inside the phone.
- Confidence in the build → flash → boot loop.

It is still the *vendor's* kernel. The recovery image itself is flashed permanently, but its running root filesystem lives in RAM: shell changes and temporary uploads disappear on reboot. The next chapter adds a persistent root filesystem.

!!! info "Details in the repository"
    `docs/boot-chain.md`, `docs/recovery-image-format.md`, `docs/usb-console.md`, `docs/ondevice-terminal.md` and `docs/hardware-status.md` are the working notes from this stage.
