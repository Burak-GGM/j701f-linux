# USB serial, screen heartbeat and local terminal

**Hardware update:** `/init`, BusyBox, the USB shell and the automatic boot heartbeat are confirmed on the flashed phone. The original bar appeared green/orange. A RAM-only red/blue swap test produced blue/green, confirmed by the user. The latest rebuilt archive includes that correction and needs a RECOVERY reflash to retain it after restart. See [the recorded observations](hardware-status.md).

This is the second image, built after the console-only recovery produced a black screen. It keeps the original kernel, complete DTB table, header parameters and Samsung trailer. Its additional device interactions are volatile USB gadget settings, serial TTYs and display/backlight interfaces; it does not mount or write storage partitions.

## Heartbeat screen and local terminal

The following screen appears automatically on the flashed phone. The new archive also corrects its bar colors:

```text
BURAK LINUX
INIT IS RUNNING

CONNECT USB
SERIAL CONSOLE
```

The earlier diagnostic image shows a bar that changes between green and blue about once per second. The latest image starts the [local touchscreen terminal](ondevice-terminal.md) instead, retaining the heartbeat as a fallback. Changing output proves the display process continues to run after `/init` launched it. A static image proves it reached the drawing code at least once. This is a status screen, not an on-screen terminal or touchscreen UI.

The renderer queries the actual resolution, stride, visible offsets and RGB/alpha bitfields through the framebuffer API. It supports packed true-color 16/24/32-bit layouts and the measured Samsung visual-0 XRGB8888 inconsistency, unblanks the display, reapplies the queried current mode with `FBIOPUT_VSCREENINFO` and `FB_ACTIVATE_FORCE`, re-queries and validates the resulting layout, writes opaque pixels and requests scanout with `FBIOPAN_DISPLAY`. It refuses unsupported layouts. The launcher discovers framebuffer device numbers through sysfs and sets an existing backlight to one-third of its reported maximum. No framebuffer physical address, screen geometry, device major/minor, or vendor display ioctl is guessed.

The display driver might still require initialization beyond these interfaces. **A black screen does not invalidate a working USB shell.** Display and USB are launched as independent child processes, each with a RAM log.

## Build and flash the diagnostic image

RAM-only tests disappear on restart. Reflash the rebuilt recovery to make current-mode activation run automatically at boot. A reflash is not needed to rerun the RAM-only test below. `build/recovery.tar` contains the diagnostic build. The older console-only image was saved under `build/stage1-before-usb/`. The exact OrangeFox restore archive remains `build/OrangeFox-restore.tar`.

From the project directory, verify and list Download Mode devices (no writes):

```sh
make test
./tools/odin4 -l
./scripts/flash.sh
```

The next command **overwrites RECOVERY only**, using the single `recovery.img` member. It does not request BOOT, SYSTEM, DATA, PIT, bootloader, EFS, modem, TrustZone or RPMB writes. Replace `BBB/DDD` with the actual path Odin printed; add `sudo` only if host USB access requires it:

```sh
./scripts/flash.sh --device /dev/bus/usb/BBB/DDD --execute
```

The helper requires its existing typed confirmation. After flashing, enter **recovery** using your established device-button route. A boot into stock Android tests a different image. Wait up to 30 seconds, then reconnect the data USB cable if necessary.

## Connect from the Arch host

Run these commands in an interactive host terminal:

```sh
cd j701f-linux   # the repository root
python3 tools/usb-console.py --list
python3 tools/usb-console.py
```

The script identifies the USB serial string `J701F-LINUX-CONSOLE`, opens the matching `/dev/ttyACM*`, and sends Enter. Press Enter again if needed. You should see the greeting and `j701f-linux #` prompt. Exit the host terminal connection with **Ctrl+]**. If access is denied, run the connection command with `sudo`; no Python packages need installing.

If automatic identification fails but a new `/dev/ttyACM0` appeared for this phone, select that observed port explicitly:

```sh
python3 tools/usb-console.py --device /dev/ttyACM0
```

This is a **USB CDC ACM serial root shell**, not ADB. `adb devices` remaining empty is expected. The development shell has no password and is intended for your directly connected host.

Inside the phone shell, these commands establish boot progress and collect logs without writing storage:

```sh
cat /tmp/stage1-ready
uname -a
cat /proc/uptime
cat /proc/cmdline
cat /tmp/boot.log
cat /tmp/usb.log
cat /tmp/display.log
dmesg
```

Run `cat /proc/uptime` twice to confirm the system stays running. Typing `exit` ends the phone shell; its supervisor starts a fresh session, activated with Enter. `/tmp` logs and markers disappear on reboot.

## If the host has no serial port

Read-only host checks:

```sh
lsusb
ls -l /dev/ttyACM* /dev/serial/by-id/ 2>/dev/null
sudo dmesg | tail -60
```

