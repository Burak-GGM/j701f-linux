# Hardware observations — 2026-10-07

The user booted the USB diagnostic recovery on the SM-J701F and supplied an interactive terminal transcript.

Confirmed by that transcript:

- Host connected through `/dev/ttyACM0` using `tools/usb-console.py`.
- Custom greeting appeared: `HELLO FROM BURAK'S J701F LINUX RECOVERY`.
- `uname -a` reported `3.18.140-SIMPLE-KERNEL_V1.0`, AArch64.
- `/tmp/stage1-ready` contained `Stage 1 /init reached shell loop`.
- Shell commands including `ls`, `cat` and `uname` worked.
- USB log reported ACM enabled with `04e8:6860` and shell startup on `ttyGS0`.
- `/dev/fb0` existed, but the display helper reported `Unsupported framebuffer layout; refusing to draw` on every attempt. No visual heartbeat was confirmed.

**Stage 1 custom userspace and the Stage 2 USB serial shell are working on hardware.** The remaining black screen is a separate display bring-up issue. The validation failure does not yet identify which geometry, allocation, visual type or color field was rejected.

The associated delivered host artifacts are saved in `build/usb-confirmed/`. Their image SHA-256 is `9b5f20c6e04a3ba25387dc5d7918b41505b001a559538e73eab8e57102a124fb`, and tar SHA-256 is `7050afbeb503b4e98592f0bb73cafc785c7f42926c47354a5be12705af498beb`. These identify the delivered host files; the phone's RECOVERY partition was not read back to verify its hash.

Next investigation: obtain the phone's framebuffer mode and metadata using read-only queries. The updated helper prints full layout fields and an exact rejection reason, and provides `--info` for queries without drawing, unblanking or panning. Do not weaken framebuffer bounds checks based only on the generic error.

## Framebuffer probe and live test

The subsequent phone probe reported 720×1280 visible and virtual resolution, 32 bits per pixel, packed-pixel type 0, visual 0, stride 2880, and allocation size 7,372,800 bytes. RGB fields were 8 bits each at offsets 16/8/0, with no alpha field and zero offsets. The initial helper rejected only `visual=0`.

A scoped compatibility rule now accepts visual 0 only with that XRGB8888 channel arrangement. It still validates pixel type, bitfield positions, dimensions, stride and allocation bounds. Other unexpected visual-0 formats remain rejected.

The revised helper was transferred to the running phone's RAM and executed for six frames. The phone reported `Layout validation: supported`, successful mapping, unblank result 0, pan result 0 for all six frames, and helper exit status 0.

The report is saved in `build/phone-display-test.txt`. This confirms the revised helper runs and the driver accepts its display operations. The user subsequently confirmed that the physical panel remained black. Return codes alone did not establish visible output.


## Panel report and activation experiment

A read-only report collected over the working USB shell found only fb0 at `/sys/devices/14830000.decon_fb/fb0`. The backlight `panel` reported brightness 118, maximum 355, actual brightness 152, and bl_power 0. Reading LCD lcd_power returned `No such device or address`, so that attribute does not establish panel power state. The kernel log contained `decon already enabled` and `ea8061s_displayon` during the earlier unblank tests.

The related SIMPLE kernel source initializes window registers in `decon_set_par` and consumes them in `decon_pan_display`. This suggests missing mode activation as an experiment, but the source tag is not a verified exact match to the binary. The first temporary current-mode activation test lost USB before completing; no partial output was retained by that older host implementation. Whether the phone reset or the cable disconnected is not yet established. Activation remains an explicit experimental test only, excluded from normal boot and the standard six-frame test. No phone partition was written during either test.

The host now provides `--display-diagnostics` and preserves partial serial responses when a test is interrupted. Further live diagnosis requires the phone's USB connection to return.


## Visible output confirmed after activation

The user clarified that the disconnect during the first activation test was intentional cable removal, and that BURAK LINUX appeared. After restarting, the standard tests in the pasted transcript did not activate the mode and the panel stayed black again. This was a volatile display state change, not a flashed change.

