# Hardware driver status — 2026-10-07

This is Alpine 3.24.0 userspace running on the reused Samsung/OrangeFox 3.18.140-SIMPLE-KERNEL_V1.0 kernel. Many device drivers are already built into that kernel. Exposing an interface or device node confirms detection, not successful end-to-end operation.

Read-only live reports: `build/phone-driver-inventory.txt` and `build/phone-driver-inventory-extra.txt`. No interfaces were activated, packages installed, partitions mounted or phone settings changed during these checks. The embedded binary's configuration is `extracted/boot-metadata/kernel.config`; the related public SIMPLE source tree is a family reference, not an exact attested source match.

| Component | Observed status | Remaining work |
| --- | --- | --- |
| CPU, RAM, internal storage | AArch64 Alpine boots; DATA is writable ext4 root. | Repeat-reboot persistence and longer stability testing. |
| Display and touch | Existing framebuffer/input terminal and touchscreen have hardware evidence; fb0 remains exposed. | Additional graphical applications and normal-system UI checks. Terminal rendering uses CPU writes, not GPU acceleration. |
| USB | Serial root shell works in normal Alpine boot. | USB networking/ADB not implemented. |
| Wi-Fi | BCM43438A1 using existing DHD driver and matching Samsung firmware; WPA2 association, DHCP, gateway, DNS and HTTPS repository access verified. | Cold-boot reconnection and longer stability/power testing. See `wifi.md`. |
| GPU | Mali-T83x, one core, hardware ID 0x0830, exposed as /dev/mali0. Kernel config uses ARM/Samsung Midgard r28p0 and disables DRM. No /dev/dri. | Compatible graphics userspace and real rendering tests; no accelerated EGL/OpenGL is configured. |
| Audio | Universal7870-I2S ALSA card and PCM/control nodes exposed; COD3026X codec probed. | Mixer routing, playback/record tools, speaker/headphone/microphone trials. |
| Bluetooth | Broadcom power/rfkill device exposed, software blocked; Bluetooth protocol stack initialized. No HCI controller listed in /sys/class/bluetooth. | Controller transport/firmware bring-up, suitable userspace and pairing tests. Merely enabling rfkill is not proof of controller availability. |
| Battery and charger | Samsung battery/fuel-gauge/charger sysfs interfaces exposed; battery reports Full, 100% at capture. | Charge/discharge behavior, power management, suspend/resume and power efficiency tests. Names such as wireless in sysfs do not establish corresponding physical features. |
| Sensors | Accelerometer and proximity sensor class entries exposed. | Actual readings/events, calibration and application support. |
| SD card | mmcblk1 enumerated as SD, 61,440,000 sectors. | No SD filesystem mount/read/write test performed. |
| Camera and media codecs | Exynos FIMC-IS sensor/pipeline nodes, JPEG/scaler and MFC decode/encode nodes exposed. | Firmware where required, media routing and compatible userspace; no capture or accelerated decode/encode tested. |
| Cellular modem | rmnet and umts interfaces exposed. | No calls, SIM handling or cellular data integration tested. Interface presence does not prove a usable modem service. |

## Wi-Fi

The compiled config defaults differ from the paths actually chosen by the running driver. A live interface-up trial identified BCM43438 revision 1 and requested `/vendor/etc/wifi/bcmdhd_sta.bin` plus `/vendor/etc/wifi/nvram.txt`. Those matching files were extracted from the supplied J701FXXUACUH1 Samsung AP archive into the Linux DATA root. Firmware 7.119.17 loaded; its CLM regulatory data is embedded, so a separate CLM blob was not required.

The phone now associates with the laptop's network using Alpine wpa_supplicant and BusyBox DHCP. Automatic startup is configured under BusyBox init. No kernel replacement was needed. See [Wi-Fi setup and verification](wifi.md) and `build/phone-wifi-test.txt`. The earlier inventory reports describe the state before this installation.

## Graphics

The framebuffer scanout/display controller works independently from the Mali 3D processor. Our terminal maps fb0 and paints pixels with the CPU, so seeing a working screen does not prove GPU acceleration.

Mesa documents Mali-T830 hardware support in [Panfrost](https://docs.mesa3d.org/drivers/panfrost.html). That does not make the current ARM/Samsung /dev/mali0 driver a Panfrost DRM driver. The current kernel has DRM disabled, and no EGL/OpenGL utilities or acceleration stack is installed. A standard Panfrost path requires matching kernel graphics support and board/display integration; an alternative vendor userspace path requires a compatible Mali driver ABI and libc/platform integration. Neither is implemented or promised. GPU boot logs also note missing generic regulator/clock/devfreq control; no rendering workload was run to determine their practical effect.

## Practical sequence

Wi-Fi is a reasonable next milestone because a real wireless interface already exists, and network access would allow Alpine package management. Audio and battery/sensor UI can then be tested separately. GPU acceleration and camera/media integration are larger independent milestones. This is a development system with confirmed boot/storage/terminal foundations; peripheral support is still being brought up individually.