The gadget reuses VID:PID **04e8:6860** extracted from the original OrangeFox USB configuration. The kernel may overwrite the product label with `SAMSUNG_Android`; that label does not mean stock Android booted. If USB enumerates with an ACM interface but no terminal appears, load the host's standard serial class driver (`sudo modprobe cdc_acm`) and reconnect. This loads a host driver and does not flash the phone.

If the heartbeat appears but USB does not, `/init` ran and USB setup needs debugging. If USB works but the screen is black, inspect `/tmp/display.log`. If neither appears, the evidence is still inconclusive: possibilities include failure before `/init`, recovery not selected, gadget/driver failure or cable issues. Return to the known-good OrangeFox using the README's RECOVERY-only restore procedure if needed; do not attempt repartitioning or early-bootloader changes.

## Read full framebuffer metadata without reflashing

Close the interactive USB console with Ctrl+], then run on the host:

```sh
make framebuffer-probe
python3 tools/usb-console.py --probe-framebuffer
```

This transfers a checksum-verified helper to a unique file under the phone's RAM-backed `/tmp`, runs it with `--info /dev/fb0`, and removes it. `--info` opens the device read-only and only queries framebuffer metadata; it does not mmap, draw, change mode, unblank, or pan. The host saves the report in `build/phone-framebuffer.txt`. Only one host terminal should use the serial port at a time.

The report includes dimensions, offsets, stride, allocation size, visual type, color bitfields and the exact validation failure. BusyBox `fbset` alone does not report all of those fields. Reconnect normally afterward with `python3 tools/usb-console.py`.

For a six-second visual test using the current helper, close other serial terminals and run:

```sh
make framebuffer-probe
python3 tools/usb-console.py --test-display
```

This uploads the helper into RAM, draws six alternating frames, and records the driver's results in `build/phone-display-test.txt`. It changes the screen temporarily without flashing. The final frame may remain visible after the test exits. Successful ioctl results must be checked against what the panel actually shows.

## Read panel power and driver logs

With other serial terminals closed, run:

```sh
python3 tools/usb-console.py --display-diagnostics
```

This reads framebuffer, backlight and LCD class attributes and filtered kernel messages, saving `build/phone-display-diagnostics.txt`. It does not change display settings. Interrupted serial operations now save partial output in `build/phone-display-interrupted.txt` and report a concise error.

The related Samsung driver prepares its window registers in `decon_set_par`; panning consumes those registers. The first activation test lost USB because the user unplugged the cable; the user subsequently clarified that BURAK LINUX did appear. A repeated activation test completed with USB connected, and the user confirmed text or the colored bar appeared again.

Current-mode activation is now included in normal boot and `--test-display`. `--test-display-activation` remains a compatible alias. `--probe-framebuffer` remains read-only and never activates the mode. The driver changed from visual 0 without alpha to truecolor visual 2 with an 8-bit alpha field at offset 24; the helper uses the new fields and writes opaque alpha after revalidating the layout. For the measured activated J701F format, red and blue are exchanged in a copy used only for rendering. The mode sent to the driver remains unchanged. The user confirmed that this produces blue/green instead of orange/green.

The explicit color test remains available:

```sh
make framebuffer-probe
python3 tools/usb-console.py --test-display-swap-rb
```

The correction is also automatic in the regular `--test-display` and the rebuilt startup helper for the measured format. It is applied once, including when explicitly requested. Display tests pause the flashed `/bin/fb-heartbeat` process briefly and resume it on script exit, so the running boot heartbeat cannot overwrite the temporary test. The old flashed image resumes its old colors after the six-second test; the new archive must be flashed to retain corrected colors at startup.

## Implementation evidence and limits

The embedded kernel config enables `CONFIG_USB_G_ANDROID`, `CONFIG_USB_F_ACM`, `CONFIG_USB_U_SERIAL` and Samsung composite behavior, with configfs disabled. The shipped kernel strings also reference ACM and `ttyGS`. The related [SIMPLE kernel USB source](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/SIMPLE-V1.0-PERMISSIVE/drivers/usb/gadget/android.c) describes the function `instances` attribute and legacy `functions`/`enable` interface. That source tag is a kernel-family reference, not a verified exact source match to the supplied July 2021 binary. Runtime function-directory discovery and read-back checks therefore remain mandatory.

The launcher uses the existing `f_acm` or `f_acm0` directory, enables one instance, checks the selected function, then discovers `ttyGS*` device numbers from live sysfs. It does not use a generic configfs recipe, guessed TTY major/minor, or borrowed Android adbd libraries.

Host tests cover USB setup in isolated filesystem fixtures, actual AArch64 BusyBox getty startup on a pseudo-terminal, required applets, static helper execution, and framebuffer layout/color/bounds with address/undefined-behavior sanitizers. The display preview is a host rendering. **USB enumeration, an interactive shell, and visible output from the RAM activation test are confirmed on the phone. Automatic display is confirmed on the previous image; the latest color correction has been confirmed in RAM and still needs a reflash/reboot check.**