The activation test was repeated over USB without disconnecting. `FBIOPUT_VSCREENINFO` returned 0; the queried geometry remained 720×1280 at 32 bpp with stride 2880 and allocation 7,372,800 bytes. The driver normalized visual from 0 to 2 and alpha from absent to 8 bits at offset 24. All six pan calls and the helper exit status returned 0. The user explicitly confirmed that text or the colored bar appeared.

The complete report is `build/phone-display-activation-test.txt`. Current-mode activation is now performed by normal startup and the regular `--test-display` helper. The metadata is re-queried and all layout/bounds checks run again before mapping, so the renderer uses the normalized alpha fields. Read-only `--info` still performs no activation. The rebuilt recovery preserves the baseline kernel, DTB and header parameters; a reflash/reboot test of its automatic startup display has not yet been performed.

The regular `--test-display` was then repeated with the final embedded helper (SHA-256 `d0815357eefc250a63538117b885bc43d173fa871e01e6fd33340816121b580f`). Activation, all six pans and exit status returned 0. The rebuilt archive SHA-256 is `673e7d33a81854492e2f1d79a0026c98da6a32964ef260b92decbff338ad63b7`; this identifies the host artifact, not a read-back measurement of the phone partition. All 27 Python tests, native framebuffer sanitizer checks, activation failure/bounds checks and AArch64 execution checks passed.


## Automatic heartbeat and channel correction confirmed

The user flashed the activation-enabled image and confirmed the bar changes automatically, appearing green/orange. A RAM-only six-frame test exchanged red and blue only in the renderer's copied bitfields; no driver mode color fields were changed. The continuously running boot helper was paused during the test and resumed afterward. All six pan calls and the helper exit status returned 0; the user confirmed the bar appeared blue/green. The resumed boot helper's process state was checked and was sleeping normally, not stopped.

The correction is now automatic for the measured activated format (packed truecolor 32 bpp, red/green/blue fields at 16/8/0 and alpha at 24, all 8-bit fields). Other supported formats continue to use their reported fields unless the explicit swap test is requested. White and opaque alpha remain unchanged. The previous delivered image is saved in `build/green-orange-confirmed/`. The rebuilt color-corrected image requires a new RECOVERY reflash; no phone partition was written during this investigation.


## On-device touchscreen terminal

The read-only input report identified `sec_touchscreen` as event2 with multitouch capabilities. The new static framebuffer terminal queried X 0–720 and Y 0–1280 from the live input API, opened a PTY and started a local interactive BusyBox shell. The first three-minute RAM-only trial completed with 89 keyboard presses sent to the shell, 935 shell output bytes, and helper exit status 0. The user explicitly confirmed that the touchscreen keyboard and commands worked, but reported a periodic half-second black flash.

The first report is retained as `build/phone-terminal-first-test.txt`. The renderer initially cleared and repainted the entire shared framebuffer on cursor blinks. It was changed to repaint only changed cells and keys. A traced-pixel sanitizer test verifies that a static cursor blink writes only within its cell. The second RAM-only trial checks the physical result. The rebuilt recovery starts the local terminal automatically while keeping USB separate; shell exit restarts the local shell, and unavailable touch/PTY setup falls back to the heartbeat. No bootloader work or phone partition writes occurred during these trials.

The user confirmed during the second trial that black flashes were gone and the keyboard still worked. The terminal and touchscreen path are now physically confirmed in RAM. The latest archive's automatic startup still needs a RECOVERY reflash/reboot check.

The second three-minute trial completed cleanly with 39 key presses, 329 shell output bytes, and helper exit status 0. The final embedded helper and RAM-tested helper are byte-identical (SHA-256 `59a6c88e11c834683eace46eda0bf38807bfd4ba588394a24cba440a4d510ef3`). All 27 Python tests, framebuffer/terminal sanitizer checks, incremental-write tracing, and real PTY AArch64 execution checks passed. The terminal archive SHA-256 is `086f340a4254cc6a79b0ff000f7475e6b41ec0ffef27fddb841954f53e954055`, identifying the host artifact rather than a phone partition read-back.


