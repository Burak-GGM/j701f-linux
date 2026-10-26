# 12. The real display driver

**Goal:** drive the panel ourselves instead of drawing into a picture the bootloader left behind.

## What was wrong with what worked

Since the first desktop (chapter 6) the screen had worked through a trick. Samsung's bootloader switches the panel on and shows its logo from a piece of memory; Linux can keep writing into that same memory and the picture changes. The kernel calls this a "simple framebuffer". It needs no driver for any of the display hardware.

It also has limits no tuning removes. The GPU renders a frame, and then the whole frame has to be **copied** into that memory - 54 to 56 frames per second at best. There is no signal for "the panel has finished showing the last frame", no way to switch the panel off, and brightness could only be faked by darkening the pixels.

## The chain

```text
DECON  →  DSIM  →  EA8061S
(display  (MIPI DSI  (the AMOLED
controller) transmitter) panel)
```

Mainline Linux has drivers for the first two blocks, written for other Exynos chips, and none for this panel. The panel driver was written from the start-up sequence in Samsung's source for this phone: nineteen commands, with tests on a computer that check every byte and every wait, and what happens when any one transfer fails.

## How to experiment on the only screen you have

A display driver that fails leaves a black screen, and this phone has no second screen and nobody watching it at night. The method that made the work possible was built before the driver was tried:

- **Nothing was flashed.** The display's device-tree nodes were added at run time as an overlay, loaded by a module, on top of the unchanged working image. A reset undoes everything.
- **A reset was guaranteed.** A supervisor program opens the hardware watchdog, starts the trial, and then deliberately stops feeding the watchdog while keeping it open. Whatever happens - success, hang, crash - the phone restarts into the working image within half a minute.
- **The guarantee was rehearsed first**, with a trial that changes nothing about the display, to prove that the reset really comes and the same system really returns.
- **Results were read, not seen.** The kernel's own display state, the panel's answer to a status command, the number of completed frame flips. Every report said "appearance unseen" until the owner had looked.

## What stood in the way

- **Timing numbers.** The shared DSI driver would have programmed the horizontal timing differently from what the bootloader had running (46/39/0 where the working link used 56/48/4). A phone-specific timing profile was added, off by default.
- **A check that was backwards.** The driver waits for the transmitter's clock generator to report that it is stable. That test was inverted and its interrupt masked, so the wait either timed out or passed for the wrong reason.
- **The order of two steps.** The panel was being sent its commands before the transmitter was ready to carry them. One line saying "prepare the transmitter first" was the last fix.

Then, in a trial nobody watched: the panel answered a status request, and 120 frames were flipped at 59.641 per second.

## From a trial to every morning

A passing trial is not a desktop. Three more steps followed, each again from RAM with the watchdog behind it:

1. **Plasma on the native driver.** The compositor now hands finished frames to the display controller without a copy: 59.5 to 59.8 frames per second, which is simply the panel's own rate.
2. **Brightness.** An AMOLED panel has no backlight; brightness is a register in the panel. The range was taken from Samsung's table.
3. **Screen off and on,** and waking from suspend.

Then the owner looked at the screen and confirmed picture, brightness and blanking. Only after that did the switch become part of every boot - still loaded from the root filesystem rather than built into the boot image, so the bootloader's framebuffer stays available as the way back: hold Volume Down while starting, and the phone stays on it.

One more fault appeared exactly here. The switch is guarded by a stamp file: if the phone resets before the desktop is up, the next boot skips the switch. The first version kept skipping on every boot after that, silently - and the very first ordinary reboot tripped it. A safety net that stays down without saying so is a fault of its own; the stamp now costs one boot.

## What to take from it

- Build the way back before the way forward, and rehearse it.
- On hardware nobody is watching, decide in advance what will count as evidence, and say plainly what has not been seen.
- Keep the old path alive next to the new one for as long as it costs nothing.

This part of the project was begun by Codex and finished by Claude. Reference: [Real display driver](../reference/display.md).
