# Debugging the recovery

The original console-only image produced a black screen. The current build adds a USB serial shell and a direct framebuffer heartbeat. See [usb-console.md](usb-console.md) for the new connection procedure. A blank screen alone remains inconclusive.

## What this build can prove

`make test` verifies the original image's exact round-trip, preservation of boot-critical bytes, the static AArch64 ELF, archive contents, checksum logic and flash guards. With `qemu-aarch64` installed it also runs BusyBox `ash`, checks `/init` syntax and confirms every linked applet exists. It does not execute `/init` on the host, emulate this Exynos board, or prove the phone boots. Do not run `sudo ramdisk/init` on the host.

The initial applet execution test caught that Alpine's static BusyBox has no `cttyhack`; the script now uses its verified `setsid -c` applet and a shell fallback. No Android dynamic linker is required. The kernel supports AArch64 and compatibility ARM32, but this userspace is genuinely ELF64 AArch64.

Useful read-only host checks:

```sh
make test
python3 tools/recovery.py verify
cmp original/OrangeFox-recovery.img build/original-roundtrip.img
sha256sum -c build/SHA256SUMS
tar -tvf build/recovery.tar
gzip -dc build/ramdisk.cpio.gz | cpio -itv
readelf -h -l ramdisk/bin/busybox
```

The tar must list exactly one regular `recovery.img`. The CPIO should contain root-owned `/init` and BusyBox, BusyBox symlinks, directories, and character nodes `console` (5:1), `null` (1:3), `kmsg` (1:11), `tty` (5:0). Those major/minor values are Linux character-device ABIs, not Samsung partition addresses.

## Console visibility is the first hardware limitation

The inspected kernel has `CONFIG_VT` disabled and `CONFIG_SERIAL_SAMSUNG_CONSOLE=y`. The image header contains no `console=` setting. The bootloader may add runtime settings; inspect `/proc/cmdline`, `/proc/consoles` and `/sys/class/tty/console/active` from a working recovery before relying on a UART. Do not guess pinouts, voltage levels, UART names, or baud rates.

The recovery prints `HELLO FROM BURAK'S J701F LINUX RECOVERY`, `uname`, version, command line and consoles to available console/kmsg channels. It writes `/tmp/stage1-ready` after initialization; this marker is in RAM and disappears on reboot. It prefers an existing character-device console reported by `/proc/consoles`, falling back to `/dev/console`. A console shell without a controlling terminal can lack job control. If no reachable console exists, lack of visible output is inconclusive.

Removing OrangeFox removes its GUI, Android init services and adbd. **This build uses USB serial, so `adb devices` still does not show a connection.** Run `python3 tools/usb-console.py` from a host terminal. The display helper independently attempts framebuffer output with text and an alternating bar. If both remain absent, boot is still unconfirmed; do not infer userspace success from Odin's transfer result.

## Symptoms and checks

| Symptom | Check |
| --- | --- |
| Odin rejects the image | Return to Download Mode. Check physical model, cable, permissions, exact recovery-only tar, unchanged original hash and image size. Do not add erase/repartition flags. |
| Samsung logo or blank screen | Confirm recovery boot route; the display helper may have failed, or boot may have failed earlier. Check for a USB serial connection independently. |
| `No working init found` / `Failed to execute /init` | Check `/init` mode, LF shebang, `/bin/sh` symlink, static ELF architecture, and the CPIO tree. |
| `Attempted to kill init` | PID 1 must stay alive. This script keeps an outer respawn loop instead of replacing PID 1 with a disposable interactive shell. |
| Shell immediately exits | Inspect available runtime consoles. `/dev/console` can open yet have no input source. The loop delays two seconds to avoid rapid respawns. |
| `mount devtmpfs` fails | Static archive device nodes remain. Proc/sysfs/devpts failures are logged without terminating PID 1. |
| `Exec format error` | Ensure the binary is AArch64 ELF64; inspect with `readelf`. Do not use Arch's host x86_64 BusyBox. |
| Applet/library missing | Run `scripts/test-busybox.sh`; OrangeFox's `/sbin/busybox` is dynamically linked and intentionally not copied. |
| Stock Android bootloops again | It may have booted BOOT rather than RECOVERY. Stock Android repair is outside this milestone. |

## Capture baseline runtime evidence while OrangeFox works

These ADB commands read runtime information only; they do not mount storage or write partitions. They require the known-good OrangeFox to be running, not Download Mode or this custom image, which uses USB serial instead of ADB:

```sh
adb devices
adb shell 'uname -a; cat /proc/cmdline; cat /proc/consoles; cat /proc/partitions'
adb shell 'cat /sys/class/tty/console/active; ls -l /dev/block/platform/*/by-name'
adb shell 'ls -l /sys/class/android_usb/android0; ls -l /sys/class/udc'
adb shell 'dmesg' > build/orangefox-dmesg.txt
```

The original fstab supplies a RECOVERY by-name path under `13540000.dwmmc0`; it is a reference from this image, not proof of the live partition map or size. The build and flash scripts do not resolve or write that block path.

Pstore is configured, including ramoops and pmsg, but `CONFIG_PSTORE_CONSOLE` is disabled. Do not assume normal `/dev/kmsg` messages survive reboot. Ramoops panic records depend on reserved memory and actual configuration. Inspect `/sys/fs/pstore` from a working recovery if already available; absence of a record is not proof that `/init` never ran. No persistent log partition is mounted. Runtime logs are in `/tmp/boot.log`, `/tmp/usb.log`, and `/tmp/display.log`, readable through the USB shell.

For restoration, use the RECOVERY-only restore procedure in the README. An OrangeFox restore replaces the recovery userspace again and does not recover this build's RAM logs. Keep host build reports/checksums alongside observations from each hardware attempt.
