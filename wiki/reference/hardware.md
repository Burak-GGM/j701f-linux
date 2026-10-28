# Hardware and status

## The device

| | |
| --- | --- |
| Model | Samsung SM-J701F, code name `j7velte` |
| SoC | Exynos 7870 (`S5E7870`), 8 × Cortex-A53, 14 nm |
| GPU | Mali-T830 MP1 (Midgard) |
| RAM | 2 GB (about 1.6 GB visible to Linux) |
| Storage | 16 GB eMMC |
| Display | 720 × 1280 AMOLED, panel EA8061S, DECON display controller + MIPI DSI |
| PMIC | Samsung S2MPU05 (regulators, RTC, audio codec) |
| Charger / fuel gauge / USB switch | Samsung S2MU005 |
| Wi-Fi / Bluetooth | Broadcom BCM43430A1 (SDIO + UART) |
| Touchscreen | Melfas MIP4 |
| Touch keys | Coreriver TC360 |
| Accelerometer | ST LIS2HH12 |

## Status on mainline (Linux 7.1.13)

| Component | State | Notes |
| --- | --- | --- |
| Boot | ✅ | S-BOOT → U-Boot shim → Linux |
| CPU, 8 cores | ✅ | Frequency scaling 546–1586 MHz, local driver |
| eMMC | ✅ | DDR52, 60–80 MB/s sequential read (was 22 MB/s in legacy mode). HS200 was tried and is unstable (write errors); not enabled |
| USB | ✅ | Gadget only: serial shell and MTP file access (home directory and SD card); the USB network function of the early stages is switched off since 2026-10-13. The MUIC switch is set by a script in the initramfs and re-checked by the charger module, which also reads the cable type. No host mode |
| Display | ✅ | Native driver since 2026-10-10: DECON + DSIM + the EA8061S panel, switched to at every boot before the desktop starts (modules and a device-tree overlay loaded from the root filesystem; the bootloader framebuffer is the fallback, also by holding Volume Down). 59.6 frames per second, real panel brightness, blanking, resume from suspend. See [Display](display.md) |
| GPU | ✅ | Panfrost; frequency scaling 343–1001 MHz |
| Touchscreen | ✅ | Three small patches |
| Wi-Fi | ✅ | `brcmfmac`, fixed locally administered MAC address |
| Bluetooth | ⚠️ | Controller up with patch firmware and a fixed address, BlueZ running, scanning finds devices. Pairing and Bluetooth audio not tested |
| Sound | ⚠️ | Speaker playback and recording from the main microphone work. The second and headset microphone inputs, headphones and earpiece are written but not confirmed. Headset insertion is reported (not yet seen with a real plug) but the output does not switch by itself. No call audio |
| Battery gauge | ⚠️ | Percentage, voltage, current. The chip drifts unless it is switched between its current and voltage modes as the vendor kernel does; a script does that (`system/battery/`), run by hand for now, not yet a boot service |
| Charging | ⚠️ | The hardware charges on its own; the driver reports cable, cable type, charging state and health, sets the two current limits by cable type and can switch charging off and on (`charge_behaviour`). Limits: computer port 500 mA in / 450 mA into the battery (the bootloader's values), charging port 1000/1000, wall charger 1200/1000 (vendor: 1550/2150). The battery helper script raises the wall-charger values to 1550/1500 while the battery is between 15 and 41 °C and lowers the current when it is cold or hot. The wall-charger case is written and tested against a simulated system, but not yet tried with a wall charger. Float voltage and top-off are the bootloader's |
| Temperature | ✅ | Processor: local read-only driver; throttling at 70 °C, shutdown at 105 °C. Battery and board thermistors: read through the SoC's ADC by a small module (`j701f_adc`, a hwmon device), loaded at boot |
| Watchdog | ✅ | 30 s, armed from boot |
| Home key, touch keys | ✅ | Mapped to home, task switcher and back. Recents needs the release's `kglobalshortcutsrc` binding; back works where the app has somewhere to go back to (Kirigami apps, the app drawer, folders), and does nothing on the home screen |
| Accelerometer | ✅ | `iio-sensor-proxy` reads it and KWin rotates the screen; all four orientations confirmed by the owner after the mounting matrix was corrected |
| Vibration motor | ⚠️ | `regulator-haptic`; since 2026-10-13 the desktop's vibration service (feedbackd) is installed and drives it - the motor's supply switches on during a feedback event. Not yet confirmed by hand |
| microSD slot | ✅ | High-speed mode, about 22 MB/s; mounted at `/media/sdcard` at boot and offered over MTP; UHS modes and hot-plug not tested |
| Proximity sensor | ⚠️ | CM36672P through the `vcnl4000` driver; readable, seen by `iio-sensor-proxy`, not verified with an object, not used by the desktop. The phone has no ambient light sensor, so there is no automatic brightness |
| Hardware video decoding | ⚠️ | The codec works: a 720p H.264 file decodes with about 24 times less CPU time than in software. Loaded at boot; H.264 from 360p to 1080p, HEVC and VP8 decode correctly (bit-exact against software), MPEG-2 works, MPEG-4 does not. `mpv` is configured to use it; the browsers are not |
| Modem (calls, SMS, data) | ❌ | Not started |
| Camera | ⚠️ | Both sensors (rear S5K3L2, front S5K5E3) deliver raw frames through a local driver that bypasses Samsung's FIMC-IS; libcamera processes them in software. Plasma Camera shows a preview, takes photographs and switches cameras. Short video works from the front camera at Auto and the rear camera at 540p, but rear Auto fails under memory pressure. Reduced resolution (2072×1552 rear), no autofocus and plain colours. See [Camera](camera.md) |
| Flashlight | ✅ | Rear and front flash LEDs as two LED devices in torch mode (rear 25–150 mA in six steps, front 25–50 mA); confirmed by the owner. Plasma's flashlight tile switches the rear one; the "Flashlight" app (`j701f-flashlight`) both |
| Power domains | ⚠️ | No driver. All four are on at boot and stay on (the module that switched the camera domain off is retired now that the camera is used). Switching the video domain by hand broke the codec until a reboot |
| Suspend | ⚠️ | Suspend-to-idle works and resumes in half a second (verified with clock-alarm wake-ups up to 60 s). Wakes on the clock alarm only (key wake-up was removed again, it slowed application start); nothing suspends the phone automatically; power saving not measured ([details](kernel.md#suspend)) |

## Partitions that matter

| Name | Device | Size | Use in this project |
| --- | --- | --- | --- |
| `BOOT` | `mmcblk0p10` | 32 MiB | Mainline kernel image |
| `RECOVERY` | `mmcblk0p11` | 38 MiB | The project's graphical recovery (since 2026-10-10); the vendor 3.18 image it replaced is kept as a file |
| `SYSTEM` | `mmcblk0p18` | 3 GiB | Untouched |
| `USERDATA` | `mmcblk0p24` | 11.1 GiB | Alpine root filesystem (ext4) |

Partition numbers are observations from this phone. Tools identify partitions by name, size and content, never by number alone.

## Addresses worth knowing

| What | Where |
| --- | --- |
| Bootloader framebuffer | `0x67000000`, 720 × 1280, 32 bpp |
| GPU | `0x11400000`; clocks from `CMU_G3D` at `0x11460000`; supply `BUCK2` |
| CPU clock controllers | cluster 0 `0x10900000`, cluster 1 `0x10800000`; supply `BUCK1` |
| Temperature sensor | `0x10130000` |
| Watchdog | `0x10170000` |
| Audio: I²S / mixer / DMA / resets | `0x148a0000` / `0x14880000` / `0x14890000` / `0x148f0000` |
| Audio and display clocks (`CMU_DISPAUD`) | `0x148d0000` |
| PMIC | I²C bus at `0x10510000`, address `0x66`; audio codec on the same bus at `0x04` |
| USB switch (MUIC) | I²C bus at `0x13870000`, address `0x3d` |

## Measured values

**CPU voltage per frequency** (regulator `BUCK1`, read under the vendor kernel; the driver adds 12.5 mV):

| MHz | 546 | 676 | 757 | 839 | 902 | 1014 | 1144 | 1248 | 1352 | 1482 | 1586 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| mV | 625.00 | 668.75 | 693.75 | 712.50 | 737.50 | 781.25 | 825.00 | 868.75 | 906.25 | 956.25 | 1006.25 |

**GPU steps:** 343, 450, 545, 676, 728, 845, 1001 MHz. The mainline table never goes below 775 mV (the value at boot) because `BUCK2` may feed more than the GPU; 845 MHz uses 850 mV and 1001 MHz uses 943.75 mV.

**Benchmarks on mainline:**

| Test | Result |
| --- | --- |
| `sysbench cpu`, 1 thread, 1586 MHz | 741 events/s (421 at 902 MHz) |
| `sysbench cpu`, 8 threads, 1586 MHz | 5146 events/s |
| `es2gears_wayland`, vsync off, GPU at 1001 MHz | about 730–820 FPS (about 250 at 343 MHz) |
| 4 minutes, all cores and GPU at maximum | 54 → 60 °C |