## Power menu dry run

The user requested a long-press Power menu as the first of three new milestones, with loader/system placement and Alpine to follow separately. A 1.2-second physical Power hold now opens Power off, Download mode, Reboot system and Cancel. The user confirmed that all buttons respond and Cancel returns to the terminal during a RAM trial with reboot calls blocked. Actual reboot/power-off destinations remain untested. No loader work or system installation was performed.

The timed power-menu trial completed with helper exit status 0, 40 keyboard presses and 859 shell output bytes. The helper discovered KEY_POWER on `/dev/input/event6` and logged two menu openings. The report is `build/phone-power-menu-test.txt`. The user confirmed the buttons and Cancel behavior; the captured log contains no action-dispatch lines, so individual action dispatch remains supported by host checks rather than a captured hardware dispatch. All 27 Python tests and native/AArch64 terminal checks passed. Actual reboot destinations remain untested.


## Internal loader validation and DATA layout

The user confirmed the power menu works and selected a future dedicated Linux root on all of DATA. Read-only live discovery measured BOOT at 32 MiB, RECOVERY at 38 MiB, SYSTEM at 3 GiB and USERDATA at 11.1171875 GiB. The current USERDATA filesystem signature was not recognized by the read-only probe; this alone does not establish encryption or corruption. No block partition was mounted or written. Reports: `build/phone-internal-layout.txt` and `build/phone-data-signature.txt`.

The new `boot-manager` validation component was uploaded into a temporary RAM file, checked by SHA-256, run in inspect mode, and removed. It correctly discovered the agreed BOOT/DATA layout and returned status 0. `/proc/mounts` afterward contained only rootfs, proc, sysfs, devtmpfs, devpts and tmpfs. `build/phone-loader-inspect.txt` records this trial. Candidate-root mounting/validation/cleanup is host-fixture-tested, not hardware-tested; system execution and PID 1 handoff are not implemented in v0.1. All 37 Python tests and the existing native/AArch64 checks passed. The new recovery artifact preserves the original kernel, DTBH/DTB and boot parameters; it was not flashed during this work.


## Alpine 3.24.0 base userspace in RAM

The SHA-256-pinned, release-signature-verified AArch64 minirootfs was uploaded through the existing USB shell in checked chunks and extracted into a 64 MiB tmpfs. The phone's 3.18.140 kernel successfully ran Alpine 3.24.0's dynamic BusyBox 1.37.0, musl linker, APK 3.0.6-r0 and shell/file/pipeline tests inside a bounded chroot. APK's installed-package listing succeeded despite absent cached repository indexes. No packages were installed and no network connectivity was tested.

`build/phone-alpine-ram-test.txt` contains PASS, chroot exit 0 and cleanup success markers; its final mount table shows only the original virtual/RAM mounts. The trial did not replace PID 1 or mount any storage partition. The supplied inittab invokes absent OpenRC and tty1–tty6 gettys; full boot requires a phone-specific init configuration and separate RAM handoff trial. See `docs/alpine-ram-trial.md` and `build/alpine-provenance.json`. The recovery image did not change in this milestone.


## Prepared BOOT/DATA installer and isolated PID 1 handoff

The live original BOOT partition was read in bounded USB chunks and its 32 MiB host copy matched the phone's SHA-256. Its load addresses/page/header were inspected before creating the custom BOOT image. The stock signing footer is preserved in the restore backup, not copied into modified output. The known recovery kernel and complete DTBH are unchanged in the custom BOOT.

A correction to the DATA probe moved its private device node from nodev `/tmp` to RAM `/dev`; DATA is recognized as ext4. The earlier unrecognized result did not establish encryption/corruption. No physical DATA mount/write occurred.

A private mount/PID/UTS namespace ran the BOOT loader's virtual-mount move and switch_root into Alpine BusyBox init as PID 1 on a 64 MiB RAM-backed ext4 filesystem. Phone startup and APK after handoff passed. The initial harness stalled because /proc/task/children is unavailable; it was safely cleaned and corrected. The final trial completed handoff and automatic cleanup, with only the original virtual/RAM mounts remaining. Report: `build/phone-system-handoff.txt`.

