# Userspace

## The installed system

| | |
| --- | --- |
| Distribution | Alpine Linux 3.24 (`main` and `community` repositories) |
| Root filesystem | ext4 on `USERDATA` (`mmcblk0p24`), about 10.9 GB, mounted by UUID |
| User | `burak-alpine`, with `sudo` |
| Init | A small script as PID 1, which starts OpenRC on the mainline kernel |
| Session | elogind, D-Bus, PipeWire + WirePlumber, SDDM with automatic login |
| Desktop | KDE Plasma Mobile 6.6, KWin on Wayland, Xwayland for the session manager |
| Graphics | Mesa 26.1 with Panfrost; the native display driver (`exynos-drm`) for scan-out, the bootloader's framebuffer (`simpledrm`) as fallback |
| Network | Wi-Fi through NetworkManager on the mainline kernel (so Plasma shows and manages it), with a fixed address from the router; `sshd`. The vendor kernel still uses the original `wpa_supplicant` script |

## Files this project installs on the phone

The sources are in `system/` in the repository.

| On the phone | Source | Role |
| --- | --- | --- |
| `/sbin/j701f-start` | `start` | PID 1. Mounts the RAM filesystems, enlarges `/tmp` to 256 MB, then follows `/etc/inittab` |
| `/etc/inittab` | `inittab` | Starts the pieces below |
| `/sbin/j701f-openrc` | `openrc-runlevel` | Runs an OpenRC runlevel with a time limit — only if OpenRC is installed |
| `/sbin/j701f-display` | `display-select` | Chooses between the desktop (mainline) and the framebuffer terminal (vendor kernel) |
| `/sbin/j701f-netguard` | `netguard` | No Wi-Fi address 300 s after boot → reboot into the recovery. Off since 2026-10-26 (`/etc/j701f-netguard-off`) |
| `/etc/local.d/j701f-gpufreq.start` | `gpufreq-limit` | 40 s after boot: GPU limit to 1001 MHz, CPU limit to 1586 MHz, guarded by a stamp file |
| `/etc/local.d/j701f-audio.start` | `audio-autoload` | Loads the audio modules, the video codec modules and the modules in `~/j701f-misc-modules/` (charger status), guarded by a stamp file |
| `/etc/udev/rules.d/60-j701f-video.rules` | `video-udev.rules` | Gives the video codec device nodes to the `video` group |
| `~/j701f-mfc-modules/load.sh` | `mfc-load` | Loads the video codec modules in order |
| `/etc/local.d/j701f-stamps.stop` | `stamps-stop` | Clears the stamp files on an orderly shutdown |
| `~/j701f-audio-modules/load.sh` | `audio-load` | Loads the six audio modules in order |
| `/etc/elogind/logind.conf.d/…`, `/etc/elogind/sleep.conf.d/10-j701f-nosleep.conf` | `elogind-powerkey.conf`, `elogind-nosleep.conf` | Power key is left to Plasma; suspend is disabled. The no-sleep file only works in `sleep.conf.d`: in `logind.conf.d` it is ignored and the phone suspends after 15 idle minutes with no key to wake it |
| `/etc/sddm.conf.d/…` | `sddm-autologin.conf` | Automatic login into the `plasma-mobile` session |
| `/etc/profile.d/…` | `session-profile.sh` | Session environment |
| `~/j701f-boot-swap/` | — | `reboot-recovery` and the backup of the original `BOOT` image |
| `/etc/fstab` (one line) | — | Mounts the SD card (`/dev/mmcblk2p1`, FAT) at `/media/sdcard` as the phone's user; `nofail`, so a missing card does not hold the boot |
| `~/j701f/boot-swap/reboot-recovery.sh` | `reboot-recovery.sh` | Restart into the recovery with clean filesystems: clears the stamp files, stops the desktop, remounts read-only, then calls `reboot-recovery` |
| `~/j701f/battery/j701f-battery` | `battery/` | Battery helper: gauge mode switch and charge current by temperature (see below); run by hand so far |
| `~/j701f/modules/misc/j701f_adc.ko` | `tools/kmod/j701f_adc.c` | Battery and board temperature (hwmon device `j701f_adc`); loaded with the other modules in that folder |
| `/etc/localtime`, `/etc/timezone` | `build-release.py --timezone` | Time zone; the release builder uses the build computer's zone unless told otherwise. Without it the phone shows UTC (both the old system and the first release lacked it) |
| `/usr/local/bin/j701f-flashlight`, app "Flashlight"; `/usr/local/bin/j701f-front-flash` | `flashlight/` | Two buttons for the rear and front flash LEDs (Plasma's flashlight button only drives the rear one); both go off when the app closes. `j701f-front-flash [on\|off\|toggle]` does the front one from a terminal |
| `~/.config/kglobalshortcutsrc` | `release/kglobalshortcutsrc` | Binds the recents touch key (`KEY_PROG1`, Qt "Launch (1)") to Plasma Mobile's task switcher; Plasma binds nothing to it by default. Takes effect at the next login |

## Graphics

KWin renders with Panfrost and presents through the native display driver, `exynos-drm`, without copying frames (through `simpledrm`, with a copy, when the phone has fallen back to the bootloader's framebuffer; `tools/phone-health.sh` says which). Check the renderer with:

```sh
# as the desktop user, inside the session environment
qdbus org.kde.KWin /KWin supportInformation | grep -i renderer
```

**Firefox** is no longer in the daily-use package set. It could not use the GPU here: Mesa's compiler for this GPU family produced bad code for Firefox's WebRender shaders, causing missing page regions and GPU job faults. A system-wide preference file forced software rendering when Firefox was installed.

**Angelfish**, Plasma Mobile's own browser (Chromium engine), renders pages on the GPU without faults and is the browser to prefer. Video inside Angelfish works: the owner watched a YouTube video with picture and sound (2026-10-10) and noted two small flaws, a sound drop-out of a fraction of a second now and then and an occasional brief flicker; neither has been looked into.

The owner's daily-use app set was trimmed on 2026-10-26. Angelfish, Dolphin, Koko, Plasma Camera, the terminals, clock, calculator, GNOME Software, VLC and mpv remain. Firefox, Pure Maps, Discover, Gwenview, Elisa, AudioTube, PlasmaTube, Kasts, KWeather, Wike and GNOME Chess were removed, together with unneeded dependencies. The experimental network toolbox was archived under `~/j701f/old/` and its exclusive packages removed. This was a package cleanup, not deletion of the owner's photos or browser data. See `system/apps/` for the reproducible package lists and `setup.sh`; its default is a preview, and pruning needs an explicit flag.

**Koko photo opening.** On this phone Koko 26.04.2 crashed when opening any image in the mobile Kirigami layout. A synthetic PNG reproduced the crash; a debugger showed it in Kirigami layout code. Starting Koko with `QT_QUICK_CONTROLS_MOBILE=false` kept that same image view open, with the photo visible. `system/apps/koko-wrapper` is installed as `/usr/local/bin/koko` so only Koko uses this layout; Plasma Mobile stays mobile. On 2026-10-26 the owner confirmed that a real photo opens from inside the gallery and Koko stays open.

**GNOME Software scrolling.** The owner reported slow scrolling in the app list. A repeatable ten-second swipe trial on the phone measured roughly 10 active display flips per second with the reliable `GSK_GPU_DISABLE=all` setting. Isolated GTK GPU-option trials found that `gradients` alone blacked about 19% of the overview and `occlusion` alone about 99%; the other options kept the overview visible. Leaving only these two options disabled (`GSK_GPU_DISABLE=gradients,occlusion`) kept the content visible after swipes, but measured about 12 flips/s with greater CPU use than the baseline. The reliable `all` setting was restored. These measurements are limited to this one view and trial; store scrolling remains an open performance issue.

**Core-app launch sample.** A silent cache-drop/warm-start trial on 2026-10-26 measured time until each process was CPU-quiet, not time until its window first appeared: Dolphin 4.5/3.0 s (cold/warm), Koko 7.0/5.3 s, Kalk 8.5/7.0 s, QMLKonsole 7.0/5.3 s and Plasma Settings 6.5/4.8 s. Koko and Kalk each used roughly 110-120 MiB of proportional memory in that trial. This identifies application start-up as further optimization work; it does not imply that every application was visually tested end to end.

**VLC** is the default video application. Its Qt 5 interface runs through Xwayland. It decodes in software. For a day it was set to use the hardware codec (`avcodec-codec=h264_v4l2m2m` in `~/.config/vlc/vlcrc`), and the measurements looked excellent - a third of one core, no late frame - because VLC was showing nothing: with that decoder VLC 3 receives one picture, reports "buffer deadlock prevented" and leaves the window black while the sound plays. The owner noticed; the setting was removed on 2026-10-10. The lesson is on the [lessons page](lessons.md): a low CPU figure is not a picture. `mpv` is the player that uses the hardware codec.

## Hardware video decoding

The Samsung video codec (MFC) is available as a V4L2 decoder once its modules are loaded:

```sh
sudo sh ~/j701f-mfc-modules/load.sh      # /dev/video0 decoder, /dev/video1 encoder
sudo ffmpeg -c:v h264_v4l2m2m -i ~/Videos/test720.mp4 -an -f null -
```

It needs Samsung's codec firmware as `/lib/firmware/s5p-mfc-v10.fw`; that file comes from the phone's own Samsung firmware package and must not be redistributed. The modules are loaded at boot by the same guarded script as the audio drivers, and members of the `video` group can use the device nodes. H.264 from 360p to 1080p decodes correctly. **mpv** is installed and uses the decoder by default (`/etc/mpv/mpv.conf`: `hwdec=v4l2m2m-copy`); VLC, which is still the default video application, and the browsers decode in software.

## Sound

The sound card is `J701F` with one playback and one capture device (the main microphone). PipeWire presents it as "Built-in Audio Stereo".

| Control | Meaning |
| --- | --- |
| `Speaker Volume` | Speaker amplifier gain, 0–8 (−6 dB to +2 dB). Capped below the chip's maximum because higher values distort |
| `SPK SPK On` | Route to the speaker (on by default) |
| `HP HP On`, `Headphone Volume` | Headphone path — written, untested |
| `EP EP On`, `Earphone Volume` | Earpiece path — written, untested |
| `DAC Gain` | Digital gain |
| `Headset Jack` (read-only) | Whether a headset is plugged in; also an input device `J701F Headset Jack` |
| `MIC1 Volume`, `MIC1 Boost Volume`, `ADC Gain` | Main microphone gain stages |
| `MIC1 MIC1 On`, `MIC2 MIC2 On`, `MIC3 MIC3 On` | Which microphone input is recorded (default: MIC1). MIC2 and MIC3 (headset) are not confirmed to work |

Only 48 kHz, 16-bit stereo is accepted by the hardware path; PipeWire converts everything else.

Loading or reloading the drivers by hand:

```sh
sudo sh ~/j701f-audio-modules/load.sh
```

## Where the project keeps its files on the phone

Everything the project puts into the home directory lives under `~/j701f/`: `boot-swap/` (the helper that reboots into the other slot, the saved vendor image), `boot-update/NAME/` (the image being installed), `modules/audio`, `modules/mfc`, `modules/misc` (kernel modules loaded at boot), `experiments/`, `recovery-build/`, `display-runtime/`, and `old/` (leftovers of the first stages). Nothing else is created next to the user's own folders, and staged images of earlier updates are deleted.

## Wi-Fi, rotation and other desktop services

- **Wi-Fi in the desktop.** `/sbin/j701f-wifi` used to run `wpa_supplicant` and a DHCP client by itself, which works but leaves Plasma believing there is no Wi-Fi. On the mainline kernel, when the file `/etc/j701f-wifi-nm` exists, the script starts NetworkManager instead; the saved network is `/etc/NetworkManager/system-connections/j701f-home.nmconnection`, and `/etc/NetworkManager/conf.d/j701f.conf` keeps the fixed MAC address. If NetworkManager has no address after 90 seconds, the script stops it and falls back to the old way for that boot. Deleting `/etc/j701f-wifi-nm` returns to the old way for good.
- **Screen rotation.** `iio-sensor-proxy` (in the default runlevel) reads the accelerometer; `qt6-qtsensors` lets KWin use it; the output's rotation policy is "always". After installing the package once, `udevadm trigger` was needed before the sensor was recognised. `/etc/udev/rules.d/81-j701f-accel.rules` (source `system/accel-udev.rules`) makes the service poll the sensor: its data-ready interrupt stops after a few hundred samples and the readings froze. The sensor's orientation (mount matrix) in the device tree was a mirror image, so the screen turned the wrong way; the owner found the right one by trying, and since the `accel1` image it is in the device tree itself.
- **An application store.** GNOME Software with the `apk` plugin is the sole installed graphical store. It shows applications with icons and descriptions from Alpine's AppStream catalogue in `/var/lib/swcatalog` (fetched by `alpine-appstream-downloader`, refreshed weekly by the tune script; the directory must be world-readable). GTK 4 applications need `GSK_RENDERER=gl` together with `GSK_GPU_DISABLE=all` on this GPU, set for the session in `~/.config/plasma-workspace/env/j701f-gtk.sh`: with GTK's default optimisations parts of the window stay black, and the software renderer (`cairo`) is correct but too slow to use comfortably.
- **Vibration.** Plasma Mobile asks a service called feedbackd for vibration (key presses, notifications). It was not installed, so the shell logged "feedbackd vibration failed" and the motor, whose driver had long been loaded, was never used by the desktop. Installed on 2026-10-13 (`feedbackd`, `feedbackd-device-themes`); its udev rule knows this motor's driver name and gives the logged-in user access. Its profile is set to `quiet` (`gsettings set org.sigxcpu.feedbackd profile quiet`): vibration only. In the default profile, `full`, the same events also ask for sounds, which are Plasma's business here. Checked without anyone touching the phone: a 150 ms feedback event switched the motor's supply on and off again, and so did two injected taps on a quick-settings tile - Plasma's own touch feedback - with no further failure lines in the session log. Whether it can be felt is for the owner to say.
- **polkit** is installed and running. Plasma's helpers for privileged actions (the backlight among them) do not work without it.
- **Music.** Elisa was removed from the daily-use profile. The owner's music files remain untouched; a music player can be added from the package repository when wanted.

## Memory

A 1.2 GB compressed swap device (zram) is set up at every boot by `/etc/local.d/j701f-tune.start`, together with a few kernel settings, and the `earlyoom` service ends the largest web renderer before the desktop can freeze. The browser engine is started with low-memory switches from `~/.config/plasma-workspace/env/j701f-webengine.sh`. Applications that stay in the background for five minutes are stopped and continue when activated (`j701f-freezer`, settings in `~/.config/j701f-freezer.conf`). What each setting does and what it bought is on the [performance page](performance.md).

## Known rough edges

- Restarting the desktop session cleanly requires stopping all of the user's session processes; restarting only KWin or SDDM leaves a half-started session.
- The vendor kernel is no longer in `RECOVERY`; the scripts that chose between desktop and text terminal by kernel are still installed and simply always choose the desktop.

## Who is the administrator

Polkit (the service that shows "Authentication required") treats members of the group `wheel` as administrators and otherwise asks for root's password. The phone's user is not in `wheel`, so the software store rejected his own, correct password. `/etc/polkit-1/rules.d/49-j701f.rules` (`system/polkit/49-j701f.rules` in the repository) names the user as the administrator and lets him install, remove and update packages from GNOME Software without a password while he is at the phone - he has password-less `sudo` anyway.

## Files over USB (MTP)

Plugged into a computer, the phone offers its home directory as an MTP device ("SM-J701F Linux"), next to the serial shell. The USB network function the initramfs still sets up - the way in before Wi-Fi worked, which made every computer show a new wired connection - is taken out of the gadget by the same start script since 2026-10-13 (`touch /etc/j701f-usb-net` keeps it). The program behind it is uMTP-Responder, built on the phone because Alpine does not package it; `system/usb-mtp/` in the repository holds its configuration and the script that adds the MTP function to the USB gadget at boot. Files copied from the computer belong to the phone's user. The whole home directory is visible, hidden folders included. When an SD card is in the slot at boot it appears as a second storage, "SD-card" (it is mounted at `/media/sdcard`; the start script adds it to the running MTP server, so without a card no empty storage is shown).

## Battery percentage, temperature and charging

**Percentage.** The fuel gauge in the S2MU005 counts the charge going in and out ("current mode") and drifts; on 2026-10-13 it showed 43 % on a battery the charger itself reported as full (4.35 V, charge current tapering). The vendor kernel corrects this by switching the chip to "voltage mode" near full and near empty, where the cell voltage is the better witness; the mainline driver only reads the chip. The battery helper `system/battery/j701f-battery` does the vendor's switch from user space, with the vendor's conditions, by writing one register (0x4A: 0x10 current, 0xFF voltage) when needed. With the chip in voltage mode the shown value climbed from 43 % to 91 % in a little over half an hour, toward the true value. The chip keeps the mode it was left in across a reboot.

**Temperature.** `j701f_adc.ko` reads the battery pack's thermistor and a thermistor on the board through the SoC's ADC and shows them as a hwmon device named `j701f_adc` (`temp1` battery, `temp2` board), converted with the factory device tree's tables. The mainline device tree does not describe this ADC and the kernel's own Exynos ADC driver does not work with it (its conversions time out; the vendor's variant is initialised differently and keeps its result elsewhere), so the module brings a small device-tree overlay and its own polled driver. `BOOT` is not touched.

**Charging speed.** The charger driver sets the input limit and the charge current by cable type every time the type changes: computer port 500/450 mA, charging port 1000/1000 mA, wall charger 1200/1000 mA. Both can be read and written in `/sys/class/power_supply/s2mu005-charger/` (`input_current_limit`, `constant_charge_current`, in µA; capped at 1550 and 1500 mA); a written value holds until the cable type changes. Module parameters `dcp_input_ma`, `dcp_charge_ma` and `auto_limits` change the policy. On top of that the battery helper uses the temperature: with a wall charger and the battery between 15 and 41 °C it raises the limits to 1550/1500 mA (the vendor charges with up to 2150 mA); below 15 °C it allows 700 mA, below 5 °C or above 41 °C 450 mA, and above 50 °C or below 0 °C it switches charging off until the battery is back below 45 °C or above 5 °C. Without a temperature reading it changes nothing.

**Stopping the charge by hand.** `charge_behaviour` in the same folder takes `inhibit-charge` and `auto`. Inhibited, the phone runs from the cable and the battery rests (measured: battery current falls from about 120 mA to 1 mA, status "Not charging"); `auto` resumes. The bootloader switches charging on again at every boot.

**Charge limit.** A file `/etc/j701f-battery.conf` with the line `charge_limit=80` (any value from 50 to 99) makes the helper stop charging at that percentage and start again five points below it; the phone runs from the cable in between. Without the file there is no limit. Tried on the phone with a temporary file: at 100 % the helper switched charging off within one round ("Not charging", battery current about zero).

**State.** The helper needs `i2c-tools`. It is on the phone in `~/j701f/battery/` with an OpenRC service file, but **it is not installed as a boot service yet**; until then it runs only when started by hand after a boot (`sudo sh ~/j701f/battery/j701f-battery &`). `sudo sh ~/j701f/battery/install.sh` on the phone installs the service. Its decisions are covered by `tests/test_battery_daemon.py` against a simulated system; the wall-charger path has not been exercised with a real wall charger.

**Clock.** The kernel sets the system clock from the hardware clock at boot, but nothing ever wrote the hardware clock, so every boot began in the year 2000 until Wi-Fi brought the time. The Wi-Fi start script now writes the hardware clock after each successful time fetch.

## Backup and rebuilding the phone

`tools/phone-backup.sh` archives, from the running system, what makes this phone the J701F port rather than a plain Alpine installation: `/etc` (which includes the list of installed packages, `/etc/apk/world`), `/sbin` and `/usr/local` (the project's start-up scripts and the MTP server), the user's `.config` and `.local/share`, and from `~/j701f` the kernel modules, the battery helper and the helpers for restarting into the recovery. The archive goes to the SD card (`j701f-backups/`), next to the ones the recovery's Backup page makes - both use the same script, `recovery/scripts/backup.sh`, and can read each other's archives. It holds secrets (the Wi-Fi key, password hashes, SSH host keys), so it stays on the card and is never copied into the repository.

After making the archive the tool **rehearses the restore**: it unpacks the archive into an empty directory on the phone and compares every file with the live one - content, type, owner and mode - then removes the directory. On 2026-10-13: 35 MB, 1693 entries, 1369 files identical, none different. Nothing is ever unpacked over the running system.

Putting a lost system back is a manual job, and it has not been rehearsed end to end because that would mean erasing this phone:

1. Install Alpine and boot it with the project's `BOOT` image (the images are in `build/kernel/` on the computer; the recovery can write one).
2. Unpack the archive into an empty directory (`backup.sh restore`), then copy `etc/apk/world` into place and let `apk` install the packages it lists.
3. Copy the rest of the archive over the new system.
4. The kernel modules in `~/j701f/modules` only load on the kernel they were built for: if `BOOT` holds a different kernel, rebuild them (see [Build and install](tools.md)).

## Flashlight

The rear and the front LED are two ordinary LED devices: `/sys/class/leds/white:flash` (rear, brightness 0-6, 25 mA per step) and `/sys/class/leds/white:front-flash` (front, 0-2). Writing a number switches the light on, 0 switches it off; the desktop user may write them. They are driven by the charger chip, so the code lives in the project's charger driver. Currents are kept well below what the vendor allows. Confirmed by the owner on 2026-10-10: both LEDs light, and the rear one gets brighter with each of its six steps. Plasma's flashlight tile in the quick settings works with it (checked 2026-10-13 with injected taps and the chip's enable register: the tile switches the rear LED to its full step 6, 150 mA, and off again). The tile looks for an LED whose name ends in `:flash` or `:torch`, which is why only the rear one is found, and writes through its own small privileged helper.
