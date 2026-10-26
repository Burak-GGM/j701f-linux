# Wi-Fi milestone — 2026-10-07

The normal Alpine system connects to the home router's network using WPA2-PSK/CCMP on 2462 MHz (2.4 GHz, channel 11). Initial DHCP address: `192.168.1.139/24`; gateway and DNS: `192.168.1.1`. DHCP addresses can change, especially because this driver generates a MAC when no Android MAC store is present.

## Driver and firmware

The existing 3.18.140-SIMPLE-KERNEL_V1.0 kernel was retained. Its Broadcom DHD 100.13.36.1 driver reports BCM43438 revision 1. Its actual startup paths are `/vendor/etc/wifi/bcmdhd_sta.bin` and `/vendor/etc/wifi/nvram.txt`, despite different compile-time config defaults.

Both files came from `/vendor/etc/wifi` in `system.img.lz4` inside the supplied J701FXXUACUH1 Samsung AP archive. Only the host copy of that image was decoded and read using debugfs. The phone's SYSTEM partition was not mounted or changed. The stock NVRAM identifies J7 refresh / BCM43438A1 and J701F; no RF calibration values were invented or modified.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| bcmdhd_sta.bin | 371153 | 18490dd2da867471d9744ede586497f6a20a9b94044042a74f99287ae2cbb189 |
| nvram.txt | 1531 | 12770a57b4957d5110122ad7ad9db2604872efca88fb4adf8dd5756f9b944379 |

Firmware version: 7.119.17, FWID 01-940b5c82, dated 2021-03-19. The driver confirms the firmware contains CLM data. Firmware is kept in ignored `extracted/wifi`, with the supplied archive remaining its source; it has not been added to repository source files.

The archived [Quantum J7velte source](https://github.com/Quantum-kernel/Quantum-Kernel-J7velte) was inspected as a reference. Its Samsung DHD customization code demonstrates vendor/chip-specific firmware handling; it is not an attested source match for our running SIMPLE binary. The live driver's diagnostic output determined the files used here.

## Userspace and credentials

Signed aarch64 packages were fetched from Alpine v3.24/main on the laptop, transferred in SHA-256-checked chunks over USB, and installed with apk's normal signature checking (no `--allow-untrusted`). Installed connection tools are wpa_supplicant 2.11-r4 and iw 6.17-r0, with dbus-libs, libnl3 and pcsc-lite-libs. libcrypto3 and libssl3 were upgraded to 3.5.9-r0 to satisfy the current package set. BusyBox supplies DHCP and NTP; no OpenRC migration was performed.

The laptop's active NetworkManager connection was read with user authorization. Its saved credential was converted privately into a WPA2 PSK and copied to `/etc/wpa_supplicant/wlan0.conf` on the phone, owned by root, mode 0600, inside a mode-0700 directory. SSID is encoded as hex; `update_config=0`. The PSK is password-equivalent and must remain private. No credential is in source, build reports, flash images or documentation. Temporary host credential copies are removed after setup.

## Startup and operation

`system/wifi` installs as `/sbin/j701f-wifi`; BusyBox init supervises it through an added respawn entry. It waits quietly when no credentials/tools are installed. When provisioned it brings up wlan0, runs wpa_supplicant, waits for association, runs foreground udhcpc, and maintains BusyBox NTP for the old kernel's incorrect boot clock. If association or DHCP processes exit, it cleans up its children and init restarts the service. NTP failures are retried without restarting Wi-Fi.

`system/wifi-dhcp` installs as `/sbin/j701f-wifi-dhcp`. It configures address, default route and DNS for wlan0, handles renewals without waiting on stdin, and removes the address/route on deconfiguration. This replaces Alpine's stock DHCP hook for this interface: the shipped stock renewal code has grep calls without an input file, unsuitable for our supervised foreground DHCP client.

Runtime logs are private RAM files under `/run/j701f-wifi/`: `association.log`, `dhcp.log` and `time.log`. Do not enable wpa_supplicant's `-K` key logging.

These live changes are on DATA: packages, firmware, protected Wi-Fi config, service scripts and `/etc/inittab`. BOOT, RECOVERY and SYSTEM were not flashed. The existing `build/system` flash images predate this provisioning and do not contain the installed Wi-Fi environment. The builder now includes the optional service scripts; rebuilding alone does not supply firmware, packages or credentials. Do not reflash DATA to apply these changes: it would replace the installed system and its private configuration.

## Verification

The phone passed WPA2 association, DHCP configuration, three gateway pings without loss, DNS resolution and authenticated HTTPS fetching of both Alpine package indexes (`apk update`). This fetched indexes, not a full distribution upgrade. Service recovery, DHCP renewal, an NTP clock correction, and HTTPS repository access are recorded in `build/phone-wifi-test.txt`. The laptop also reached the phone with three successful Wi-Fi pings. Shell syntax checks and 14 system-image unit tests passed. Automatic startup was initially exercised by reloading BusyBox init and restarting the supervised service. A subsequent normal reboot during the CPU BOOT-parameter trial automatically restored Wi-Fi and SSH, assigning `192.168.1.140`. GUI dependency installation over this connection then succeeded.

Read current status at either the on-device or USB terminal:

```sh
wpa_cli -i wlan0 status
ip -4 addr show dev wlan0
ip -4 route show
cat /run/j701f-wifi/dhcp.log
```

SSH was subsequently installed by the user and enabled separately; see [SSH setup](ssh.md).