The full DATA image passes read-only e2fsck, exact sparse roundtrip, legacy ext4-feature/UUID/capacity validation, and strict archive/hash checks. All 54 Python tests plus native/AArch64 checks passed. The flasher was exercised in preview only; its failure-stop/target guards have host tests. Normal BOOT route, DATA flashing, full persistent UI/USB startup and read-back are not yet hardware-confirmed. See `docs/system-flashing.md`.


## First DATA upload failure and rescue recovery restored

The user ran the BOOT/DATA installer. Its first USERDATA upload failed at connection close (`Fail request receive -1`), and the script stopped before BOOT. The phone displayed its software-update error screen; the recovery key sequence initially returned to that screen. The user then successfully flashed only the verified custom recovery archive and confirmed the rescue terminal opens again.

A read-only USB check measured the full BOOT hash as `c5fda1d67a40deaff6d4c8836d5eea7329222b9b1079db0520ded70c4ea27196`, equal to the original BOOT backup. DATA's start and ext4 UUID region are zero, and no ext4 signature is recognized. No physical partition was mounted or written by this check; its report is `build/phone-flash-failure-check.txt`.

Comparison with the supplied J701F stock userdata image found a Samsung sparse 32/16-byte RAW/DONT_CARE profile with chunk extension 0x55ca, while the rejected image used generic 28/12-byte headers and FILL. Compatibility is a plausible cause, not independently proved. The host DATA image has now been repackaged in that measured profile with every allocated ext4 block transmitted as RAW. Source ext4 and BOOT payloads are unchanged; only DATA transport packaging changed. Host fsck and exact sparse decode comparison pass, along with all 58 Python tests. The revised sparse DATA upload and normal BOOT route remain untested. A DATA-only staged flasher option and read-only USB startup-file checker are prepared for the next trial. See `docs/system-flashing.md`.


## Installed DATA read-back passed

The user ran the read-only installed-system checker after the staged DATA trial. The saved report `build/phone-installed-system-check.txt` identifies the project ext4 filesystem (`BURAK_LINUX`, UUID `4ce26b55-8a59-4fb7-aad4-919a5c2cefeb`), validates the internal MMC/layout and root/init structure, and verifies all 14 startup-file SHA-256 values against hashes extracted from the prepared raw image. Cleanup returned `READBACK_RAM_CLEANUP_OK`.

This confirms the Linux filesystem and checked startup files are installed on DATA. The user did not supply the most recent Odin exit transcript; the installation evidence here is the actual read-back. This does not prove every partition byte, all filesystem contents or normal BOOT behavior. BOOT installation is the next staged action; the agent has only verified its BOOT-only preview and has not executed it.


## Normal Alpine boot from DATA confirmed

After the BOOT-only installation step, the user reported Alpine release 3.24.0, PID 1 named init and the 3.18.140 AArch64 kernel. A subsequent read-only USB capture independently confirms `BURAK_ALPINE_0_1`, BusyBox `/bin/busybox` as PID 1, hostname `burak-linux`, and the full kernel string `3.18.140-SIMPLE-KERNEL_V1.0`. DATA is mounted as `/` from `/dev/j701f-linux-root` with ext4 `rw,relatime,data=ordered`. `df -h /` reports 10.9G filesystem capacity, 8.4M used and 10.8G available. The startup log says Alpine 3.24.0 started as PID 1. The USB root shell works in the normal booted system. Report: `build/phone-normal-boot.txt`.

The first BOOT → Linux loader → DATA ext4 root → Alpine BusyBox init boot is now confirmed. This keeps the previously verified recovery kernel/DTBH and the existing Samsung early boot chain. The phone still needs independent checks of persistence across another reboot, normal-system power-menu destinations and network connectivity/package installation; those results are not implied by this first successful boot. The recorded checks refer to the current image hashes in `build/system/verification.json`; newly rebuilt images need their own hardware verification.


## Read-only peripheral driver inventory

