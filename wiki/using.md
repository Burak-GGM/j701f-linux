# Using the phone

A short guide for the person holding the phone. Everything here is described in more detail in the reference pages; this page only says what to do.

## Starting, and when it does not start

| What | How |
| --- | --- |
| Normal start | Power key. The desktop appears about half a minute after the kernel starts |
| Recovery | Hold **Power + Home + Volume Up** while switching on. Tiles for writing or rolling back a kernel image, files, backup, a terminal. Left alone for four minutes it starts the normal system |
| The screen stays black or looks wrong after an update | Hold **Volume Down** while the phone starts: it then stays on the simple display path the bootloader set up |
| Recovery from the running system | `~/j701f/boot-swap/reboot-recovery.sh --execute` in a terminal |

In the recovery the volume keys move, Power or Home selects, and the button at the top right switches between English and Turkish.

## Files

- **From a computer:** plug in the USB cable. The phone appears as "SM-J701F Linux" with two storages, the home folder ("J701F") and the SD card ("SD-card").
- **SD card:** mounted at `/media/sdcard` when it is in the slot at start-up; in the file manager it is under Places.
- **Photographs** from the camera application are in `Pictures` in the home folder.

## Battery and charging

- The percentage is kept honest by a small helper. Until it is installed as a service it has to be started once after each start of the phone; `sudo sh ~/j701f/battery/install.sh` installs it for good.
- **A wall charger** charges faster than a computer port (up to 1.5 A against 0.45 A) once the helper runs; without it, 1 A. This is written and tested against a simulated system but has not yet been tried with a real wall charger.
- **Charge limit:** to keep the battery between 75 and 80 % when the phone lives on a cable, create `/etc/j701f-battery.conf` containing the line `charge_limit=80`. Delete the file to charge fully again.
- **Stop charging now:** `echo inhibit-charge | sudo tee /sys/class/power_supply/s2mu005-charger/charge_behaviour`; `auto` instead of `inhibit-charge` resumes. A restart of the phone also resumes.

## Light, camera, browser

- **Flashlight:** the flashlight tile in the quick settings (pull the top panel down) switches the rear light on at full strength and off. For other strengths or the front light: `echo 3 > /sys/class/leds/white:flash/brightness` (rear, 0 to 6), `echo 1 > /sys/class/leds/white:front-flash/brightness` (front, 0 to 2); `0` switches off.
- **Camera:** Plasma Camera shows a preview, takes photographs and switches between the two cameras. Video recording does not work yet, and there is no autofocus.
- **Browser:** use Angelfish. It draws with the graphics chip; Firefox works but draws in software and is slower.
- **Video files:** `mpv` is set up to use the hardware video decoder.

## Looking after it

| Task | Where |
| --- | --- |
| Backup of settings to the SD card | Recovery → Backup, or `tools/phone-backup.sh` from the computer (also rehearses the restore) |
| Is everything all right? | `tools/phone-health.sh` from the computer: one line per check |
| Package updates | `tools/phone-update.sh` from the computer (shows first; `--apply` to install) |
| A new kernel image | `tools/run-recovery-update.sh NAME` from the computer, or the Kernel tile in the recovery |

## What it cannot do

No calls, SMS or mobile data (the modem is not driven). No GPS. No automatic sleep: the screen switches off, the phone stays awake. No automatic brightness (the phone has no light sensor). Headphones, earpiece and Bluetooth audio are not confirmed.
