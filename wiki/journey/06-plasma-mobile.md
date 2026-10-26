# 6. Plasma Mobile

**Goal:** a touch-friendly graphical desktop, drawn by the GPU.

## From "a shell" to "a session"

Up to here the phone started a single shell script as its first process. A desktop needs more around it: something to start and supervise services, a way to tell which user sits at which screen, a login manager. On Alpine that means:

- **OpenRC**, the service manager,
- **elogind**, which tracks sessions and hands devices (the display, the touchscreen) to the logged-in user,
- **D-Bus** and **PipeWire**, the message bus and the audio/video server,
- **SDDM**, a login manager set to log in automatically,
- **Plasma Mobile** itself, with **KWin** as the Wayland compositor.

The original start script was kept as the first process, and OpenRC is started from it only when the phone is running the mainline kernel. That keeps the vendor-kernel fallback simple and unchanged.

## How pixels reach the screen

There is still no driver for the phone's real display controller. The screen works because the bootloader set it up and the kernel was told where the picture lives in memory (`simpledrm`). That is a "dumb" display: it can show a finished image but cannot render.

The GPU is the opposite: it can render but has no display output of its own. Mesa joins the two with a mechanism called **kmsro** — Panfrost draws each frame, and the result is copied to the simple display. KWin reports the renderer as `Mali-T830 MC1 (Panfrost)`, and animations are smooth.

The price of not having the real display driver: no brightness control, no way to truly switch the panel off, and a fixed refresh rate.

## Things that went wrong

Getting from "packages installed" to "a desktop you can touch" took an evening of small surprises. They are typical of this kind of work:

**A black screen after the Plasma logo.** The session manager needed **Xwayland** to be installed even though everything visible is Wayland. One package and one directory (`/tmp/.X11-unix`) fixed it.

**The phone "rebooted by itself".** It did not crash: one short press of the power button made elogind shut the system down, as it would on a PC. The power key is now ignored by elogind and left to Plasma.

**A benchmark showing 5 frames per second.** The screen had been blanked by power saving; the compositor was not presenting frames. With the screen awake the same test ran at 44 FPS with vertical sync and over 200 without.

**"The notification drawer does not open."** It did; the remote test for it was wrong. A real swipe — injected as touch events — opened it.

The last two are the same lesson: before fixing something, make sure the measurement is telling the truth.

## Working without touching the phone

Part of this stage was done while the owner was away from the phone. That required tools to see and operate the screen remotely:

- `tools/phone-screenshot.sh` wakes the display, unlocks the session, asks KWin for a screenshot and converts it to PNG on the PC.
- `tools/inject-swipe.py` and `tools/inject-key.py` write touch and key events into the kernel's input devices, so a gesture can be performed over SSH.

They are documented on the [tools](../reference/tools.md) page.

## Navigation keys

The phone has a physical Home button and two touch keys beside it. Home was mapped to the "Meta" key, which Plasma Mobile uses to return to the home screen. The touch keys came later, in the driver stages.

At the end of this chapter the phone showed a real desktop, opened a terminal, installed software from the network and could be used with a finger.