The normal Alpine system exposes Broadcom DHD wlan0 (down, with expected Wi-Fi firmware directory absent), Mali-T83x /dev/mali0, an ALSA Universal7870-I2S card, battery/charger telemetry, accelerometer/proximity entries, an SD device and Exynos camera/JPEG/scaler/MFC nodes. Bluetooth has a software-blocked Broadcom rfkill device but no enumerated HCI controller. DRM is disabled in the embedded kernel config; the framebuffer terminal uses CPU rendering and does not establish GPU acceleration. Wi-Fi connection, audio playback/record, Bluetooth pairing, sensor readings, camera capture and accelerated media remain untested. Reports and next-step distinctions are in `docs/driver-status.md`.

## Wi-Fi milestone (2026-10-07)

Normal Alpine now has working WPA2 Wi-Fi, DHCP, DNS, NTP and HTTPS package-index access using the existing kernel and matched Samsung BCM43438 firmware. The laptop can reach the phone over Wi-Fi. Automatic startup and reconnection across a subsequent normal reboot passed. See [Wi-Fi details](wifi.md) and `build/phone-wifi-test.txt`. SSH was enabled in the next milestone below.

## SSH milestone (2026-10-07)

OpenSSH is now supervised by the existing BusyBox init. Authenticated login as the regular user `burak-alpine` works using the laptop’s existing SSH key. See [SSH setup](ssh.md). OpenRC is installed but not integrated into this custom boot path.

Wi-Fi and SSH returned automatically after the CPU-parameter trial's normal reboot. DHCP changed the address from `192.168.1.139` to `192.168.1.140`; the host key was unchanged.

## Administration and CPU hotplug (2026-10-07)

The user-approved passwordless sudo rule is installed and verified over SSH. Neovim, Git, GCC, musl-dev and Make are installed. Eight CPU cores are present, but CPU4 startup is vetoed alongside zswap compressor allocation failures. A short workload reproduced this; it is separate from the SSH user’s original permissions. A temporary maximum of four CPUs stops repeated failed hotplug attempts for this boot only. See [administration and CPU diagnosis](admin-cpu.md).

The subsequent BOOT-header trial did not deliver `zswap.enabled=0` into `/proc/cmdline`, so zswap stayed enabled. The original working BOOT was restored with full-partition SHA-256 verification. This did not fix CPU hotplug or require a kernel replacement.

## First Qt GUI trial (2026-10-07)

Qt Widgets and QTermWidget were installed and compiled natively on the phone. The application provides a graphical PTY terminal running as `burak-alpine`, a touch keyboard, directory browser and status page. It uses Qt software raster rendering and the measured Samsung framebuffer/touch interfaces; it does not establish GPU acceleration or Plasma/KWin support.

The offscreen PTY/screenshot test passed. The first physical timed trial initialized framebuffer and touchscreen successfully, exited cleanly and resumed the original terminal. The user confirmed the GUI and touch work but reported substantially slower response than the native terminal. Redraw optimization reduced measured idle CPU use from approximately 96% of one core to 4.6%. The revised three-minute trial also exited cleanly and resumed the original terminal; the user's second-trial responsiveness feedback is pending. See [GUI details](gui.md). The native terminal remains the normal startup interface.

