# J701F roadmap 2 (proposed 2026-10-10, evening)

Written by Claude from the owner's feedback after trying the phone. **Status:
approved 2026-10-10 ("continue from the new roadmap, full authority"); MTP for C.1 not objected to.** It replaces nothing: items of
`docs/roadmap.md` that are still open are referred to by their numbers there.

The standing rules of `docs/roadmap.md` stay in force unchanged (no sound from
the phone without a fresh yes; never touch PIT, bootloader, EFS, TrustZone,
modem, RPMB; nothing leaves the computer; project files on the phone under
`~/j701f/`; wiki and log with every change; no passwords or other secrets in
the repository).

New since the first roadmap: Codex is away for a long time, so **Claude takes
over the display work**; the graphical recovery is installed and kernel images
are written through it (`tools/run-recovery-update.sh`).

Order: A first (things that worked and no longer do), then B (the owner:
"the display is important"), C and D in between whenever B waits for a build
or a trial, E alongside D, F as time allows.

## A. Broken or regressed - first

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| A.1 | VLC plays only the sound of the test videos in `~/Videos` that used to play with picture | The same files play with picture again in VLC; the cause (hardware decoder setting, decoder module, or the kernel image in BOOT) is named in the log | A look at the end **Done 2026-10-10:** my own hardware-decoder setting made VLC 3 show black; removed, picture verified by framebuffer dump. |
| A.2 | GNOME Software: "Authentication required" rejects the correct password | Installing an application through the store works with the user's password | Types the password once **Fixed 2026-10-10, owner to confirm:** polkit was asking for root's password; rule installed, store actions need no password now. **Parked by the owner 2026-10-10** ("pause the store"): he could not try it because the store shows only installed applications at the moment. |
| A.3 | The password dialog is very slow to type in | Typing in it is as responsive as in other dialogs, or the cause is named | A look **Open:** not explained; the dialog no longer appears for the store. Could not be reproduced from SSH; in the application search field the lag while typing is plasmashell searching on every letter (0.5 s of CPU each), not the keyboard. |
| A.4 | Video decoder patch that is written but unbuilt (HEVC / MPEG-2 lose their first key frame); MPEG-4 and VP8 do not start (roadmap 2.10) | Patch built and measured against software decoding; the other two explained or fixed | No **Done 2026-10-10:** HEVC and VP8 identical to software, MPEG-2 correct; MPEG-4 part 2 explained (headers outside the stream), left to software. |

