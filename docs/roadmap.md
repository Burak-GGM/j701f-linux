# J701F roadmap

**Status: APPROVED by the owner on 2026-10-10** (written by Claude the same day),
with the owner's decisions worked in. It is the shared goal for Claude and Codex.

Starting point: BOOT holds `bl7` (Linux 7.1.13, Plasma Mobile, about 54 frames
per second through the bootloader framebuffer, software backlight, Wi-Fi through
NetworkManager). Details: `docs/coordination/STATE.md`, wiki `reference/`.

How to read the tables: **Done when** is the test that closes the item.
**Owner needed** means the item cannot be finished without the owner at the phone
(looking at the screen, pressing a key, listening).

## Standing rules

- No sound from the phone without a fresh yes from the owner.
- Display work may proceed without the owner watching (decision of 2026-10-10:
  "do it anyway; I will look now and then and write if something looks odd").
  Because nobody may be there to see a black screen, every display trial must
  return the phone to a working image by itself, and what the panel showed is
  recorded as "not seen" unless the owner reported it.
- Never write PIT, bootloader, EFS, TrustZone, modem or RPMB; no secrets in the
  repository or the wiki; `mfc_fw.bin` stays out of any public repository.
- Every change is measured before and after and written to the wiki (English and
  Turkish) and to the log in the same piece of work.
- Nothing leaves the computer: no patches, e-mails, pull requests, bug reports
  or uploads to any third party without a new, explicit decision by the owner.