On 2026-10-08, the user confirmed that the revised GUI is fast overall, with some delay confined to its graphical terminal. Subsequent offscreen measurements identified whole-interface rendering as the largest component. Partial rendering and deferred event scheduling reduced median PTY-to-image latency from 78.51 to 16.33 ms across 48 samples per behavior using the same binary. Full-image pixel comparisons passed 29 frames and eight automated widget interactions, and passed again during installation. The revised manual GUI is installed with the previous files backed up; startup is unchanged. These checks excluded framebuffer presentation and physical touch. The remaining hardware feel needs a supervised trial; no CPU hotplug or GPU fix is claimed. See [latency evidence and limits](gui.md#terminal-latency-measurement-and-revision).

## Source kernel builds and Panfrost target (2026-10-08)

The user chose Mesa Panfrost and requested kernel building. Two local cross-builds completed: the related SIMPLE vendor baseline `3.18.140-BURAK-BASELINE-01` and Exynos7870 mainline research target `6.15.0-BURAK-PANFROST-01`. The baseline DTBH exactly matches the supplied working table. The mainline build includes linked Panfrost and Exynos DRM code and compiled five related-board DTBs, but has no J701F board tree. The live phone's vendor device tree was copied read-only through temporary RAM and saved as a board-port reference; cleanup passed.

Artifact checksums, AArch64 headers and three focused header tests passed. Neither target was flashed or hardware-booted; the phone keeps the original kernel and recovery. A J701F-specific board tree, boot-handoff checks and diagnostic userspace are required before a mainline boot trial. See [kernel builds and next steps](kernel-build.md).

## J701F diagnostic preparation (2026-10-08)

The measured live DT now has a non-identifying hardware manifest. A local J701F diagnostic tree compiled without dtc warnings against the pinned Linux port. Checks verify the two measured RAM banks, 13 vendor reservations plus a conservative debug-memory envelope, matching PSCI IDs and regulator limits, and disabled MMC/GPU. Three negative tests reject missing modem protection, accidental eMMC activation and incorrect memory capacity. USB VDD33=LDO8 remains a related-board wiring hypothesis; panel/touch/Wi-Fi/storage/GPU activation are later stages.

A static configfs ACM initramfs is packaged. The final BusyBox binary executed on the existing phone, all required applets and shell syntax passed, and temporary RAM cleanup was confirmed. The boot init and USB setup were not executed by that check. No phone persistent files, partitions or kernel were changed.

Official U-Boot v2026.01 was pinned and adapted as a Samsung-loaded diagnostic second stage for the measured J701F revision 3. The initial console prototype compiled, but later driver inspection found no matching U-Boot drivers for its enabled Exynos7870 USB wrapper/PHY. It is superseded by a minimal RAM handoff loader with those peripherals disabled; Linux supplies the diagnostic USB console instead.

The guarded loader compiled and was paired with an inline kernel/DT/initramfs FIT. A host-only Samsung-container preview preserves the original DTBH, header fields other than payload sizes/digest, and trailer. Five new payload/container tests pass. The actual C handoff guards accepted two valid property encodings and rejected eleven invalid cases in a host harness with mocked boot APIs. This is compile/packaging/guard evidence, not a kernel boot or USB-driver test. At that preparation stage no phone image was installed; the later authorized trial is recorded below. See [board preparation and remaining milestones](j701f-mainline.md).

## GPU board audit and rendering probe (2026-10-08)

The r28p0 vendor source selected by the running configuration maps the GPU supply to BUCK2. Read-only GPU sysfs reported `power_state=0`, `clock=0`, `vol=662500` and seven vendor ASV/frequency entries. The live GPU power-domain phandle resolves to `pd-g3d@10484000`. The pinned modern port has GPU clock/Panfrost support but no Exynos7870 power-domain provider. Its CMU driver probes independently and accesses gate registers, so the first RAM diagnostic now disables unused G3D/DISPAUD/ISP/MFCMSCL providers as well as their consumers. The disabled GPU's supply is described as BUCK2. The paired artifacts were rebuilt, and two additional DT rejection tests pass.

A new headless Panfrost rendering probe compiled natively on the phone in tmpfs using existing packages. It found no Panfrost DRM render node, then passed an explicitly software-only checkerboard shader/readback test with llvmpipe; cleanup was confirmed. This proves the diagnostic pipeline on Alpine, not hardware acceleration. No screen/input device or persistent phone file was changed. See [Panfrost integration and outstanding power requirements](panfrost-bringup.md).

## First mainline RECOVERY flash (2026-10-08)

The user explicitly authorized flashing during goal work. The complete original recovery was backed up and verified on phone/laptop, matching the known rescue image prefix. The rebuilt Linux 6.15 diagnostic container was flashed into RECOVERY; complete read-back matched the expected partition hash. The original BOOT hash remained unchanged. The native recovery-restart helper acknowledged its request, then USB disconnected. No diagnostic USB console or normal Alpine SSH returned during the 180-second observation, and a subsequent USB/Odin/SSH check found no software control path.

This proves the write, not successful kernel execution. The user subsequently reported red Samsung normal-boot/ramdisk error text. The original recovery was restored successfully through Download Mode; complete BOOT and RECOVERY hashes were verified over its USB shell. A normal restart then returned Alpine 3.24.0 on the original kernel. DHCP changed its address to **192.168.1.141**; pinned-key SSH and both partition hashes were independently verified there. The experimental diagnostic is no longer installed. See [recovery evidence and packaging investigation](j701f-mainline.md#verified-recovery-after-the-rejected-boot). No mainline CPU/GPU/display claim follows from this attempt.

## Second unattended kernel trial — 2026-10-08

The user explicitly accepted that a failed boot could remain unreachable until returning home. The smaller diagnostic image was written only to RECOVERY; its full read-back passed and BOOT remained unchanged. Its recovery reboot produced no diagnostic USB, normal Alpine return or Download Mode during 180 seconds. The phone is currently unreachable and RECOVERY restoration is pending. This does not prove which stage failed or establish mainline CPU/GPU operation. The one unattended attempt has been consumed. See [trial evidence and recovery instructions](j701f-mainline.md#accepted-unattended-smaller-candidate-trial).

## Rescue restored after second trial — 2026-10-08

The user re-entered Download Mode. The hash-verified RECOVERY-only working archive flashed successfully at USB path `/dev/bus/usb/003/054`. Full BOOT and RECOVERY read-back matched their original working hashes over the returned rescue USB shell, and independently over SSH after a normal reboot. Alpine 3.24.0 on the original kernel is reachable at **192.168.1.142**; the second diagnostic is no longer installed.

The first return showed CPUs `0-7` online; follow-up showed `0-3`. Hotplug remains unresolved. The offline C terminal update is compiled and host-tested but not installed or physically validated. See [restoration evidence](j701f-mainline.md#verified-restoration-after-the-second-trial).

## New C terminal installed — 2026-10-08

At the user's request the new terminal was installed atomically in Alpine and flashed into RECOVERY with full read-back and unchanged BOOT. Only the terminal CPIO entry changed. Both recovery and normal boot returned. The user confirmed keyboard, session swipes and scroll work, but reported rapid taps requiring a pause. A separate evdev capture recorded 22 contacts, all reproduced as 22 correct keys by the current parser; this does not prove where the live delay occurs.

A refinement now drains the nonblocking touch queue before framebuffer painting and requests monotonic event timestamps so queued events retain their actual press duration. The handset accepted that clock ioctl; the refined recovery and normal UI booted. Physical rapid typing confirmation is pending. Normal status reports `wlan0 192.168.1.144`; recovery's offline indicator is expected because it does not start Wi-Fi. The full current UI rescue was copied from the handset, hash-verified and packaged separately for restoration. Evidence: `build/ui-v2-install/` and `build/ui-v2-fast-input/`.


## Third kernel trial and current UI restoration — 2026-10-08

The embedded-FIT/empty-Android-ramdisk/stub-DTBH candidate had a corrected nonoverlapping U-Boot BSS layout and passed host guard/container tests. RECOVERY writing and complete read-back passed with BOOT unchanged. The phone stayed at the Samsung logo; no diagnostic USB or normal Alpine appeared in 180 seconds. Kernel execution and GPU acceleration were not verified.

The user entered Download Mode; Odin restored the full current UI rescue. USB independently verified complete RECOVERY `75dd7d3d1a44ea91b9b72afefd21f3eeadcdb828b2e1851d8d6d8b11b4b5da93`, unchanged complete BOOT, exact eMMC CID and the refined UI binary. Normal Alpine 3.24.0/new UI/Wi-Fi/pinned SSH returned at **192.168.1.145** on the original `3.18.140-SIMPLE-KERNEL_V1.0`. Records: `build/kernel/recovery-trial-embedded/`. Physical rapid-input feedback remains pending; restoring the UI is not new evidence for that issue.