## B. Display - taken over from Codex (roadmap 1.2 to 1.5)

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| B.1 | Take stock of Codex's work: what is in BOOT (`dsimpll2`), his trial tooling, open findings (panel answer `0x1c` instead of `0x9c`, PRIME import error), and port his update/watchdog flows to the new recovery | A written summary in the log; his trials can be repeated from this side | No **Done 2026-10-10:** his RAM-only trials run from this side; two small fixes to his tools. |
| B.2 | Plasma on the native display driver (DECON + DSIM + panel) instead of the copied framebuffer | Desktop runs on it day to day; 60 frames per second in the test that gives 55 today; **the faint line / tearing / brief black flash the owner sees every 30-60 s is gone** (believed, not proven, to come from the unsynchronised copy) | Yes, to look **State 2026-10-10:** Plasma ran on the native driver in three watchdog trials, 59.6 frames per second against 55; appearance unseen. Boot-time switch written, **not installed** (needs the owner's yes). **Later the same day:** boot service installed with the owner's permission; one "once" boot on the native driver succeeded and was left on screen for him to judge. **DONE 2026-10-10: the owner confirmed the picture ("Doğru"); the boot service is set to `always`.** |
| B.3 | Real panel brightness | Slider drives the panel; software backlight removed | Yes **State 2026-10-10:** backlight device on the panel driver (AOR register), writes accepted in a trial; real dimming unseen. **Confirmed by the owner 2026-10-10** as part of the same answer. |
| B.4 | Screen really off and on again, also across suspend | Dark when off, back when woken | Yes **State 2026-10-10:** one off/on cycle through the compositor passed in a trial; suspend not tried. **Confirmed by the owner 2026-10-10** for screen off/on; across suspend still untried. Suspend/resume with an RTC alarm passed on the native display (kernel state and frame rate; panel unseen). |
| B.5 | Display IOMMU (optional if B.2 works without) | Enabled without regressions | No |

Every trial returns to a working image by itself, as before; the recovery is
now the way back if a display image does not start.

## C. USB: the computer sees the phone's storage

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| C.1 | Choose the method. Proposal: MTP (the phone stays usable while connected and nothing has to be unmounted), offering the home directory and the SD card; the existing USB serial shell stays | Decision recorded | Agrees or picks otherwise **Decided 2026-10-10:** MTP. |
| C.2 | Implement on the installed system | The owner's computer shows the phone and files copy both ways | Plugs it in **Done 2026-10-10 from this computer:** home directory listed, a file written and read back. The owner's own look still welcome. |
| C.3 | The same from the recovery (read-only view of the system, read-write SD card) | Works with the recovery on screen | Plugs it in **Done 2026-10-10 (`rec7`):** system home read-only and SD card read-write, checked from this computer. |

## D. General speed

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| D.1 | Measure first: start-up of a fixed set of applications (Angelfish, Settings, Calculator, Software, the new ones from E), split into process start, toolkit start and first frame | A table in the wiki to compare against | No **First table 2026-10-10** (log): Qt applications use 4-7 s of CPU time to start, warm barely better than cold; GNOME Software 21 s; three applications never stop drawing. |
| D.2 | Application start-up (roadmap 3.1) | Each measurably faster, or shown to be at the floor for this processor | A look **State 2026-10-10:** one profile of kalk: a third of its start is the C library's dynamic loader, most of the rest the QML engine; no quick fix found. |
| D.3 | GTK applications (Software) stutter while Qt ones do not | The cause named (renderer, compositor path, or the application); smoother, or replaced by something better suited | A look **State 2026-10-10:** start-up: not the renderer - about 22 s of CPU loading the catalogue with every renderer. Stutter while using it: not measured yet. The 22 s was measured in that slowed boot: to be repeated. **Parked by the owner 2026-10-10**; no background instance wanted. |
| D.4 | Home screen, task switcher, keyboard (roadmap 3.2, 3.4) | Frame figures in the wiki; fixes where something stands out | A look **State 2026-10-10:** top panel 52-54 frames per second while moving; application drawer and page swipe only 21-25; keyboard and task switcher not measured; cause of the slow drawer open. **Corrected the same evening:** the slow drawer was a stale safety stamp holding the GPU at 343 MHz for that boot; with the limits restored the drawer animates at 55-60. Guard changed to cost one boot only. Task switcher: 10-20 frames per second while the finger drags it, 60 once it animates alone; keyboard could not be triggered by injection. |

## E. Applications for a phone

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| E.1 | Install a small set of light, touch-friendly applications for trying out: a YouTube Music client, gallery, file manager, clock/alarms, weather, calculator, notes, podcasts, maps - chosen from what Alpine packages for Plasma Mobile | Installed, each started once and its start time and memory noted (feeds D.1) | Tries them **State 2026-10-10:** audiotube, koko, kweather, kasts, marknote, pure-maps installed; not measured or started yet. Marknote removed again (its Alpine package does not start). Measured in D.1. |
| E.2 | Keep what the owner likes, remove the rest, set defaults (roadmap 3.5) | Done with the owner | Choices **Decided 2026-10-10:** all five stay (AudioTube, Koko, KWeather, Kasts, Pure Maps). Defaults not set yet. |

## F. Carried over, lower priority

| # | Item | Note |
| --- | --- | --- |
| F.1 | Sound drops for a fraction of a second in browser video | Owner: sound is not a priority now |
| F.2 | Rotation matrix into the device tree | Works through a udev rule today **Done 2026-10-10:** in the device tree, BOOT image `accel1` installed through the recovery; udev override removed. |
| F.3 | Recovery: flashing / rollback / copy by tapping, power off, download mode, behaviour with a damaged system; language kept across reboots | Untested or missing **2026-10-10:** language now kept across reboots (settings block in the RECOVERY slot, `rec8`; verified in a boot of the recovery); the tapping tests remain. **Tapping tests 2026-10-10:** copy to SD, flash and rollback by injected taps all verified; power off and download mode left for the owner. |
| F.4 | Everything else still open in `docs/roadmap.md` (suspend in daily use, battery, charger, Bluetooth, sensors, OTG, GPS, camera; modem and FM radio deferred by the owner; publishing later) | **2026-10-13 (free-work session):** battery percentage corrected (gauge mode switch), battery temperature readable, charge current by cable type and temperature, charging can be switched off, SD card mounted and offered over MTP, time zone and hardware clock fixed, clean restart into the recovery. Waiting for the owner: a wall-charger trial and the yes for the battery helper as a boot service. Camera: first version works (photographs), paused by the owner. The rest unchanged. |
