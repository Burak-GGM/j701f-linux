# Boot chain and safety nets

## From power button to desktop

```text
S-BOOT (Samsung, untouched)
  └─ loads the Android boot image in BOOT
       └─ "kernel" = patched U-Boot v2026.01, with an embedded FIT image
            └─ FIT: gzip-compressed Linux Image + device tree + initramfs
                 └─ Linux 7.1.13
                      └─ initramfs /init
                           ├─ sets the USB switch (MUIC) over I²C
                           ├─ starts the USB gadget (serial + network)
                           └─ alpine-handoff: find USERDATA by UUID, check it with e2fsck, mount, switch_root
                                └─ /sbin/j701f-start (PID 1)
                                     └─ OpenRC → elogind, D-Bus, sshd, Wi-Fi, SDDM
                                          └─ Plasma Mobile (KWin, Wayland)
```

A few details that are easy to miss:

- The Android image has an **empty ramdisk** and a **stub device-tree table**. S-BOOT insists on both being present; neither is used.
- The **kernel command line is set inside U-Boot** (`kernel/diagnostic/j701f-embedded-ramboot.c`). The `bootargs` in the device tree source are not what the kernel receives.
- The command line keeps `clk_ignore_unused` and `regulator_ignore_unused`. The display only works because the bootloader's clocks and supplies are left running; without those two options the kernel would switch them off.

## Two slots

| Slot | Started by | Contents |
| --- | --- | --- |
| `BOOT` | Normal power-on | Current mainline image |
| `RECOVERY` | Power + Home + Volume Up | Since 2026-10-10: the project's [graphical recovery](recovery.md) (its own kernel and initramfs). Before that: the vendor 3.18 kernel starting the same Alpine root |

The recovery is a separate small system; it can hand over to the installed one ("Boot system", or by itself after 240 seconds without anyone using it).

Moving between them without touching the phone:

| From | To | How |
| --- | --- | --- |
| System | Recovery | `sudo ~/j701f/boot-swap/reboot-recovery --execute` |
| Recovery | System | "Boot system" or Power → "Reboot into the system" on screen; `reboot -f` in its USB shell |

## Installing a new kernel image

New images are always written **from the recovery**, never from the running system:

1. `tools/build-mainline-image.sh NAME kernel/dts/BOARD.dts` builds and verifies the image and prepares an update directory.
2. `tools/run-recovery-update.sh NAME` copies the image to the phone, reboots it into the recovery, logs in there over Wi-Fi with the pinned SSH host key, has the recovery's `flash-boot.sh` write the image and reboots. (Until 2026-10-10 this was `tools/run-boot-update.sh`, through the vendor system.)

The recovery checks the hash of the image before writing, keeps the previous contents of `BOOT` in RAM for a rollback and reads back what it wrote. `build/kernel/boot-slot.json` records which image is installed, `build/kernel/recovery-slot.json` what is in `RECOVERY`.

## Safety nets

| Net | Catches | What happens |
| --- | --- | --- |
| Watchdog, 30 s, armed at boot | A hang | The SoC resets |
| initramfs fallback, 90 s | The root filesystem cannot be mounted | Reboot into the recovery |
| `j701f-netguard`, 300 s | Mainline is up but has no Wi-Fi address | Reboot into the recovery (which tries Wi-Fi itself and waits 240 s before booting the system again). **Off since 2026-10-26** (`/etc/j701f-netguard-off`): in daily use away from the known Wi-Fi it sent the phone to the recovery after every restart. Remove that file to arm it for unattended kernel trials |
| "Pending" stamps | A reset shortly after raising CPU/GPU limits or loading audio drivers | On later boots that step is skipped until the stamp file is removed |
| Graphical recovery in `RECOVERY` | A kernel that does not boot at all | Hold Power + Home + Volume Up; write another image or roll back from there. The vendor 3.18 slot is kept as a file (`tools/restore-vendor-recovery.sh`) |
| Odin archive of the original `BOOT` | Both slots unusable | Download Mode and a cable |

!!! warning "A hang during reboot"
    The watchdog driver switches the watchdog off as the system shuts down. If the kernel then hangs before the actual restart, nothing resets the phone: it happened once, after a kernel fault had left a lock held. Recovery is a forced restart — hold Volume Down + Power for about ten seconds. A local patch (`s3c2410_wdt.keep_on_shutdown=1`) keeps the watchdog running through shutdown; it is installed, and an ordinary reboot still completes normally. Power-off and a deliberately provoked hang have not been tested.

!!! warning "What the nets do not catch"
    A kernel that crashes **early in boot, every time** simply restarts forever: the watchdog resets it, and it crashes again before user space can do anything. Only a person holding the key combination ends that loop. This happened once, during the audio work. The answer is not another net but a habit: anything risky is built as a module or left disabled by default, and switched on from user space after boot.

### The stamp files

`/etc/local.d/j701f-gpufreq.start` and `/etc/local.d/j701f-audio.start` each create a file in `/var/lib/` before their risky step and delete it a few minutes later. If the phone resets in between, the file is still there on the next boot and the step is skipped. `/etc/local.d/j701f-stamps.stop` removes the files on an orderly shutdown, so an ordinary reboot is not mistaken for a crash.

To re-enable a skipped step:

```sh
sudo rm /var/lib/j701f-gpufreq.pending /var/lib/j701f-audio.pending
```

### Filesystem check at boot

Before the root filesystem is mounted, the initramfs runs `e2fsck` on it. It has no copy of its own: it borrows the installed one, with the libraries it needs, from the root while that is mounted read-only. The mode is chosen by a file in the installed system:

| `/etc/j701f-fsck-mode` | What runs |
| --- | --- |
| absent | `e2fsck -p` — only safe, automatic repairs |
| `-fn` | A forced, read-only report; nothing is changed |
| `-fy` | A forced full repair |

The result is in the kernel log (`j701f: e2fsck … exit status N`) and in `/run/j701f-fsck.log`. Remove the mode file after a one-off `-fn` or `-fy` run.

## What is never written

PIT, BL / sboot, EFS, TrustZone, modem and RPMB. The Wi-Fi MAC address normally comes from EFS; a fixed locally administered address in the device tree is used instead so EFS never has to be read.
