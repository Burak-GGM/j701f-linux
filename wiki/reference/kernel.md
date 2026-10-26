# Kernel, patches, device tree

## Which kernels

| Kernel | Where | Purpose |
| --- | --- | --- |
| **Linux 7.1.13** (`7.1.13-BURAK-PANFROST-01`) | `BOOT` | The system in daily use |
| The same Linux 7.1.13 with the recovery's initramfs | `RECOVERY` | The project's [graphical recovery](recovery.md): fallback and the place new images are written from (since 2026-10-10) |
| Samsung 3.18.140 ("SIMPLE" custom-ROM build) | kept as a file | Was in `RECOVERY` until 2026-10-10 as the fallback; the whole slot is saved and can be written back |
| Linux 6.15 + exynos7870-mainline tree | not installed | The first mainline base; its build entry is kept as `panfrost-6.15` |

The 7.1.13 source is the kernel.org tarball, pinned by SHA-256 in `kernel/inputs.json`. Patches are applied on top in the order below.

## Community patches (`kernel/patches/exynos7870-7.1/`)

Six patches from the [exynos7870-mainline](https://gitlab.com/exynos7870-mainline/linux) 7.1 branch that are not in kernel.org yet:

| Patch | Subject |
| --- | --- |
| 01 | Exynos 7870 configuration fragment |
| 02 | postmarketOS configuration fragments |
| 03, 04 | `samsung-dsim` display bridge fixes |
| 05, 06 | `dw_mmc` DMA threshold option and its Exynos value |

Everything else the SoC needs — clock controllers, pin control, the S2MPU05 PMIC, USB, I²C, the base device tree `exynos7870.dtsi` — is already upstream in 7.1.

## Local patches (`kernel/patches/linux-*.patch`)

These exist only in this project. None has been sent upstream. Two of them, the `btbcm` address and the video decoder's first frame, have been rewritten against current mainline and prepared for sending in `kernel/upstream/` (checked with `checkpatch.pl`, recipients from `get_maintainer.pl`); sending them is the owner's step, with his own `Signed-off-by`.

| Patch | What it does | Why |
| --- | --- | --- |
| `linux-mip4-vdd-supply` | Optional power supply and a 300 ms start-up delay for the Melfas touchscreen | The chip was queried before it was ready |
| `linux-mip4-z-resolution` | Fill in a missing axis resolution | The desktop's input library rejected the device |
| `linux-mip4-empty-packet-debug` | Extra diagnostics for empty touch packets | Used while finding the two bugs above |
| `linux-tm2-touchkey-bitmap-events` | Bitmap event format for the TC360 touch keys | This chip does not send key codes |
| `linux-tmu-exynos7870-readonly` | Read-only temperature sensor driver | No mainline TMU support for this SoC |
| `linux-cpufreq-exynos7870-j701f` | CPU frequency scaling for both clusters | No mainline driver; voltages measured on this phone |
| `linux-g3d-exynos7870-scaling` | GPU PLL rate table, and a driver that parks the GPU on a spare clock during PLL changes | GPU was fixed at 343 MHz |
| `linux-wdt-s3c2410-keep-on-shutdown` | Option to keep the watchdog running through shutdown | A reboot once hung with the watchdog already stopped |
| *(in `kernel/patches/staged/`, not applied)* | Experiments kept for reference: two simpledrm changes (cacheable framebuffer, software gamma table) that gave no gain or were superseded, and display-driver patches still under review | Each file says in its header why it is not used |
| `linux-sysfb-j701f-fast-argb-copy` | Faster conversion and copy of each frame into the bootloader framebuffer | That copy limits the frame rate of the whole desktop ([measurements](performance.md#frame-rate-the-display-path)) |
| `linux-zz-simpledrm-j701f-software-backlight` | Backlight device `j701f-panel` whose level is applied while frames are copied; connector reported as DSI | Brightness without the compositor's extra pass (20 → 49 frames per second when dimmed). The `zz` keeps it after the copy patch it builds on |
| `linux-zzz-sysfb-j701f-neon-copy` | The frame copy (plain and dimmed) done with NEON instructions | Dimmed frames cost 10 ms more than plain ones: 41 → 51 frames per second |
| `linux-zzzz-mfc-keep-first-frame-all-codecs` | The video decoder keeps the first data packet for decoding for every format, not only H.264 | HEVC, MPEG-2 and VP8 lost their first key frame: garbage until the next one |
| `linux-wdt-s3c2410-keep-on-suspend` | Option to leave the watchdog running across suspend | Safety net for suspend experiments nobody is watching: a hang ends in a reset |
| `linux-cpuidle-psci-exynos7870-default-off` | Register the CPU power-down idle state switched off on this SoC | The state is an experiment; a core is opted in at run time, so a hang cannot become a boot loop |
| `linux-btbcm-43430a1-patched-default-addr` | Recognise the address the Bluetooth chip reports after its patch firmware is loaded as "not configured" | Without it the fixed address in the device tree was ignored |
| `linux-panfrost-shrinker-switch` | Runtime setting for how the kernel discards GPU buffers under memory pressure (the phone uses mode 2: never the shared ones) | Black areas in the browser; see [performance](performance.md) |
| `linux-mfc-exynos7870` | Names the clock for the video codec driver's v10 variant, switches the memory-management unit in front of the codec to bypass, and lets the codec use a dedicated memory region | Without the bypass the codec's firmware never starts; without the region small videos fail |
| `linux-power-j701f-s2mu005-charger` | Charger status, current limits by cable type, flashlight LEDs (a module) | The desktop could not tell whether the cable was plugged in; a wall charger charged no faster than a computer port |
| `linux-audio-exynos7870-lpass` | Audio PLL corrected to a fractional PLL; audio subsystem bring-up driver | First step for sound |
| `linux-audio-j701f-codec-card` | COD3026X playback codec, S1402X mixer setup and the sound card | Ported from the vendor kernel |

The audio drivers are derived from Samsung's GPL-licensed 3.18 sources. The reference files, their repository and commit are recorded in `build/kernel/vendor-audio-reference/SOURCE.txt`.

### Parameters the local drivers expose

| File | Meaning | Kernel default |
| --- | --- | --- |
| `/sys/module/exynos7870_cpufreq/parameters/max_khz` | Highest CPU frequency | 1352000 |
| `/sys/module/exynos7870_cpufreq/parameters/min_khz` | Lowest CPU frequency | 546000 |
| `/sys/module/clk_exynos7870_g3d_park/parameters/max_khz` | Highest GPU frequency | 343000 |

The defaults are deliberately conservative. A boot script raises them to 1586000 and 1001000; see [userspace](userspace.md).

## Configuration

The kernel configuration is the upstream `defconfig` plus the two community fragments plus `kernel/configs/mainline-bringup.config`, which holds every option this project adds, with comments. Notable choices:

- All other SoC families (`ARCH_*`) are switched off; this cut the kernel image from 44 MB to about 28 MB.
- Drivers the phone needs to boot and show a picture are built in, not modules.
- The Samsung I²S and the local audio drivers are **modules on purpose** and are not installed under `/lib/modules`; see the [sound chapter](../journey/08-sound.md) for why.

The resolved configuration is pinned by hash in `kernel/inputs.json`. When the fragment changes, the build stops and the new hash has to be recorded deliberately.

## Device tree

The board description is built in layers. Each file includes the previous one and adds one stage, so the history of the port can be read from the file list:

| File (`kernel/dts/exynos7870-j7velte-…`) | Adds |
| --- | --- |
| `diagnostic.dts`, `pmic.dtsi` | The base board: memory, PMIC regulators, UART, USB |
| `logged.dts` | Simple framebuffer, ramoops |
| `usbdiag.dts` | The I²C bus used to set the USB switch |
| `emmc.dts` | eMMC |
| `gpu.dts` | GPU and its clock controller |
| `touch.dts` | Touchscreen |
| `wifi.dts` | Wi-Fi, Home key, storage aliases |
| `periph.dts` | Fuel gauge, touch keys |
| `thermal.dts` | Temperature sensor and thermal zone |
| `wdt.dts` | Watchdog |
| `cpufreq.dts` | CPU frequency driver, thermal trip points |
| `extra.dts` | Bluetooth, accelerometer (with its mounting matrix) |
| `gpufreq.dts` | GPU operating points, clock-parking node |
| `gputhermal.dts` | GPU as a cooling device |
| `audio.dts` | Audio clocks, LPASS, DMA, I²S, codec, sound card |
| `emmchs.dts` | eMMC High Speed / DDR52 |
| `phone1.dts` | Vibration motor, microSD slot, proximity sensor |
| `mfc.dts` | Video codec clock controller and node |
| `bt.dts` | Fixed Bluetooth address |
| `charger.dts` | Charger status node |
| `cpuidle.dts` | One CPU idle state (core power-down); registered switched off, see below |
| `suspend.dts` | Wi-Fi card keeps its power during suspend |
| `fbmem.dts` | The framebuffer node names its reserved memory region, which makes the per-frame copy faster ([why](performance.md#frame-rate-the-display-path)) |
| **`camera.dts`** | The two camera sensors on their I²C buses, with their supplies, clocks and reset lines ([Camera](camera.md)) — **the current top of the chain** |
| `emmchs200.dts` | A failed HS200 attempt, kept as a record; not used for builds |

A verifier (`tools/build-j701f-dtb.py`) refuses a device tree that enables storage, the GPU, Wi-Fi or the audio clocks unless the matching `--allow-…` flag is given (`--allow-sd` for the microSD slot), and checks memory reservations and GPU resources against values measured on the phone.

## Building

```sh
# Kernel only
python3 tools/build-kernel.py panfrost --jobs 11

# Kernel + device tree + initramfs + U-Boot + Android image, verified
tools/build-mainline-image.sh NAME kernel/dts/exynos7870-j7velte-camera.dts "--allow-audio --allow-sd --allow-mfc"
```

The compiler is LLVM/Clang. Sources are unpacked under `/tmp/j701f-kernel-build`. Each patch is applied once and marked with a file named after the patch's hash; to change an already-applied patch, restore the files it touched, delete its marker and rebuild.

Audio modules are built with the same environment and explicit `.ko` targets; the built modules are kept in `build/kernel/audio-modules/`.

## Offline panel prototype

`tools/kmod/ea8061s/` contains an experimental, separately built EA8061S J7VE
panel module. It is not part of the installed kernel image or an autoload list.
Compilation and host command/failure checks pass; panel output, DECON DMA and
the handover from simpledrm remain untested. See [real display driver](display.md).

The local `linux-dsim-pll-wait-fix.patch` corrects the imported DSIM PLL
completion result, unmasks its interrupt, and preserves combined IRQ events.
Host regressions and a full kernel build pass. The recorded `pfshrink3` BOOT
package includes this fix, `linux-dsim-init-errors.patch` for failure
cleanup and `linux-dsim-j701f-timing-trial.patch` for the explicit, default-off
J701F timing profile. Native display controllers remain disabled in its device
tree; the changes are compiled, not hardware-validated.

## Suspend

**Suspend-to-idle works** (`s2idle`, the only kind this firmware allows: its PSCI is version 0.1 and has no system-suspend call). Processes are frozen, every driver suspends its device, the cores sit idle until a wake-up interrupt, and everything resumes in about half a second.

How it was brought up without anyone at the phone:

1. The kernel got its suspend test facility (`CONFIG_PM_DEBUG`), which can stop a suspend at a chosen depth and come back after five seconds: `freezer`, then `devices`, then `platform`.
2. A local watchdog option keeps the watchdog running across the suspend, so a hang would have ended in a reset. It never fired.
3. A script armed the real-time clock as the wake-up source and rebooted the phone if the network did not come back.

What had to be fixed:

| Seen | Cause | Fix |
| --- | --- | --- |
| Wi-Fi dead after resume, every SDIO access timing out | The card lost power in suspend; the MMC host did not allow "keep power" | `keep-power-in-suspend` in the device tree |
| Kernel asked for the Wi-Fi and Bluetooth firmware at suspend and did not find it | Those files existed only in the initramfs | Copies in `/lib/firmware/brcm/` on the root filesystem |
| Codec I2C errors twice a second while asleep | The headset-detection poll kept running | It now runs on the freezable work queue |

Tested: sleeps of 6, 8 and 60 seconds ended by the clock alarm, with all local modules loaded; the desktop, Wi-Fi and screenshots worked afterwards. One harmless message remains (`tm2-touchkey … failed to read i2c data` on resume).

Waking with a key is **not** configured at the moment: marking the power and home keys as wake-up sources, together with the Wi-Fi setting above, made the browser start 1.1 seconds slower (measured across eight images; either setting alone is harmless and the reason is not understood). So a sleeping phone wakes on the clock alarm only. Not measured: how much power the sleep saves — the cores only idle, they are not powered down (see the next section).

Nothing puts the phone to sleep by itself. That is deliberate for now: Wi-Fi does not wake the phone and neither do the keys, so always set the clock alarm first. To try it by hand:

```sh
# sleep for 30 seconds, then wake by the clock
echo +30 | sudo tee /sys/class/rtc/rtc0/wakealarm
echo freeze | sudo tee /sys/power/state
```

## CPU idle: an experiment that is switched off

When a core has nothing to do it only stops its clock (WFI); upstream describes no deeper state for this SoC. The vendor kernel powers idle cores down, and that is also the first thing system suspend needs, so it was tried:

- The device tree describes one state: core power-down through the firmware call PSCI `CPU_SUSPEND`, with the parameter from the vendor device tree.
- The vendor kernel also clears a field in the core's power-management register just before that call. Without it the phone hangs within seconds. A small module, `tools/kmod/j701f_cpupd.c`, does the same.
- With the module, cores 1–7 entered the state tens of thousands of times over several minutes without a problem. **Including core 0 hangs the phone** after 20–80 seconds (four times out of five). Core 0 receives every device interrupt, which is the likely connection; it has not been investigated further.
- No benefit could be measured: on USB power the phone offers only the SoC temperature, and that did not move beyond noise.

So the state is registered **switched off** and nothing turns it on. To experiment (the watchdog reboots the phone if it hangs):

```sh
sudo insmod ~/j701f-cpuidle/j701f_cpupd.ko
for c in 1 2 3 4 5 6 7; do echo 0 | sudo tee /sys/devices/system/cpu/cpu$c/cpuidle/state1/disable; done
```

One core alone never enters the state: the kernel needs one awake core to wake the others, and a single candidate is always that one.

### Display diagnostic kernel

`linux-dsim-z-j701f-pll-diagnostics.patch` records PLL interrupt masks, link lock
and reset completion only with the J701F display trial enabled. It changes no
register programming and still rejects timeout. Package `dsimdiag2` was installed
with full BOOT read-back; running GNU build ID and Plasma/simpledrm were verified.
Its native/watchdog retest passed; daily output remains simpledrm. See [display notes](display.md).

`linux-dsim-zz-j701f-inherited-pll.patch` stops an inherited enabled PLL before
reset only for the J701F trial. Isolated `dsimpll2` is now installed: full BOOT
read-back `a2b11f5a…`, running build ID `1950147e…` and Plasma/simpledrm match.
Fresh watchdog reset/unchanged return and native first-init verification passed
in `native-dsimpll2-01`: one completion on the first attempt, no PLL timeout,
native checks/120 flips and automatic unchanged BOOT/Plasma return. It retains
the exact prior diagnostic DTB/initramfs. Five actual-init regression tests pass;
this is one bounded hardware A/B, not a long soak or daily native desktop.