- On the phone, project files live under `~/j701f/` only; staged images of earlier
  updates are deleted once a newer one is verified (owner's rule of 2026-10-10).
- Phone and kernel tree are shared through `tools/coord.sh`.
- Flashing: the owner has given both assistants full rights to flash kernel and
  recovery images (BOOT and RECOVERY slots) without asking (2026-10-10). The
  limits in the third rule above are unchanged.

## Stage 0: left over from the owner's first test

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| 0.1 | Screen rotation does not happen; no rotation lock in the quick settings | Turning the phone turns the screen the right way, touch follows, and a quick-settings tile switches automatic rotation on and off | Yes, to turn the phone. **State 2026-10-10:** sensor readings were frozen (fixed by polling), quick-settings tile available after the reboot, rotation by command works; owner confirmed it turns but upside down; mount matrix corrected through udev, waiting for his re-test **Confirmed by the owner on 2026-10-10: rotation works in all directions** (udev matrix `0, -1, 0; 1, 0, 0; 0, 0, -1`). Left: put the same matrix into the device tree. |
| 0.2 | Discover lists every package | The store shows applications only, or a better store is installed and is the default | A look at the result. **State 2026-10-10:** GNOME Software with the apk plugin installed next to Discover and showing applications only; installing through it not tried yet |
| 0.3 | ~~Black areas in Angelfish~~ | Closed: the owner confirmed on 2026-10-10 that they are gone | – |
| 0.4 | ~~Housekeeping on the phone~~ | Closed 2026-10-10: 64 old boot-update directories removed with the owner's agreement, everything else gathered under `~/j701f/`; new standing rule below | – |

## Stage 1: the display (largest remaining gain)

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| 1.1 | First trial of the native display driver (DECON + DSIM + EA8061S panel) | **Passed 2026-10-10**, RAM-only `native-bl9-05`: native bind, DCS answer `0x9c`, 120 flips at59.641Hz, native buffer and timing registers, automatic unchanged bl9/Plasma return. Physical appearance unseen. Initial transient PLL timeout remains to investigate before 1.2; daily path unchanged. Evidence: `build/kernel/display-runtime/runs/native-bl9-05/result.json` | Helpful, not required |
| 1.2 | Native driver as the daily display path: no per-frame copy, real vertical sync | Desktop runs on it; compositor at 60 frames per second in the same test that gives 54 today | Yes **Owner's note 2026-10-10 (low priority):** every 30-60 s while watching video a faint line / slight tearing / a brief black flash; probably not visible to our tests. Expected to belong to the copy-based display path this item replaces. |
| 1.3 | Real panel brightness (the panel's own dimming commands) | Brightness slider drives the panel; software backlight removed | Yes |
| 1.4 | Screen off / on (blanking), and the panel surviving suspend | Screen really goes dark and comes back, also after a suspend | Yes |
| 1.5 | Display IOMMU instead of physical addresses | Enabled without regressions (optional if 1.2 works without it) | No |

Fallback if 1.1 fails repeatedly: keep the bootloader framebuffer and continue
shaving the copy path (currently 54 frames per second).

## Stage 2: what a phone needs every day

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| 2.1 | Suspend in daily use: wake by power/home key without the 1.1 s start-up penalty found on 2026-10-10, automatic suspend when idle, alarms still fire | Phone sleeps by itself, wakes on a key and on an alarm; Angelfish start unchanged | Yes, to press keys |
| 2.2 | Battery life: measure drain awake/idle/asleep on battery; deeper CPU idle (works on cores 1–7, hangs with core 0) | Numbers in the wiki; idle state enabled only if it survives a long soak including core 0 or is safely limited | Yes, phone off the cable for hours |
| 2.3 | Charger: charge current/limit control, correct charger type, battery health reporting | Plasma shows correct charging state and time; optional charge limit works | Plug/unplug **State 2026-10-13:** current limits by cable type and by battery temperature, charging can be switched off and on, battery percentage corrected, battery temperature readable. An optional charge limit (`charge_limit=80` in `/etc/j701f-battery.conf`) is in the helper and tried on the phone. Open: a trial with a wall charger, the battery helper as a boot service (owner's yes). |
| 2.4 | Proper power-domain driver (today: all on at boot, one switched off by hand) | Unused blocks are off without hand-written register writes; video decoder survives | No |
| 2.5 | Sound, the rest: headphones, earpiece, headset microphone, jack detection by interrupt, the second microphone | Each path confirmed by ear | Yes, every step **Owner's note 2026-10-10 (low priority):** in a YouTube video in Angelfish the sound drops for a fraction of a second now and then, e.g. the last letter of a sentence is clipped. |
| 2.6 | Bluetooth: pairing, audio (A2DP), file transfer | A headset or speaker pairs and plays | Yes |
| 2.7 | Vibration and proximity confirmed (drivers load, never felt/seen) | Motor buzzes on a notification; proximity changes with a hand over it | Yes **State 2026-10-13:** the desktop could not vibrate at all - feedbackd was missing; installed, profile `quiet` (vibration only), motor supply seen switching during an event. Still to be felt by the owner. |
| 2.8 | USB: proper MUIC driver, host mode (OTG), charging-only versus data | A USB stick or keyboard works through an adapter; cable type reported correctly | Yes, adapter needed |
| 2.9 | GPS | A position fix in a maps application | Yes, near a window |
| 2.10 | Video: hardware decoding inside the browser; HEVC and MPEG-4 errors in the codec; the encoder | YouTube at 720p without dropped frames; the two codecs decode cleanly | A look **State 2026-10-10:** H.264 bit-exact; HEVC and MPEG-2 frames flagged (status 190) and not identical to software; MPEG-4 error 102, VP8 error 34; causes open. |
| 2.11 | Touch keys and their backlight, notification LED if present | Keys and lights behave as on Android | Yes |

## Stage 3: polish and optimisation

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| 3.1 | Application start-up (Angelfish 5.5 s, Settings 4.3 s, Calculator 6.5 s) | Each measurably faster, or shown to be at the floor for this processor | No **State 2026-10-13:** the dynamic loader alone takes 0.5-1.1 s per start on a warm cache (94-170 libraries), measured in isolation; that share is at the floor for this processor and distribution. A full profile shows the rest spread thin (QML engine 17 %, kernel memory handling 16 %, Qt Core 15 %, no function above 1 %): no hot spot to remove; shown to be at the floor short of rebuilding the distribution's libraries. Tables in the wiki's performance page. |
| 3.2 | Home screen and task switcher smoothness measured like the browser was | Frame statistics in the wiki; fixes where something stands out | A look |
| 3.3 | Background freezer refinements: do not stop applications that are downloading or expecting messages; show in the task switcher that an application is stopped | No missed message or broken download in a week of use | Use |
| 3.4 | On-screen keyboard: start-up memory (240 MB of GPU buffers at start), latency | Measured and reduced | Typing |
| 3.5 | Default applications and missing ones for daily use (gallery, files, maps, mail, a music player the owner likes) | Chosen with the owner and set as defaults | Choices |
| 3.6 | Updates: a safe way to update Alpine packages and to update the kernel image without a computer | One documented command or button; rollback proven | No **State 2026-10-10:** kernel image updates now go through the recovery with read-back and a kept previous image (`tools/run-recovery-update.sh`, still driven from the computer). **2026-10-13:** `tools/phone-update.sh` for Alpine packages: lists, upgrades the ordinary ones, holds the graphics/desktop/boot-critical ones back unless asked, records the installed versions first and runs the health check after; used once (four packages). No proven rollback for packages: the stable repository keeps no old versions; `tools/phone-backup.sh` is the safety net. Still from the computer. |
| 3.7 | Robustness: backup of the phone's configuration, a tested restore, the fallback system kept current | Restore rehearsed once | No **State 2026-10-13:** `tools/phone-backup.sh` archives the configuration, the start-up scripts, the modules and the user's settings to the SD card and rehearses the restore into an empty directory, comparing every file with the live one (1369 identical, none different). A restore onto an erased phone is written down as steps but, by the owner's rule, not rehearsed on this phone. |

## Stage R: a graphical recovery (requested by the owner on 2026-10-10)

Goal: what TWRP or OrangeFox is for Android, for this Linux phone. Today the
RECOVERY slot holds the vendor 3.18 kernel with a text terminal; it is the
fallback every boot update depends on, so the existing way in must keep working
at every step.

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| R.1 | Design and base: which kernel and userland the recovery runs on, how the touch UI is drawn (no desktop, a few MB), how it is built reproducibly and installed without losing the current fallback | Written design; a recovery image that boots to a touch menu and still offers today's USB serial shell and SSH | A look at the screen. **State 2026-10-10:** design written (`docs/recovery-design.md`, three questions open), the UI builds natively on the phone and ran on its real screen as an ordinary program (home, Power, Terminal, Files seen through the framebuffer; first tap after start is lost, to be fixed); the self-contained image `rec1` booted once from BOOT: home screen on the panel (after unbinding the text console by hand; fixed in the source), USB shell working, automatic hand-over to the system working. Owner's decisions: it replaces the vendor fallback once proven, Wi-Fi wanted, English + Turkish with English default UI now switches between English and Turkish (own font for the Turkish letters); the lost-first-tap defect traced to LVGL's touch reader and replaced. **Trial 2 (`rec2`) passed on the phone:** UI on the panel by itself, used by touch by the owner, Wi-Fi + SSH working. Next: install into RECOVERY. **Installed in RECOVERY on 2026-10-10 (`rec4`) on the owner's order; the vendor slot is kept as a file and `tools/restore-vendor-recovery.sh` writes it back.** |
| R.2 | Terminals: an on-screen terminal with keyboard, and the USB-accessible shell as now | Both usable; USB shell works with nothing on screen | Typing. **State 2026-10-10:** terminal page works on the computer build; not on the phone yet Hardware keys (volume = move, power/home = select) coded as a fallback for a dead touchscreen; untried on the phone. |
| R.3 | System information: which kernel image is in BOOT (name, version, hash, build date), slot state, battery, storage, last kernel log of the main system (pstore) | Shown on screen and over USB | A look. **State 2026-10-10:** Kernel page and `sysinfo.sh` work on the computer build Works in the booted recovery (trial 2). |
| R.4 | Kernel flashing from the recovery: choose an image file from storage or receive one over USB, verify it, write BOOT with read-back, keep the previous image for one-tap rollback | A known-good image is written and rolled back from the menu | Taps. **State 2026-10-10:** `flash-boot.sh` with rollback passes eight tests on image files; not in the UI, never run on a device **Done on hardware in trial 2:** the recovery wrote a 32 MiB image to BOOT with read-back and kept the previous one (through the script over USB; rollback and the touch path still to be exercised). `tools/run-recovery-update.sh` ran end to end from the installed recovery. |
| R.5 | File manager: browse the root filesystem and the SD card, copy to and from SD/USB, view text files and logs | Files copied both ways | Taps. **State 2026-10-10:** browse-and-select page on the computer build; no copy or view yet Later the same day: view-as-text and copy-to-SD added (computer build, tested); the installed system is mounted read-only without journal replay. `rec5`: the system partition is made read-only at device level before mounting (ext4 was deleting orphans on a "read-only" mount). |
| R.6 | Backup and restore of the user's configuration and chosen directories to SD card or over USB | A backup is taken and its contents verified; restore is exercised only on a scratch directory | Taps. **State 2026-10-10:** `backup.sh` passes four tests on temporary directories; not in the UI Later the same day: Backup page wired through `storage.sh` (backup to the SD card, verify newest), five more tests. **Trial 2:** 28 MB backup written to the SD card and verified from the booted recovery. |
| R.7 | Maintenance actions: filesystem check, reboot targets (system, recovery, download mode), power off | Each works from the menu | Taps. **State 2026-10-10:** Power page and `power.sh` (dry-run tested) on the computer build Later the same day: Maintenance page (read-only `e2fsck -n`, kernel and crash log); `e2fsck` still has to be added to the image. **Trial 2:** `e2fsck -n` now in the image and run on the real filesystem (2.7 s, nothing changed); Wi-Fi/SSH switch on this page. "Reboot into recovery" and the 240 s automatic boot seen working from the installed recovery; power off and download mode still untried. |

**Rule for this stage, set by the owner:** anything that would erase the
installed system or lose files (formatting or wiping partitions, factory reset,
restoring over live data, repartitioning) may be written, but is **never run or
tested on this phone**. Such functions stay behind an explicit confirmation, are
tested only against image files or loop devices on the computer, and are marked
"untested on hardware" in the UI and the wiki. PIT, bootloader, EFS, TrustZone,
modem and RPMB stay out of reach of the recovery entirely.

## Stage 4: larger and later

| # | Item | Done when | Owner needed |
| --- | --- | --- | --- |
| 4.1 | Camera, rear then front (sensor drivers, the Exynos imaging pipeline, libcamera) | A photo is taken in a camera application | Yes |
| 4.2 | Modem: calls, SMS, mobile data | Deferred by the owner on 2026-10-10 ("leave it for now"); not to be started without a new decision | Yes, SIM |
| 4.3 | FM radio | Deferred like 4.2 | Yes |
| 4.4 | Remaining sensors (magnetometer, gyroscope if fitted) and the features that need them (compass) | Readings exposed and used by an application | A look |
| 4.5 | Kernel maintenance: follow new stable kernels and reduce the local patch set. Patches may be cleaned up to kernel style locally (candidates: Exynos 7870 GPU frequency scaling, the btbcm address fix, the DSIM fixes, the MFC v10 clock and SysMMU handling, the S2MU005 charger, a reworked Panfrost shrinker fix). **Nothing is sent to kernel.org, a mailing list or any other third party** (owner's decision of 2026-10-10, correcting an earlier misunderstanding); sending upstream is the very last step of the whole roadmap and needs a new, explicit decision | Patch list shorter than today; cleaned series kept in the repository only. **2026-10-26:** `btbcm` and `s5p-mfc` fixes prepared for mainline in `kernel/upstream/`, not sent | Decision before anything leaves the computer |
| 4.6 | Publishing: clean public repository and wiki without firmware or secrets | Later, together with the owner; **do not create or publish a repository yet** (decision of 2026-10-10). **2026-10-26: the owner asked for the clean-up and publication** (public, GPL-2.0-only, coordination files and home-network details kept out); see the log | Yes |

## Suggested order and division of work

1. Stage 0 first (small, the owner just asked for it).
2. Stage 1 without waiting for the owner; everything in it depends on the
   result of 1.1.
3. Stage 2 items 2.1–2.4 and 2.10 can proceed while waiting for the owner;
   2.5–2.9 and 2.11 are collected into short sessions with the owner.
4. Stage 3 runs alongside, one measured item at a time.
5. Stage R after stage 0 and alongside stage 2: R.1–R.3 first, then R.4, since
   a better recovery makes every later kernel experiment safer.
6. Stage 4 only after stages 1 and 2 are substantially done.

Suggested split: Codex keeps the display (stage 1) and its tools; Claude takes
stages 0, 2, 3 and R; stage 4.1 (camera) is shared when it starts. Either may take
any item by claiming it on the coordination board.
