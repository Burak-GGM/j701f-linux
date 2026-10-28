# J701F mainline diagnostic preparation — 2026-10-08

The J701F diagnostic device tree compiles against the pinned Exynos7870 Linux 6.15 source. A source-built U-Boot loader checks the paired kernel/DT/initramfs before handing it to Linux. The first recovery trial exposed no USB console and was recovered manually; original BOOT and rescue were then fully verified and Alpine returned at 192.168.1.141. A second, smaller candidate was tried with the user's explicit acceptance of losing access until returning home. That trial also failed to return. The user subsequently entered Download Mode, and working rescue plus normal Alpine were restored and verified at 192.168.1.142. BOOT remained unchanged; successful mainline execution has not been established.

## Measured board properties

`kernel/j701f-hardware.json` contains a deliberately small hardware manifest from the captured live device tree. It omits chosen/bootargs, serial numbers and MAC addresses. `tools/j701f-board-evidence.py` regenerates it from the ignored local capture. Properties distinguish physical measurements from the modern binding translations.

| Component | Evidence and current diagnostic treatment |
| --- | --- |
| RAM | Measured banks `0x40000000–0x7e3fffff` and `0x80000000–0xbfffffff`; the intervening gap stays excluded. |
| CPU startup | PSCI through SMC; CPU on/off/suspend function IDs match the live tree and the pinned SoC port. Eight CPU descriptions come from that port; this does not prove eight cores will come online. |
| Reservations | All 13 live reserved-memory regions are preserved as `no-map`, including modem, GNSS, TIMA, boot framebuffer and vendor multimedia regions. Reusable vendor pools are conservatively unavailable to mainline during this first trial. |
| Vendor debug memory | A conservative 16 MiB envelope at `0x46000000` covers the live boot argument log addresses through the `0x46f90000` auto-summary allocation. This envelope is a protection policy, not an exact hardware resource size. |
| PMIC | S2MPU05 on HSI2C0 at `0x66`, interrupt on GPA0 pin 2. All 26 exposed regulator names/voltage constraints come from the live J701F tree. Vendor initial-mode enums are omitted rather than copied into a different regulator driver. |
| Keys | Power GPA0-0, Home GPA1-7, Volume Down GPA2-1, Volume Up GPA2-0. Modern active-low flags replace the vendor GPIO flag encoding. Key polarity/pull configuration still needs hardware validation. |
| USB | Controller `0x13600000`, PHY `0x135c0000`, interrupt 230 agree with the port. The Linux diagnostic requests high-speed peripheral mode. **VDD33=LDO8 is a related-board hypothesis, not verified J701F wiring.** A read-only sysfs measurement found LDO8 enabled at 3,000,000 µV with zero reported users; that does not establish its consumer wiring. No VDD10 connection is invented. The modern PHY also requests `vbus` and `vbus-boost` regulators; missing consumer supplies/dummy regulators remain a runtime investigation item. |
| Storage / GPU | All three MMC controllers and GPU are disabled in this first diagnostic tree. The disabled GPU describes the source/runtime-backed BUCK2 supply mapping. Unused G3D, DISPAUD, ISP and MFCMSCL clock providers are also disabled because they probe independently. No automatic block filesystem mount is included in the initramfs. |
| Panel / touch | Vendor EA8061S J7VE panel and Melfas MMS438 at I2C address `0x48` are references for later ports. No substitute panel or touch driver is enabled. |

The original three DTBH entries were also inspected: their static FDT memreserve tables are empty. A sysfs capture cannot show any entries inserted into the live FDT header by firmware; this remains a limitation. No vendor tree is passed unchanged to the modern kernel.

## Build and checks

```sh
python3 tools/build-j701f-dtb.py
python3 tools/build-mainline-initramfs.py
python3 -m unittest discover -s tests -p test_j701f_dtb.py -v
```

The DT builder preprocesses the local board file with the checked upstream source and saves every included-file hash. It does not edit the upstream Linux tree. `build/kernel/j701f-diagnostic/` contains the resulting DTB, preprocessing/dependency output, an empty successful `dtc.log` and a report. The verifier checks the measured RAM banks, all vendor reservations, PSCI IDs, regulator voltage constraints, disabled storage/GPU/unused domain clock providers, GPU register/interrupt/supply mapping, normal restart reason and absence of copied device identifiers or stale initrd pointers. Six negative tests reject unprotected modem memory, an accidentally enabled eMMC controller, incorrect RAM capacity, an enabled G3D clock provider, an unrelated GPU rail and an incorrect normal restart reason. This is focused validation, not complete DT schema checking or hardware proof.

The initramfs contains the already pinned static AArch64 BusyBox, `/init`, a configfs ACM setup script and a local root shell. It mounts only virtual/RAM filesystems. Its configfs setup refuses to replace an existing gadget and accepts exactly one UDC. USB VID:PID `04e8:6860` comes from the known working recovery. The console uses the previously working `setsid getty` approach, waiting for Enter before launching the shell. This is an unauthenticated local development USB root console.

CPIO round-trip and shell syntax checks pass. The binary was executed separately on the running phone in temporary RAM: its checksum, required applets and script syntax passed, then all temporary files were removed. This caught the unavailable `cttyhack` applet; the final archive uses available `getty`. It **did not run `/init`, reconfigure USB or boot mainline**. The report and cleanup evidence are in `userspace-validation-report.json` and `phone-userspace-validation.txt`.

To repeat that limited userspace check against the project-pinned SSH host key:

```sh
python3 tools/validate-mainline-userspace.py --phone 192.168.1.140
```

## Samsung handoff and U-Boot draft

The working kernel Image has `text_offset=0x80000`; the modern Image has `text_offset=0`. The [AArch64 boot ABI](https://docs.kernel.org/arch/arm64/booting.html) requires placement relative to a 2 MiB aligned base and sufficient runtime memory. Changing a header field alone is not a validated way to change how kernel code is loaded.

Official [U-Boot Exynos7870 documentation](https://docs.u-boot-project.org/en/v2026.01/board/samsung/exynos-mobile/exynos7870.html) describes a Samsung-loaded second stage and notes that S-BOOT supplies chosen/memory properties and ignores Android header offsets. That is a documented SoC-family route, not proof for this particular handset. Samsung's early bootloader remains intact.

`kernel/uboot-input.json` pins official U-Boot v2026.01 to commit `127a42c7257a6ffbbd1575ed1cbaa8f5408a44b3`, archive SHA-256 `74cc33ec34d48a7376771336ae5c8c3cd1ded9eb53137c7797d926660c2c0001`. This fixed revision matches the documentation used for the prototype; it is not claimed to be the newest release. The source archive hash is an HTTPS input pin, not a verified release signature.

The local patch adds a `J701F` firmware-prefix match restricted to the measured hardware revision 3, and permits startup without the upstream fastboot/MMC partition-discovery path. The supplied diagnostic board is copied into the temporary U-Boot source tree. U-Boot's bundled SoC tree differs from the Linux port; each compiled internal board tree needs the same measured-property checks.

The first console prototype compiled, but a subsequent source audit found that its enabled Exynos7870 USB wrapper and PHY compatibles have no matching drivers in this U-Boot revision. Compilation did not establish usable ACM. That prototype is retained separately in `build/kernel/uboot-console-prototype/` and is superseded by the RAM handoff loader.

The current loader has no USB console. Its internal tree disables USB, PHY, PMIC I2C and UART, while the separate Linux tree retains the diagnostic USB path. The loader uses a null console and leaves peripheral bring-up to Linux. It disables fastboot/flashing, MMC commands/writes, filesystem-backed environment writes and storage fallback. The SoC Kconfig still selects the MMC core, but no MMC controller is enabled or its DesignWare driver compiled.

For a fresh build, bootstrap the pinned host tool before assembling its paired payload:

```sh
python3 tools/build-j701f-uboot.py --prepare-tools --jobs 2
python3 tools/build-mainline-fit.py
python3 tools/build-j701f-uboot.py --jobs 2
python3 tools/package-mainline-diagnostic.py
python3 tools/validate-ramboot-guards.py
python3 -m unittest discover -s tests -p test_mainline_handoff.py -v
```

The builder uses Clang/LLVM 22.1.8 and an explicit bare-metal AArch64 target. It overrides U-Boot's old `CLANG_FLAGS` assumption so Clang uses its integrated assembler, with LLVM linker/binutils and modern host tools. The Android GCC 4.9 baseline compiler is below this U-Boot revision's supported minimum and is not reused.

The candidate's automatic boot command is `j701f_ramboot`. It requires the matched J701F board, exactly the measured RAM banks, relocation into the free upper-bank tail, and valid Samsung-provided `linux,initrd-start/end` properties. It accepts either 32- or 64-bit properties, requires an aligned FIT entirely beyond the component targets and below the vendor-debug envelope, and verifies its exact size and whole SHA-256 pinned into the loader. FIT component hashes are checked as well. Hash pairing detects changed payloads; it is not a firmware signature or a new secure-boot mechanism. A failed guard stops without a storage fallback.

`build/kernel/handoff/mainline.itb` contains inline kernel, DT and initramfs bytes. The offline layout places the 18,677,760-byte kernel reservation at `0x40000000`, the DT at `0x41200000` with 2 MiB capacity, and the compressed initramfs at `0x41400000`. The source FIT must end below `0x46000000`. At the currently observed Samsung initrd start `0x43000000`, the 18,693,131-byte FIT would fit without overlapping these targets or reservations. That observation is not proof of where firmware will place the new payload; runtime guards use the actual supplied pointers.

The host-only `recovery-mainline-diagnostic.preview.img` uses U-Boot as the Android kernel payload and the paired FIT as the Android ramdisk payload. It preserves the original Samsung DTBH byte-for-byte so S-BOOT can supply its usual metadata. Linux receives its separate modern DT from the FIT. Only the kernel/ramdisk sizes and container SHA-1 change in the original header; the second payload, padding policy and trailer are preserved. The preview is 19,556,368 bytes and fits the measured RECOVERY capacity. No Odin archive or flash command is generated. The preview builder itself performs no installation; the subsequent trial below uses a separately verified RECOVERY-only write.

Five negative tests reject an unsafe RAM plan, misaligned RAM, a truncated FIT, a corrupted kernel payload and an unexpected Android load-address change. A separate host harness executes the actual C handoff guards with real libfdt/SHA-256 and mocked boot/environment APIs: two valid property encodings reach the mock handoff; eleven invalid cases stop before it. These checks are not U-Boot emulation, a real `bootm` test or Samsung/Linux boot proof.

## First authorized RECOVERY flash and boot trial

The user authorized flashing without additional confirmation while working on the goal. Before writing, the exact eMMC identity and RECOVERY major/minor, partition name and capacity were verified. The full 39,845,888-byte working recovery was saved on the phone and laptop; its image prefix matched `build/recovery.img`. Its SHA-256 is `1da3236ff5b3e17be26bf5208961dcab6d512838b69777a7311c5b0465392e63`. A sole-member recovery restore archive is at `build/kernel/recovery-trial/RECOVERY-working-restore.tar`.

The diagnostic `/init` now requests a normal restart 90 seconds after reaching userspace. The DT describes `mode-normal=0x12345670`, matching the vendor `SEC_RESET_REASON_UNKNOWN`. Static BusyBox's reboot applet was checked under AArch64 emulation. This timer cannot recover firmware/loader/early-kernel hangs, and its actual hardware restart path remains unverified.

The rebuilt FIT is 18,693,131 bytes. The installed Samsung-container image remains 19,556,368 bytes, SHA-256 `3283716821ea5a1a52480df19906f3a63cfcb62460ca109903120dbeca3100d7`. `prepare-mainline-recovery-trial.py` verifies its pairing, backups and bounds, creates RECOVERY-only tar files and generates guarded flash/restore scripts. The flash script restores the backup if write/read-back verification fails. The successful complete partition hash is `4bd1aa7bd4171d8231b6aa2e8e92dec393998eab7fdf35af56ff0a39c32f9d46`; BOOT's original hash was verified before and after. DATA was used for staging files, not reformatted or replaced. SYSTEM, PIT, firmware and modem partitions were not written.

The native `reboot-recovery.c` helper acknowledged a Linux RESTART2 request for `recovery`. The USB device disconnected. `observe-mainline-boot.py` watched the exact diagnostic USB serial identity for 180 seconds; none appeared, and normal Alpine SSH did not return. A subsequent check found no Samsung USB/Download Mode device and SSH reported no route to host. These observations do not distinguish S-BOOT rejection, U-Boot failure, an early Linux hang, or failed USB/reset integration. No mainline boot, CPU-hotplug fix or hardware acceleration is proven.

Evidence is in `build/kernel/recovery-trial/`: `phone-backup.txt`, `phone-flash.txt`, `manifest.json`, `reboot-request.txt` and `boot-observation.json`. Normal BOOT is intact. A hardware reset with Power + Volume Down, releasing both when the screen turns off, is the next available route back to it. Do not hold Home/Volume Up for this return, since RECOVERY currently contains the experimental image. Once normal Alpine is reachable, restore the original recovery with the guarded `restore.sh`; if Download Mode is available, the saved RECOVERY-only restore tar provides the Odin route. Early-stage observability must improve before another diagnostic boot is useful.

## Verified recovery after the rejected boot

The user subsequently reported red text transcribed as “could not do normal boot ramdisk...”. This points toward Samsung's image/ramdisk acceptance stage; the incomplete text does not establish an exact size or format rule. Download Mode then appeared at `/dev/bus/usb/003/049`. The verified `RECOVERY-working-restore.tar` was flashed successfully with Odin exit status 0. The rescue USB shell returned on kernel `3.18.140-SIMPLE-KERNEL_V1.0`.

Full BOOT and RECOVERY hashes were checked again through that shell: BOOT remained `0575c65837f1f993b46884dfa69e9ae54ae5d83aae50bcc02c8b97e3f4f3995c`; RECOVERY returned exactly to `1da3236ff5b3e17be26bf5208961dcab6d512838b69777a7311c5b0465392e63`. A normal restart from the restored rescue booted Alpine 3.24.0 as PID 1. DHCP assigned **192.168.1.141**, explaining why the former `.140` SSH checks failed. USB confirmed the new address; SSH then succeeded using the existing pinned host key, and independently confirmed both partition hashes.

Evidence: `odin-recovery-restore.txt`, `restore-usb-inspect.txt`, `restore-usb-readback.txt`, `restore-normal-reboot.txt`, `normal-reboot-usb-state.txt` and `restore-readback.txt` under `build/kernel/recovery-trial/`. Its manifest now records the recovered state. The diagnostic is no longer installed in RECOVERY, and the saved working rescue is active again. The user’s authorization to flash during goal work remains in effect.

The next candidate must address Samsung packaging rather than repeat this image unchanged. The [official Exynos7870 U-Boot procedure](https://docs.u-boot.org/en/latest/board/samsung/exynos-mobile/exynos7870.html) packages `u-boot-nodtb.bin` with a QCDT stub DT, without an Android ramdisk in its example. Our rejected experiment instead put an 18.7 MiB FIT in that slot. This difference warrants investigation; it is not proof of a particular Samsung ramdisk limit or that the stock U-Boot procedure directly supports this J701F.

## Remote investigation and smaller offline preview

The user subsequently stated that they are away from home and cannot manually enter Download Mode if another image fails. No further partition write or restart was performed. `kernel/hardware-trial-policy.json` records this constraint. Trial preparation and `observe-mainline-boot.py --reboot` refuse another hardware trial unless physical recovery access or an independent recovery mechanism has been established. This does not revoke authorization to develop and prepare artifacts.

Read-only SSH confirms the vendor kernel has both S3C2410 hardware and software watchdog support. The pinned vendor reference's `s3c2410wdt_shutdown()` masks reset and stops the hardware watchdog; the software watchdog uses a kernel timer. Opening a watchdog device before reboot therefore is not a verified rescue mechanism across S-BOOT rejection. The running kernel has no exposed kexec support. The existing Linux reboot handler can request `download` while Linux is alive, but neither SSH, the USB shell nor the diagnostic `/init` timer can issue that request when firmware has stopped before Linux. A known-good BOOT backup alone does not provide an automatic way to select or restore it. Watchdogs were not opened, armed or modified during this assessment.

The watchdog reference files and archive-derived hashes, read-only capability output, and packaging comparison are saved under `build/kernel/recovery-investigation/`. The reference source explains why relying on a watchdog is unsafe; its shutdown behavior has not been tested across a reboot on this handset.

| Image | Container bytes | Android ramdisk bytes | Ramdisk representation |
| --- | ---: | ---: | --- |
| Original OrangeFox reference | 32,194,576 | 13,559,951 | LZMA stream |
| Working rescue | 19,179,536 | 546,381 | LZMA stream |
| Rejected diagnostic | 19,556,368 | 18,693,131 | FIT/FDT magic |
| New offline variant | 9,588,752 | 8,725,427 | FIT/FDT magic, with gzip kernel inside |

The new variant compresses only the Linux Image inside FIT. Its verifier bounds decompression to the expected Image length and rejects truncated streams, bad CRCs, trailing data, additional gzip members, expansion beyond the expected length and mismatched decoded bytes. The load plan still reserves the full uncompressed kernel memory. Its separately rebuilt U-Boot loader pins the new FIT hash and verifies compiled gzip support and the decompression capacity. Original failed-trial artifacts and the restored-state manifest remain unchanged.

This is a size experiment, **not a verified fix for the red message**. The smaller variant still uses a FIT rather than an LZMA CPIO ramdisk in the Android slot; kernel compression does not address that outer-format difference. The original OrangeFox reference itself has a large ramdisk, so no arbitrary universal Samsung size limit is inferred. The incomplete red text cannot distinguish a length rule, format check or another firmware-stage failure. The official no-ramdisk/stub-DT route also remains to be adapted and validated separately.

Rebuild the separate offline variant:

```sh
python3 tools/build-mainline-fit.py --kernel-compression gzip
python3 tools/build-j701f-uboot.py --jobs 3 \
  --fit-dir build/kernel/handoff-gzip --artifact-dir build/kernel/uboot-j701f-gzip
python3 tools/package-mainline-diagnostic.py \
  --fit-dir build/kernel/handoff-gzip --loader-dir build/kernel/uboot-j701f-gzip
python3 tools/validate-ramboot-guards.py \
  --fit-dir build/kernel/handoff-gzip --loader-dir build/kernel/uboot-j701f-gzip
python3 -m unittest discover -s tests -p test_mainline_handoff.py -v
```

Twelve payload/layout/container tests pass, along with two valid and eleven rejected cases through the actual C guards. The actual compressed FIT passes verification and a mutated compressed kernel is rejected. All four compared images retain the same original DTBH. The preview SHA-256 is `91241065641783f55a6eeaa1542143492afbb2a9fbdd59f26d00f6ab9a311c35`. It remains `flash_ready=false` and `hardware_boot_tested=false`; no Odin archive was generated for it. Firmware acceptance, actual `bootm` execution, USB and the timed restart remain untested.

## Accepted unattended smaller-candidate trial

The user explicitly selected: “Try now; I accept losing phone access until I’m home.” The policy now permits one attempt with the exact smaller candidate hash, while still recording that physical recovery and independent recovery are unavailable. Its acceptance was consumed before requesting the recovery reboot; it does not authorize repeated unattended trials.

The trial uses the already checked gzip-kernel FIT and matching loader, SHA-256 `91241065641783f55a6eeaa1542143492afbb2a9fbdd59f26d00f6ab9a311c35`. `prepare-mainline-recovery-trial.py` now accepts separate handoff, loader, backup and output paths, preserving the first trial's restored-state history. Artifacts are in `build/kernel/recovery-trial-gzip/`; the phone staging directory is `/home/burak-alpine/j701f-kernel-trial-gzip`.

A verified full rescue backup was copied into the new staging directory. The guarded RECOVERY-only write succeeded. Full RECOVERY SHA-256 became `bf731d6af138a82edaaa1565c4ae35c536462e2ca4cf8c934b1b864ef7acfe40`; the original BOOT hash remained `0575c65837f1f993b46884dfa69e9ae54ae5d83aae50bcc02c8b97e3f4f3995c`. No BOOT, SYSTEM, PIT, early firmware or modem partition was written. DATA received staging files.

The native helper acknowledged RESTART2 with the `recovery` destination. The observer watched for 180.05 seconds. No diagnostic ACM console, normal Alpine return or Download Mode appeared. A final SSH check at the last address returned `No route to host`; Odin listed no device, and the phone's recorded USB topology `3-1` had no enumerated device. The second trial has no new screen-error report. Its failure stage and exact cause remain unknown; the smaller size did not produce an observable working boot.

The observer now discovers a returning normal Alpine address through the exact known USB console and reuses the existing pinned public key. It also checks for Download Mode on the same physical USB port, so an automatic return there could permit restoration. Neither path appeared in this trial. The diagnostic userspace timer did not produce an observed return; that does not establish whether /init executed.

Evidence includes `manifest.json`, `phone-stage.txt`, `phone-flash.txt`, `reboot-request.txt`, `usb-before-reboot.json`, `boot-observation.json`, `final-ssh-check.txt` and `download-mode-check.txt`. The candidate is now recorded in `kernel/rejected-trials.json` to prevent an unchanged repeat. The original first-trial records remain intact.

### Recovery when physical access returns

Try a forced restart with Power + Volume Down, releasing both when the screen turns off, to attempt the intact normal BOOT route. If the error screen returns, enter Download Mode with the established handset key sequence: Power + Volume Down to reset, then Home + Volume Down + Power, followed by Volume Up at the warning screen.

Use the device path actually printed by Odin; its device number may have changed:

```sh
./tools/odin4 -l
# Replace /dev/bus/usb/BBB/DDD with the exact listed phone path:
./tools/odin4 -a build/kernel/recovery-trial-gzip/RECOVERY-working-restore.tar \
  -d /dev/bus/usb/BBB/DDD --reboot
```

The archive has exactly one member, `recovery.img`, containing the verified full working RECOVERY backup. Archive SHA-256: `3dc3bb80bfb6e4f682fd7ff3cea7c629688ffa27f793ffec155db5d11f8920a6`; restored full partition SHA-256: `1da3236ff5b3e17be26bf5208961dcab6d512838b69777a7311c5b0465392e63`. If it boots the rescue after restoration, request a normal restart from that USB shell. If normal Alpine returns directly, use the new trial's guarded `restore.sh` as root to restore RECOVERY and verify both full partition hashes. Do not start another experimental recovery boot before restoring the rescue.

## Verified restoration after the second trial

On 2026-10-08 the user physically entered Download Mode. The same USB topology `3-1` exposed Samsung `04e8:685d` at `/dev/bus/usb/003/054`. The restore archive's SHA-256, sole regular `recovery.img` member, 39,845,888-byte size and full working partition hash were verified before Odin. Its RECOVERY-only restore completed with exit status 0.

The rescue USB shell returned on `3.18.140-SIMPLE-KERNEL_V1.0`. Full read-back verified unchanged BOOT `0575c65837f1f993b46884dfa69e9ae54ae5d83aae50bcc02c8b97e3f4f3995c` and restored RECOVERY `1da3236ff5b3e17be26bf5208961dcab6d512838b69777a7311c5b0465392e63`, including the expected eMMC CID and partition identity. A normal restart returned Alpine 3.24.0 with Wi-Fi at **192.168.1.142**. The existing pinned host key was reused for that USB-discovered address; SSH independently verified both full partition hashes again.

The first normal-return CPU snapshot showed `0-7` online, while the follow-up showed `0-3`. This is an observation of changing vendor hotplug state, not a CPU fix. No kernel code was changed by restoration. No mainline/GPU success follows from this recovery, and the new C terminal remains awaiting its temporary physical trial.

Evidence is in `build/kernel/recovery-trial-gzip/odin-recovery-restore.txt`, `restore-usb-readback.txt`, `restore-normal-reboot.txt`, `normal-reboot-usb-state.txt`, `restore-normal-ssh.txt` and `restore-readback-ssh.txt`. Its manifest now records the restored current state while preserving the failed candidate/observation records. Both rejected candidate hashes remain blocked against unchanged retries.

## UI rescue baseline and next packaging experiment

The user's next requested step was installing the C UI before returning to kernel work. Only the terminal binary changed in the recovery CPIO; original kernel, DTBH, boot addresses and trailer stayed identical. RECOVERY writes passed full read-back with unchanged BOOT. The first new UI and its queued-input/monotonic-clock refinement both booted into recovery, then normal Alpine. The user confirmed keyboard/session/scroll behavior, with physical confirmation of the rapid-input refinement pending. Current normal address: **192.168.1.144**.

The current full RECOVERY hash is `75dd7d3d1a44ea91b9b72afefd21f3eeadcdb828b2e1851d8d6d8b11b4b5da93`. The exact full partition was copied back from the phone and checked. Latest restore: `build/ui-v2-fast-input/RECOVERY-ui-v2-working-restore.tar`; its sole member is the complete working `recovery.img`. This is the current UI rescue baseline for future trials. Earlier recovery backups and failed-trial histories remain separate.

The [official Exynos7870 U-Boot packaging](https://docs.u-boot.org/en/latest/board/samsung/exynos-mobile/exynos7870.html) uses a DT table and does not place a FIT in the Android ramdisk field. The pinned v2026.01 source documentation describes an empty chosen node and zero-sized memory placeholders for S-BOOT to fill. The current website differs in which U-Boot binary/DT it packages; the prototype is explicitly based on the pinned source example, adapted to measured J701F memory bases.

`tools/prepare-sboot-stub.py` prepares an **offline DT table only**, at `build/kernel/sboot-stub/stub-dtbh.img`. It retains the trusted DTBH v2 chip/platform/subtype/revision selection fields for all three ranges (0, 1–2, 3–255), changing only payload offsets/sizes. Each new minimal tree carries matching model metadata, empty chosen and zero-sized memory placeholders at 0x40000000 and 0x80000000. The absent third RAM bank is omitted. Seven tests cover exact baseline round-trip, wrong revision/platform, overlap/truncation, invalid DT length and nonzero tail rejection.

This does **not** establish the cause of Samsung's red error or prove firmware acceptance. The old RAM handoff command requires firmware initrd pointers; the new embedded variant removes that dependency while keeping the old candidates and their failure evidence intact.

## Third candidate: embedded FIT and corrected loader layout

The user authorized flashing a ready kernel candidate on 2026-10-08. The separate candidate is in `build/kernel/handoff-embedded`, with loader artifacts in `build/kernel/uboot-j701f-embedded` and trial/restore records in `build/kernel/recovery-trial-embedded`. The Linux 6.15 Image, diagnostic DT and initramfs are unchanged from the gzip FIT; the outer packaging and second-stage loader changed.

`j701f-embedded-ramboot.c` selects only the linked FIT symbols. It requires the J701F board identity, exact measured RAM banks, a valid previous-stage DT with chosen, and a relocated monitor allocation in upper RAM above 0xb8400000. It verifies that the complete FIT lies inside that allocation, checks its format and SHA-256, and uses the existing lower-RAM component targets. Firmware initrd properties are no longer required or used to select the payload. Failure stops without storage fallback; there is no U-Boot USB console.

The initial build exposed a linker-layout problem: LLD placed `.bss ADDR(.rela.dyn) (OVERLAY)` at address zero. The embedded payload increased the relocated code/data size to 9,107,744 bytes, but the incorrectly linked BSS end was only 38,368. This invalidated both the monitor reservation and ARM64 memory-size header. The new, separate `uboot-aarch64-lld-bss.patch` uses an aligned NOLOAD BSS after the relocation records. Built-symbol checks now prove the code/data, relocation records and BSS order. The corrected monitor covers 9,193,552 bytes and the Image reserves 9,679,472 bytes including the initial stack. This is a confirmed host build defect; it does not prove where either earlier hardware trial failed.

The new container has an empty Android ramdisk, the exact generated 8,192-byte stub DTBH, the corrected loader with the 8,725,427-byte FIT in relocated read-only data, and the original Samsung load addresses/page/cmdline/trailer. Its size is **9,236,496 bytes**, SHA-256 `e7529556990e39d2f1618417aef8c45b420369f9f187d14618009d52f6493cba`. Seven container tests reject changed load parameters, nonempty ramdisk, corrupted embedded FIT, wrong revision, truncation and insufficient monitor allocation. Seven DTBH tests and the twelve existing FIT/memory tests passed. The actual new C guards passed two valid and fifteen rejected host cases; boot/environment APIs are mocked, so these are not runtime boot proof.

The RECOVERY-only flash passed complete partition read-back: `6a28142de1d39a7436b9d5dbc050dfd72fe7d77f8c72fb8d206b1fbfc6b3ff19`. BOOT stayed `0575c65837f1f993b46884dfa69e9ae54ae5d83aae50bcc02c8b97e3f4f3995c`. The current UI rescue backup and its RECOVERY-only restore archive were staged before writing. The third trial's working restore archive is `build/kernel/recovery-trial-embedded/RECOVERY-working-restore.tar`; it restores the complete current UI partition hash `75dd7d3d1a44ea91b9b72afefd21f3eeadcdb828b2e1851d8d6d8b11b4b5da93`.

The native helper acknowledged a recovery reboot. In 180 seconds no diagnostic USB, normal Alpine return or Download Mode appeared. The user reported the Samsung logo remaining on screen, without a red error report. The failure stage is not verified. The candidate is blocked against unchanged retries. The user entered Download Mode at `/dev/bus/usb/003/067`; Odin restored the full new UI rescue with exit status 0. USB read-back independently verified its complete partition hash, unchanged complete BOOT hash, exact CID and installed UI binary. The rescue booted, then a normal restart returned Alpine 3.24.0, the new UI, wlan0 at **192.168.1.145** and SSH using the previously pinned host key. The working kernel remains `3.18.140-SIMPLE-KERNEL_V1.0`. Records include `odin-ui-restore.txt`, `restore-usb-readback.txt`, `restore-normal-reboot.txt`, `normal-usb-state.txt`, `normal-ssh-state.txt` and `manifest.json` in the third trial directory. The write/read-back does not establish firmware acceptance, Linux execution, CPU behavior or GPU acceleration. Normal BOOT and DATA remain unchanged. Physical Download Mode was again required to recover this trial. A subsequent candidate needs stage-level boot evidence before adding more drivers.

## Remaining milestones

1. Confirm USB supplies, firmware DT handoff, Image placement and a usable recovery path for the diagnostic second stage.
2. Supervised RAM boot: `/init`, CPU/RAM, USB ACM and boot logs; retain the known recovery.
3. eMMC enumeration and read-only root validation, then the Alpine handoff on the modern kernel.
4. Actual panel/touch and mainline Wi-Fi integration; restore the on-device development experience.
5. GPU power/clocks and DRM render node, followed by a measured Mesa Panfrost rendering test.
6. KMS/Wayland compositor, then Plasma Mobile and later video/audio/peripheral work.

Current vendor-kernel hotplug and GUI terminal latency remain separate outstanding items. Building a modern kernel does not establish that either is fixed.

The GPU supply/clock/power-domain audit and prepared rendering test are documented in [Panfrost integration](panfrost-bringup.md). The phone's successful software shader self-test is explicitly not hardware acceleration.

<!-- CLAUDE-BEGIN 2026-10-08: written by Claude (Anthropic), not ChatGPT Codex -->
## Fourth trial reading and fifth (logged) candidate — prepared by Claude, 2026-10-08

Fourth trial (`recovery-trial-env-fixed`, candidate `b288b405…161f`, U-Boot environment comment fix): no diagnostic ACM appeared, but normal Alpine returned **by itself** after about 106 s, without Download Mode. That is the first unattended return. It matches the 90 s `/init` reboot timer plus two boots, so mainline most likely reached userspace and only the USB gadget failed. This is an inference from timing, not a log. RECOVERY was restored afterwards per `restore-normal.txt`.

Fifth candidate, **not flashed**: `build/kernel/handoff-logged/recovery-mainline-diagnostic.preview.img`, 9,238,544 bytes, SHA-256 `b9c7aba468649d103829a27356c085661400c5285d651847a959166d1d438e30`; loader in `build/kernel/uboot-j701f-logged`, QEMU trace in `build/kernel/diagnosis-05-logged`. It keeps the fourth candidate's loader path and adds a `simple-framebuffer` on the firmware scanout (0x67000000, 720x1280) plus ramoops at 0x67900000. Two defects in the first draft of `exynos7870-j7velte-logged.dts` were fixed before building:

- `/chosen` had no `#address-cells`/`#size-cells`/`ranges`, so the kernel could not translate the framebuffer `reg` and simpledrm would not have bound.
- bootargs had only `console=ttySAC2`; `console=tty0` is now last, so the kernel log and `/init` output go to the screen.

`build-j701f-dtb.py` now tolerates those three chosen properties. Host results: DT verifier, 2 valid / 15 rejected C guard cases, QEMU reaches the Linux entry boundary, all 104 unit tests pass. Expected on hardware: kernel log text over the Samsung logo within seconds, a USB/PMIC summary at 15 s and 70 s, automatic normal reboot at 90 s. A photo of the screen is the evidence to collect; the USB failure reason should be readable there.

### Fifth candidate trial status (Claude)

The user extended the flashing permission to Claude on 2026-10-08. Preparation done: `build/kernel/recovery-trial-logged/` (manifest, `flash.sh`, `restore.sh`, restore archive `RECOVERY-working-restore.tar` for hash `75dd7d3d…da93`). Live read-only check over SSH at 192.168.1.146: RECOVERY `75dd7d3d…da93`, BOOT `0575c658…995c`. Backup, candidate and scripts are staged on the phone in `/home/burak-alpine/j701f-kernel-trial-logged` with matching hashes (`phone-stage.txt`).

**Not flashed yet.** Claude's tool sandbox refused the remote write command, so the user runs it: `bash build/kernel/recovery-trial-logged/run-trial.sh [phone-ip]`. It runs the guarded write, marks the manifest and starts `observe-mainline-boot.py --reboot`. If `phone-flash.txt` is absent or the manifest still says `prepared-authorized-trial`, the trial has not happened.

The vendor 3.18 kernel has no `/dev/mem` (`CONFIG_DEVMEM` off), so the ramoops region cannot be read back from normal Alpine. The screen photo is the only evidence channel for this candidate.

After the trial: restore with `sudo sh /home/burak-alpine/j701f-kernel-trial-logged/restore.sh` once normal Alpine is back, or Odin with the restore archive from Download Mode; then add the image hash to `kernel/rejected-trials.json` if it failed.

### Fifth candidate result: mainline 6.15 boots on the J701F (Claude)

The user ran `run-trial.sh` at about 20:06 local time; write and full read-back passed (`phone-flash.txt`). Two user photographs of the screen are the evidence (not stored in the repository):

- Eight Tux logos, i.e. eight CPUs online, on `6.15.0-BURAK-PANFROST-01`.
- `simpledrm` bound to `67000000.framebuffer`, fbcon 90x80; colours and geometry look right with `a8r8g8b8`, 720x1280, stride 2880.
- S2MPU05 RTC registered and set the clock; `ttySAC2` console enabled; gpio-keys registered.
- `/init` reached (`J701F_DIAGNOSTIC_INIT_REACHED`); UDC `13600000.usb` exists and configfs reports `Bound diagnostic ACM to 13600000.usb`.
- Only notable messages: PHY `vbus`/`vbus-boost` and dwc3 `vdd10` fall back to dummy regulators; `exynos-clkout` probe fails with -22.
- The phone returned to normal Alpine by itself (now 192.168.1.147), so the DT `mode-normal` restart reason and the 90 s timer work.

So firmware handoff, U-Boot stub, Linux entry, SMP, PMIC I2C and the firmware framebuffer are now **hardware-verified**. The command line on the phone comes from `env_set("bootargs", ...)` in `j701f-embedded-ramboot.c`, not from the DT; the DT `bootargs` edit above is therefore inert.

USB is the open problem: the host kernel log shows the vendor gadget disconnect at 20:06:49 and nothing until normal Alpine re-enumerated at 20:08:43. No attach, not even a failed enumeration, so D+ never showed a pull-up to the host. The PHY driver already forces VBUS-valid. Working hypothesis (unverified): the S2MU005 MUIC at I2C 0x3d on `i2c@13870000` leaves the D+/D- switch open. The vendor driver runs it in manual mode (`CTRL1`=0x13, `SW_CTRL`=0x24 for USB) and opens the switch on shutdown; the pinned 6.15 tree has only the S2MU005 fuel-gauge driver. Vendor reference files are in `build/kernel/vendor-muic-reference/`.

### Sixth candidate: USB/MUIC diagnostic (Claude) — prepared, not flashed

- Kernel rebuilt with `CONFIG_I2C_CHARDEV=y` (`mainline-bringup.config`; `resolved_config_sha256` in `kernel/inputs.json` updated to `190a5b3a…2121`). New Image SHA-256 `183ff2a8…398b`.
- `kernel/dts/exynos7870-j7velte-usbdiag.dts`: logged tree plus `&i2c4` enabled, no client node.
- `tools/i2c-peek.c`: freestanding one-byte I2C read/write helper; built into `build/kernel/j701f-usbdiag/i2c-peek`. `build-mainline-initramfs.py` gained `--helper`.
- `kernel/diagnostic/console-diagnostics` rewritten: prints UDC state, MUIC registers, dwc3 `DCTL/DSTS/GCTL` and LDO8 on screen; then step A writes MUIC `CTRL1`=0x13 and `SW_CTRL`=0x24 (the vendor USB-attach values), step B soft-reconnects the gadget, printing the UDC state after each.
- Candidate `build/kernel/handoff-usbdiag/recovery-mainline-diagnostic.preview.img`, 9,242,640 bytes, SHA-256 `139f32506252492a6d57db1f71628f2d202f2025713eca65b98f52ae1c765f1f`. Guards 2/15, QEMU Linux-entry trace (`diagnosis-06-usbdiag`) and all 104 tests pass.
- Trial directory `build/kernel/recovery-trial-usbdiag/`; files staged on the phone in `/home/burak-alpine/j701f-kernel-trial-usbdiag`. RECOVERY still holds the **fifth** candidate, so `run-trial.sh` there restores the rescue first, then writes the sixth and reboots. The user must run it (Claude's sandbox blocks remote writes).

What to read from the result: if the host sees a USB device after step A, the MUIC is the cause and a small S2MU005 MUIC/extcon driver (or a boot-time register write) is the fix. If the UDC state stays `not attached` and nothing reaches the host, look at PHY power (LDO8 hypothesis, missing vdd10) next.

### Sixth candidate result: MUIC confirmed as the USB blocker (Claude)

The user ran `recovery-trial-usbdiag/run-trial.sh` at about 20:27. Evidence: `boot-observation.json`, `mainline-usb-boot.txt` (full mainline dmesg captured over USB) and two screen photographs.

- Before any write: `UDC 13600000.usb state=not attached`; MUIC `CTRL1(b2)=0x13`, `SW_CTRL(b5)=0x00` (switch open); LDO8 enabled at 3.0 V with dwc3 as user.
- After step A (`SW_CTRL=0x24`): `state=configured speed=high-speed`. The host enumerated `04e8:6860` serial `j701f-diagnostic` as `/dev/ttyACM0` 7 s into the observation and the observer logged `MAINLINE_USB_DIAGNOSTIC_CAPTURED`.
- Step B (soft reconnect) dropped and re-enumerated the device as expected.
- The USB root shell on 6.15 reported CPUs `0-7` online and MemTotal 1,697,856 kB. Phone returned to Alpine at 192.168.1.148.

**Hardware-verified:** mainline USB gadget (ACM console) works once the S2MU005 MUIC routes D+/D- to USB. LDO8 as `vdd33` is consistent with a working link, and the dummy `vdd10`/`vbus` supplies do not block high-speed device mode. A proper S2MU005 MUIC/extcon kernel driver is still missing; the fix below is a userspace stand-in.

### Seventh candidate: USB fix at boot + eMMC enumeration (Claude) — prepared, not flashed

- `kernel/diagnostic/muic-usb-path` (new) applies the two MUIC writes before the gadget is bound; `init` calls it. `init` also honours `touch /run/stay` to cancel the 90 s reboot.
- `kernel/dts/exynos7870-j7velte-emmc.dts`: usbdiag tree plus `&mmc0` exactly as in the pinned tree's a2corelte/j5y17lte/j6lte/on7xelte boards (LDO26 `vemmc`, LDO27 `vqemmc`, no HS200/HS400). `build-j701f-dtb.py --allow-emmc` is the explicit opt-in; without it the verifier and the existing negative test still reject an enabled eMMC. SD/SDIO and GPU stay disabled.
- `kernel/diagnostic/storage-report` (new) writes card identity, bus settings and the partition list (names, sizes) into the kernel log before USB starts, so the observer's dmesg capture contains it. **Nothing is mounted and no block device is opened for writing.**
- `console-diagnostics` now shows the USB and eMMC summary on screen.
- Candidate `build/kernel/handoff-emmc/recovery-mainline-diagnostic.preview.img`, SHA-256 `6decd3379591f5d7e7bd67066ac94826dda42133127c0e5f87cb72c10dab804e`. Guards 2/15, QEMU trace (`diagnosis-07-emmc`), 104 tests pass.
- Trial directory `build/kernel/recovery-trial-emmc/`, staged on the phone in `/home/burak-alpine/j701f-kernel-trial-emmc`. RECOVERY currently holds the **sixth** candidate; `run-trial.sh` restores the rescue, writes the seventh and reboots. User-run.

Next after a good eMMC result: mount DATA read-only from the mainline initramfs, then `switch_root` into the existing Alpine root (needs a modules/firmware plan for Wi-Fi, which the vendor kernel provides today), then panel/DECON and the G3D power domain for Panfrost.

### Seventh candidate result: USB from boot and eMMC enumeration verified (Claude)

User-run at about 20:33; evidence in `build/kernel/recovery-trial-emmc/` (`boot-observation.json`, `mainline-usb-boot.txt`) plus two screen photographs.

- `muic-usb-path` logged `sw_ctrl 0x00 -> 0x24`; the ACM console was present at the observer's first poll and stayed until the timed reboot. UDC `configured`, high-speed.
- `dwmmc_exynos 13540000.mmc` probed; `mmc0: new MMC card`, `mmcblk0: AJTD4R 14.7 GiB`, 24 partitions, boot0/boot1/rpmb present. PARTNAME values match the vendor map (p1 BOTA0, p10 BOOT 65,536 sectors, p11 RECOVERY 77,824 sectors).
- Bus: 8-bit, 1.8 V signalling, **legacy timing at 25 MHz**. No high-speed capability is declared in the DT yet, so storage is slow but correct; `cap-mmc-highspeed`/HS200 are a later, separate change.
- Part of the storage report was dropped by printk rate limiting (`22 output lines suppressed`); write it to a file instead of `/dev/kmsg` next time.
- Phone returned to Alpine at 192.168.1.149.

### Eighth candidate: mainline hands off to the existing Alpine root (Claude) — prepared, not flashed

Goal: run the installed Alpine system (USERDATA, UUID `4ce26b55-…efeb`, `BURAK_ALPINE_0_1`) on 6.15 instead of only an initramfs.

- `kernel/diagnostic/alpine-handoff` (sourced by PID 1) mirrors `system/boot-init`: USERDATA by PARTNAME, blkid UUID/type check, `ro,noload` inspection of version file and init, rw reopen, mount moves, `switch_root /sbin/init`. If any check fails before the moves it returns and the seventh-stage shell plus 90 s reboot stay in effect.
- Alpine's `/bin/usb-debug` only knows the legacy Android gadget, so the handoff bind-mounts `kernel/diagnostic/alpine-usb-debug` over it **from a tmpfs on `/run`**. Nothing on DATA is rewritten; a vendor-kernel boot is unaffected.
- `usb-configfs` now builds ACM + NCM (MACs `02:70:1f:00:00:01` device, `…:02` host). Phone side `172.16.42.1/24`; host side must be given `172.16.42.2/24` (no DHCP server on the phone). `build/phone-ssh-known-hosts` pins 172.16.42.1 to the existing host key.
- `build-mainline-initramfs.py --extra alpine-handoff --extra alpine-usb-debug` selects this stage; without `--extra` the initramfs is the seventh-stage one.
- Candidate `build/kernel/handoff-alpine/recovery-mainline-diagnostic.preview.img`, SHA-256 `1949ce55a810bd60d8b4a5a99ecf39287b236e39b7897d9c94a4d032e138af50`. Guards 2/15, QEMU trace (`diagnosis-08-alpine`), 104 tests pass. The handoff script itself has only had `sh -n`; it is untested until the phone runs it.
- Trial directory `build/kernel/recovery-trial-alpine/`; staged on the phone in `/home/burak-alpine/j701f-kernel-trial-alpine` (including a compiled `reboot-recovery`). `run-trial.sh` restores the rescue, writes the eighth, reboots to recovery, waits for the NCM interface, sets the host address with sudo and saves an SSH check to `mainline-alpine-ssh.txt`. It does not use `observe-mainline-boot.py`.

Known limits on Alpine-on-mainline: **no automatic return** after the handoff (use `reboot`, or Power + Volume Down); no Wi-Fi (`wlan0` absent, vendor driver only); no touch driver enabled; fbcon and `ondevice-terminal` both draw on the simpledrm framebuffer; no `/lib/modules` for 6.15, so everything needed must be built in; eMMC at 25 MHz.

### Eighth candidate result: Alpine runs on Linux 6.15 (Claude)

User-run at about 20:41; evidence `build/kernel/recovery-trial-alpine/mainline-alpine-ssh.txt` and the run output.

- SSH over the NCM gadget to 172.16.42.1 returned `6.15.0-BURAK-PANFROST-01`, Alpine `3.24.0`, CPUs `0-7`, `/dev/mmcblk0p24 / ext4 rw`. The handoff script worked first time; BusyBox init, sshd and the RAM-overlaid `usb-debug` (ACM root shell) run.
- Screen: `ondevice-terminal` exits (no touchscreen input device; only `gpio-keys`) and `display-status` falls back to `fb-heartbeat` on the simpledrm fb0. Expected until a touch driver is enabled (vendor: Melfas MMS438 at I2C 0x48; mainline candidate `melfas_mip4`, not yet configured).
- NetworkManager on the laptop removed the manual 172.16.42.2 address after a while; later run scripts set the interface unmanaged first. Claude then used the ACM shell through `tools/usb-console.py` for read-only inspection.
- ext4 logs `recovery complete` on each boot under both kernels: the project's reboot paths do not unmount the root cleanly. Journal replay has handled it; a clean shutdown path is a to-do.
- Measured under 6.15 via `/dev/mem` (read-only): PMU `0x10484000/20/40/60` (G3D, DISPAUD, ISP, MFCMSCL) all `CONFIGURATION=0xf`, `STATUS=0x3000f`, `OPTION=1`. Every multimedia power domain is left on by S-BOOT. BUCK2 reads 775 mV, enabled.
- Vendor `S5E7870-pmu.c` (in `build/kernel/vendor-pd-reference/`) declares G3D as `BLKPWR(PMU_G3D_CONFIGURATION, 0, 0xF, PMU_G3D_STATUS, 0, 0xF, …)`: same register shape as the mainline `samsung,exynos5433-pd` handler (`local_pwr_cfg = 0xf`, status at +4). That is source evidence for a later power-domain node; it is not needed while the domain stays on.
- `reboot` from the ACM shell returned the phone to 3.18 Alpine at 192.168.1.150.

### Ninth candidate: Panfrost (Claude) — prepared, not flashed

- `kernel/dts/exynos7870-j7velte-gpu.dts`: eMMC/Alpine tree plus `&cmu_g3d` and `&gpu` set to `okay`. The pinned tree's j6lte enables the GPU the same way. `mali-supply = BUCK2` is inherited. No OPP table, no power-domain node, no devfreq.
- `build-j701f-dtb.py --allow-gpu` is the opt-in; default verification and the negative tests are unchanged.
- Candidate `build/kernel/handoff-gpu/recovery-mainline-diagnostic.preview.img`, SHA-256 `0f07388a17795c6b7060d870108405bf1d627044604566b14c200eb2e0d51a11`. Guards 2/15, QEMU trace (`diagnosis-09-gpu`), 104 tests pass.
- Trial directory `build/kernel/recovery-trial-gpu/`; staged on the phone in `/home/burak-alpine/j701f-kernel-trial-gpu` with `panfrost-render-probe` compiled natively against Mesa 26.1.6. `run-trial.sh` restores the rescue, writes the ninth, reboots, sets up the USB network and runs the probe (`--inspect`, then `--render` on `renderD128`), saving `mainline-gpu-ssh.txt`.
- Only `PANFROST_T830_RENDER_PASS` in that file counts as hardware rendering. A hang during CMU G3D or Panfrost probe would stop before the Alpine handoff; recover with Power + Volume Down, or Download Mode and the restore archive if the phone loops into RECOVERY.

### Ninth candidate result: Panfrost hardware rendering verified (Claude)

User-run at about 20:47; evidence `build/kernel/recovery-trial-gpu/mainline-gpu-ssh.txt`.

- `panfrost 11400000.gpu: clock rate = 343000000`, `mali-t830 id 0x830 major 0x0 minor 0x1`, `shader_present=0x1` (single shader core), `[drm] Initialized panfrost 1.3.0 … on minor 1`.
- `/dev/dri`: `card0` (simpledrm), `card1` and `renderD128` (panfrost).
- `panfrost-render-probe --render --device /dev/dri/renderD128` on Alpine 3.24 / Mesa 26.1.6: `EGL_VERSION=1.5`, `GL_RENDERER=Mali-T830 MC1 (Panfrost)`, **`PANFROST_T830_RENDER_PASS: DRM identity, hardware renderer and 4096 shader pixels verified`**.

This proves the narrow path the probe covers: a surfaceless GLES context on the real GPU rendering a 64x64 shader correctly, with the GPU at the firmware's 343 MHz and BUCK2 at 775 mV. It does not prove panel scanout through the GPU, sustained load, frequency scaling, power-domain cycling or suspend/resume. The phone stays on mainline Alpine until `reboot`; RECOVERY holds the ninth candidate.

### Open items after the ninth trial (Claude's suggested order)

1. Touch: enable a driver for the Melfas MMS438 (I2C 0x48) so `ondevice-terminal` works on mainline. Compare the vendor driver's protocol with mainline `melfas_mip4` before choosing.
2. Display: simpledrm only reuses the firmware scanout. A compositor that renders with Panfrost needs either Mesa's kmsro path onto simpledrm (check whether Mesa 26.1 accepts `simpledrm` as a display-only device) or a real DECON + DSI + EA8061S panel pipeline.
3. Wi-Fi: identify the chip and firmware from the vendor system (`docs/wifi.md`), enable `mmc1`/SDIO with its power sequence, and provide firmware; `brcmfmac` is currently a module with no `/lib/modules` on the root.
4. GPU policy: OPP table from the measured vendor ASV values, devfreq, and a `samsung,exynos5433-pd`-shaped G3D power-domain node (register shape confirmed above) once idle power matters.
5. Housekeeping: a kernel S2MU005 MUIC/extcon driver instead of `muic-usb-path`; eMMC high-speed modes; clean root unmount on reboot; a deliberate decision before mainline ever replaces BOOT (RECOVERY is currently the mainline slot and the rescue image is not installed).

### BOOT swap: mainline to BOOT, 3.18 to RECOVERY (Claude) — prepared, not written

The user set the next priority as writing the mainline kernel to BOOT. To keep a fallback that does not need Download Mode, the slots are swapped instead of only overwriting BOOT:

- **Stage 1** (`build/kernel/boot-swap/run-stage1.sh`): on 3.18, `stage1.sh` verifies both partition identities, the eMMC CID and BOOT hash `0575c658…995c`, saves BOOT to `~/j701f-boot-swap/boot-3.18-backup.img`, writes those 32 MiB to RECOVERY and reads them back; BOOT is only read. Then one recovery boot shows whether the 3.18 system starts from the RECOVERY slot. This replaces the ninth candidate in RECOVERY; the UI rescue image is still not installed.
- **Stage 2** (`run-stage2.sh <wifi-ip>`), only after stage 1 is confirmed: `stage2.sh` requires the 3.18 copy in RECOVERY, writes the tenth candidate to BOOT with full read-back (expected partition hash `a7982f46…5217`, automatic restore from the backup file if the write or verification fails), then a normal reboot into mainline and an SSH/Panfrost check over USB networking.
- Tenth candidate: ninth plus `/bin/reboot-recovery` (`tools/reboot-recovery-static.c`) in the initramfs. If the Alpine handoff stops, the 90 s fallback now requests a **recovery** reboot (DT `mode-recovery = 0x12345674`, already in the pinned dtsi), i.e. back to 3.18, instead of looping into BOOT. Image `build/kernel/handoff-boot/recovery-mainline-diagnostic.preview.img`, 9,246,736 bytes, SHA-256 `09eb99dd3187bb0159e2ee7c6270163d2df3d6e2b99400d9a40b6ec67b45c173`; guards 2/15, QEMU trace `diagnosis-10-boot`, 104 tests pass. It uses the same container header as the RECOVERY trials; whether S-BOOT accepts that header in the BOOT slot is **untested** (the 3.18 BOOT image carries name `SRPQD19B006KU` and an empty header cmdline, the candidates do not).
- Fallbacks if BOOT does not start: Power + Home + Volume Up boots RECOVERY (3.18), then `sudo sh ~/j701f-boot-swap/restore-boot.sh`; last resort Download Mode with `build/kernel/boot-swap/BOOT-3.18-working-restore.tar` (sole member `boot.img`, the full verified 3.18 BOOT partition).
- Getting between systems afterwards: from mainline, `sudo ~/j701f-boot-swap/reboot-recovery --execute` goes to 3.18; from 3.18, plain `reboot` goes to mainline.
- Files and hashes: `build/kernel/boot-swap/manifest.json`, `phone-stage.txt`. Normal-boot `/proc/cmdline` before the swap is saved (with the serial number; keep it out of git) in `build/kernel/normal-boot-cmdline-before-swap.txt`.

**Stage 1 verified (Claude, about 20:57):** `STAGE1_RECOVERY_HOLDS_3_18_VERIFIED`; after the recovery reboot the phone runs 3.18 Alpine with Wi-Fi at 192.168.1.152 and `/proc/cmdline` gains `bootmode=2`, absent in the saved normal boot, so S-BOOT started it from the RECOVERY slot. Read-back over SSH: BOOT and the first 32 MiB of RECOVERY both `0575c658…995c`. Stage 2 has not run: the user's first attempt stopped at SSH host-key checking for the new DHCP address before any phone command; the address is now pinned.

**Stage 2 verified (Claude, about 21:00): mainline is the normal boot.** `MAINLINE_BOOT_FULL_READBACK_VERIFIED`, `RECOVERY_3_18_FALLBACK_VERIFIED`; after a plain reboot, SSH over USB networking reports `6.15.0-BURAK-PANFROST-01`, CPUs `0-7`, root `/dev/mmcblk0p24 ext4 rw`, `card0 card1 renderD128` and `PANFROST_T830_RENDER_PASS` (`build/kernel/boot-swap/mainline-boot-ssh.txt`). S-BOOT accepts the candidate container in the BOOT slot.

Current slot layout: **BOOT = tenth candidate (Linux 6.15 → Alpine on USERDATA), RECOVERY = the previous 3.18 BOOT image (same Alpine root, Wi-Fi and touch terminal).** `kernel/hardware-trial-policy.json`, `build/kernel/current-rescue.json` and the older README/boot-chain text still describe the pre-swap layout (BOOT = 3.18, RECOVERY = UI rescue) and are stale on that point. The guarded `flash.sh`/`restore.sh` scripts of the RECOVERY trials check vendor-kernel device numbers and expect the rescue hash, so they will refuse to run in this layout; new mainline images should be written to BOOT from the 3.18 system with a script modelled on `boot-swap/stage2.sh`.

### Eleventh candidate: touchscreen and on-device terminal on mainline (Claude) — prepared, not written

User report after the swap: the terminal UI is gone on mainline and `fb-heartbeat` shows instead. Measured on the phone under 6.15: `ondevice-terminal` exits with `No supported multitouch slot device found` (only `gpio-keys` exists) and `tsp_dvdd` (LDO34) is disabled.

- Kernel: `CONFIG_TOUCHSCREEN_MELFAS_MIP4=y` (`mainline-bringup.config`; `resolved_config_sha256` updated; Image `f98ceb4b…4ebc`). The vendor driver for this panel is `melfas_mms400` (MIP4 protocol, firmware `mms438_j7ve`), so `melfas,mip4_ts` is the mainline match. **Untested on this controller.**
- `kernel/dts/exynos7870-j7velte-touch.dts`: `&i2c1` (vendor `i2c@13840000`) with `touchscreen@48`, interrupt `gpc3-2` level-low, and `regulator-always-on` on LDO34 because the mip4 driver has no supply handling.
- `alpine-handoff` now lowers the console loglevel and unbinds fbcon from the framebuffer just before `switch_root`, so kernel text no longer paints over the terminal. Early-boot messages still appear until that point.
- Heartbeat removal (user request): `remove-heartbeat.sh` replaces the installed `/bin/display-status` with the same file minus the fallback (source `system/display-status`; installed variant differs only in `PATH`) and deletes `/bin/fb-heartbeat`, keeping the old script as `display-status.before` in the staging directory. `ramdisk/bin/display-status`, the rescue image and `tools/build-system.py` are **unchanged** and still include the heartbeat, because the rescue build chain and its tests pin that file; a rebuilt system image would bring it back.
- `tools/prepare-boot-update.py` (new) is the generic guarded path for the swapped layout: it predicts the full BOOT partition hash from `build/kernel/boot-slot.json`, and its `update.sh` refuses to run unless 3.18 is running, the 3.18 image is in RECOVERY and BOOT holds the recorded previous image; a failed write restores 3.18 into BOOT.
- Candidate `build/kernel/handoff-touch/recovery-mainline-diagnostic.preview.img`, SHA-256 `8dda33394e677583ead2294f3700e74712fb461c02630e00828cd87320ce2c67`; expected BOOT partition hash `f8c96025…c0b0`. Guards 2/15, QEMU trace `diagnosis-11-touch`. Tests: 104 run, 1 skipped — `test_corrupt_kernel_in_fit_rejected` now skips when the preserved first-trial FIT predates the rebuilt kernel Image (it compared against the current Image bytes and would otherwise error).
- Staged on the phone (3.18 from RECOVERY, 192.168.1.153) in `/home/burak-alpine/j701f-boot-update-touch`. User runs `build/kernel/boot-update-touch/run-update.sh`.

**Eleventh candidate result (Claude):** written to BOOT with full read-back by the user (`boot-update-touch/phone-update.txt`); the user reports that on mainline the on-device terminal is back on screen and the touchscreen works. `melfas,mip4_ts` therefore drives this MMS438. Heartbeat removal ran in the same script (`phone-heartbeat.txt`). No log capture of the mip4 probe was taken; this rests on the user's observation.

### Twelfth and thirteenth candidates: Wi-Fi on mainline (Claude) — written and verified

The user asked Claude to continue without stopping through display, Wi-Fi and system groundwork up to (not including) Plasma Mobile. From this point Claude also ran the guarded BOOT writes itself; `tools/run-boot-update.sh <name>` (new) drives the whole cycle: reboot mainline → 3.18 through the ACM shell, find the phone on Wi-Fi by pinned host key, stage, run `update.sh`, record `build/kernel/boot-slot.json`, reboot.

- Vendor facts: BCM43438 rev 1 on `dwmmc1@13550000`, WL_REG_ON `gpd3-6`, host wake `gpa2-2` — the same chip and pins as the pinned tree's j6lte, whose `mmc1`/`pwrseq`/`wifi@1` description is copied in `kernel/dts/exynos7870-j7velte-wifi.dts` (`--allow-wifi` opt-in in the DT verifier; mmc2 stays disabled).
- Kernel: `CFG80211`, `BRCMFMAC`, `BRCMUTIL`, `IPV6`, `RFKILL` built in (no `/lib/modules` on the root). Because the built-in driver probes about 0.45 s into boot, the firmware lives in the initramfs: `build-mainline-initramfs.py --firmware SRC:NAME` installs linux-firmware's `brcmfmac43430-sdio.bin` (7.45.98.118) and `.clm_blob`, plus this phone's stock `nvram.txt` as `brcmfmac43430-sdio.txt`. The larger Image moved the FIT's FDT load address to `0x41400000`; the layout is computed and the guards/QEMU trace follow it.
- **Twelfth (`boot-update-wifi`) failed for Wi-Fi:** the SDIO card enumerated (`02d0:a9a6`) but both functions failed to bind with `-110`. Cause, read from `/sys/kernel/debug/gpio`: Claude had added a pinctrl state to `wifi@1` containing `samsung,pin-val = <0>` on `gpd3-6`; it is applied when the SDIO function binds and pulls WL_REG_ON low. j6lte defines those pin groups but never references them. A CLKSEL phase experiment through `/dev/mem` (drive 3 → 2) made no difference and was not kept.
- **Thirteenth (`boot-update-wifi2`) works:** pinctrl reference removed. `brcmfmac … Firmware: BCM43430/1 … 7.45.98.118`, `wlan0` appears, the existing `j701f-wifi` service associates (WPA2) and DHCP gives 192.168.1.156; SSH over Wi-Fi to mainline works (`boot-update-wifi2/mainline-wifi-ssh.txt`). Candidate SHA-256 `a225902753b20bebba49ee89c66f2e45c42d48e56e5e511b36b716fe1eea0348`.
- Touch: with `IRQ_TYPE_LEVEL_LOW` the mip4 driver flooded the log with `Empty packet` (thousands of lines, pushing boot messages out of the ring buffer); the thirteenth build uses `IRQ_TYPE_EDGE_FALLING` as in the binding example and the message is now occasional. The probe also logs `Unknown event format 32896` once; touch input works per the user.
- Open: brcmfmac reports `Default MAC is used, replacing with random MAC`, so the DHCP address changes every boot; `regulatory.db` is absent (world domain).

Display plan: the pinned 6.15 tree has only the Exynos7870 DECON; DSIM and DT nodes are in later kernels. The exynos7870-mainline project's `exynos7870/7.1` branch is v7.1-rc2 plus 11 patches (DSIM MFLUSH_VS, DSIM PLL interrupt, dw_mmc DMA threshold, config fragments, a6lte, two touch WIP). Its GitLab archive downloads too slowly here, so the base will be kernel.org `linux-7.1.13.tar.xz` plus those patches. No mainline driver exists for this phone's panel (vendor `CONFIG_PANEL_EA8061S_J7VE`, files in `build/kernel/vendor-panel-reference/`): 720x1280 video mode, 4 lanes, HS 477 Mbps, PMS 3/220/2, h-porch 48/56/4, v-porch 5/9/2, reset `gpd3-4`, supplies LCD_1P8 and LCD_3P0; init sequence in `ea8061s_j7lite_lcd_ctrl.c`. A panel driver has to be written.

### Fourteenth candidate, session groundwork and accelerated compositor (Claude) — verified over SSH

- **Fourteenth (`boot-update-wifi3`, currently in BOOT):** `local-mac-address = 02:70:1f:57:4c:01` on `wifi@1` (project-chosen, locally administered; EFS is not read) so DHCP stops handing out a new address each boot, and the handoff's `/run` tmpfs is 64 MiB. Verified: `wlan0` reports that MAC; phone at 192.168.1.158.
- **Packages installed on the phone** (apk, signed, over mainline Wi-Fi): `eudev seatd cage foot kmscube` and dependencies (wlroots etc.).
- **`system/start` → `/sbin/j701f-start`** (old copy kept as `/sbin/j701f-start.before-session-groundwork`): on non-3.18 kernels only, it mounts `/dev/shm`, starts `udevd` with a coldplug trigger, the D-Bus system bus and `seatd -g video`, and creates `/run/user/1000`. `burak-alpine` was added to `video`, `input`, `seat`. Verified after reboot: the three daemons run, `/dev/dri/*` and `/dev/input/*` carry `video`/`input` group ownership. The 3.18 fallback path is unchanged by the `case`.
- **GPU output through simpledrm works.** Mesa 26.1.6's kmsro accepts `simpledrm`: `kmscube -D /dev/dri/card0` reports `renderer: "Mali-T830 MC1 (Panfrost)"`, and wlroots (`cage -s -- foot`, as the unprivileged user through seatd) logs `Initializing DRM backend for /dev/dri/card0 (simpledrm)`, `GL renderer: Mali-T830 MC1 (Panfrost)`, `Modesetting with 720x1280 @ 60.000 Hz`, with the touchscreen picked up by libinput. Evidence is log text only; **nobody has yet looked at the screen during these runs**, and kmscube's frame count on simpledrm is meaningless (no vblank, flips return immediately; 600 "frames" in about a second).
- For those tests `ondevice-terminal` and `display-status` were SIGSTOPped and resumed; they are still what init starts on the display. A compositor session needs them replaced in `/etc/inittab` (they also read the touchscreen directly).

Consequence for the roadmap: a real DECON/DSI/panel driver is **not a prerequisite for a first accelerated desktop**. It remains wanted for vsync, brightness, blanking and suspend. Status of that work: only researched (see the display plan above). `kernel/downloads/linux-7.1.13.tar.xz` (158,441,368 bytes) is downloaded from cdn.kernel.org and matches the published SHA-256 `614d95fafdcb5cce2b6620e7edc6afbb606bffd4655405586815d84687841ad7` (checksum only; the PGP signature was not checked). Nothing has been built from it and it is not yet in `kernel/inputs.json`.

**Stopping point agreed with the user: before Plasma Mobile.** Not done and needed for it: choosing the session stack (Plasma Mobile wants a logind provider — elogind — plus a user D-Bus session, PipeWire, polkit; the system still boots with the custom BusyBox init, no OpenRC runlevels), taking `ondevice-terminal` off the display, an on-screen keyboard, and disk/RAM checks (8.9 GiB free, 1.6 GiB RAM, eMMC at 25 MHz). GPU frequency is fixed at 343 MHz.

### OpenRC on mainline and fifteenth candidate (Claude) — verified over SSH

The user chose OpenRC as the base for the Plasma Mobile session stack. The migration is additive and mainline-only; the supervised BusyBox-init entries for display, USB shell, Wi-Fi and sshd are kept, so access does not depend on OpenRC.

- `system/openrc-runlevel` → `/sbin/j701f-openrc`: exits immediately on a 3.18 kernel; otherwise runs `openrc <runlevel>` under `timeout` (60 s, shutdown 30 s), logging to `/run/j701f-openrc-<level>.log` and one status line to `/tmp/boot.log`.
- `system/inittab` → `/etc/inittab` (old copy `/etc/inittab.before-openrc`): after `j701f-start`, `sysinit` entries for runlevels `sysinit` and `boot`, a non-blocking `once` entry for `default`, and a `shutdown` entry before the final `sync`.
- `system/start` → `/sbin/j701f-start` (old copy `.before-openrc`): the manual udev/D-Bus/seatd starts added earlier today are gone again; only `/run/user/1000` creation remains for mainline.
- Runlevels on the phone: `sysinit` devfs procfs sysfs cgroups udev udev-trigger; `boot` machine-id seedrng sysctl loopback; `default` dbus seatd; `shutdown` killprocs mount-ro. The user's earlier `sshd` registration in `sysinit` was removed (the supervised `j701f-sshd` is the only sshd). OpenRC pulls in modules/fsck/root/localmount as dependencies; `modules` only prints a harmless `/lib/modules` warning.
- Verified on two mainline boots: all three runlevels exit 0, services `started`, sshd/Wi-Fi/terminal up. After an OpenRC shutdown the next mount shows **no** `recovery complete`, so the unclean-root issue is fixed for reboots issued on mainline. Reboots from 3.18 and through the `reboot-recovery` helper still skip unmounting and replay the journal.
- 3.18 fallback re-verified with the new inittab: the update cycle booted it from RECOVERY and reached it over SSH.
- **Fifteenth (`boot-update-wifi4`, now in BOOT):** DT `aliases { mmc0 = &mmc0; mmc1 = &mmc1; }`. Without them the SDIO host became `mmc0`, the eMMC `mmcblk1`, and `storage-report` waited its full 10 s on every boot. Now `waited=0s`, root on `mmcblk0p24`, handoff about 3.5 s after kernel start.

Next for Plasma Mobile (not started): replace `seatd` with `elogind` in `default` (plus polkit, a user D-Bus session and PipeWire), install the Plasma Mobile packages, take `display-status`/`ondevice-terminal` out of the mainline display path, and start the session for `burak-alpine`. Alpine's `plasma-mobile` packages assume `rc-service`-managed daemons, which now work.

### User D-Bus session and PipeWire (Claude) — verified after reboot

Division of work agreed with the user: Claude sets up D-Bus and PipeWire; **the user installs Plasma Mobile with apk themselves.**

- Packages: `pipewire wireplumber pipewire-pulse pipewire-openrc wireplumber-openrc pipewire-tools` (1.6.8 / 0.5.15).
- OpenRC **user services** for `burak-alpine` (`~/.config/rc/runlevels/default`): `dbus` (session bus at `$XDG_RUNTIME_DIR/bus`), `pipewire`, `wireplumber`, `pipewire-pulse`. They are started by the system service `user.burak-alpine` (symlink to `/etc/init.d/user`, in runlevel `default`).
- There is no PAM or logind on the system, so nothing sets `XDG_RUNTIME_DIR` for `openrc-user`; it exited 255 silently until `/etc/conf.d/user.burak-alpine` passed `supervise_daemon_args="--env XDG_RUNTIME_DIR=/run/user/1000"`. The directory itself is created by `/sbin/j701f-start`.
- `system/session-profile.sh` → `/etc/profile.d/j701f-session.sh` exports `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` for uid 1000 login shells.
- Verified after a reboot: `user.burak-alpine` started, four user services started, `dbus-send --session … GetId` answers, `wpctl status` shows the PipeWire instance with WirePlumber attached, clean ext4 mount.
- Limits: PipeWire has **no audio device** — the mainline tree has no sound card driver enabled for this phone, so this is the daemon stack only. `rtkit` is not installed (PipeWire logs RTKit warnings and runs without realtime priority). `seatd` is still the seat manager; if the Plasma packages bring `elogind`, only one of the two should own the seat, and the conf.d/profile workarounds above become unnecessary once elogind creates the runtime directory. `display-status`/`ondevice-terminal` still own the screen on mainline.

### Touch regression from the edge trigger, and its fix (Claude) — image prepared, not yet written

The user reported the touchscreen dead on the fifteenth image while `apk add plasma-mobile` was running (316 packages, about 1.1 GiB; 8.7 GiB was free). Measured without rebooting: `/proc/interrupts` shows `mip4_ts` at **1** interrupt 14 minutes after boot and `/sys/kernel/debug/gpio` shows the attention line `in lo`. Claude's switch to `IRQ_TYPE_EDGE_FALLING` (thirteenth image) caused this: the MMS438 leaves the line low, so no second edge ever arrives. The earlier "Empty packet is now occasional" note was really "touch stopped after one interrupt".

Fix prepared as `boot-update-touchfix`: `IRQ_TYPE_LEVEL_LOW` again (the configuration the user confirmed working), plus `kernel/patches/linux-mip4-empty-packet-debug.patch`, which turns the driver's `Empty packet` `dev_err` into `dev_dbg`. `tools/build-kernel.py` now applies `kernel/patches/linux-*.patch` once per extracted tree (marker files next to the source directory). Image SHA-256 is in `build/kernel/boot-update-touchfix/manifest.json`; guards, QEMU trace and tests pass. **Not written yet** — writing needs a reboot into 3.18 and must wait until the user's package installation has finished. Whether level-low re-entry costs noticeable CPU while the screen is touched is unmeasured.

### Plasma Mobile session wired up (Claude, 2026-10-09) — runs at boot; touch state unconfirmed

The user installed `plasma-mobile` (6.6.6, 316 packages incl. sddm, elogind, kwin, plasma-keyboard, NetworkManager) and found that `rc-service sddm start` changed nothing on screen. Causes: the framebuffer terminal still owned the display, `seatd` rather than elogind held the seat, and the DRM/input devices carried no logind seat tags until udev re-triggered after elogind's rules were installed.

- `system/display-select` → `/sbin/j701f-display`, respawned from `/etc/inittab` instead of `/bin/display-status` (old inittab: `/etc/inittab.before-plasma`). 3.18: runs the framebuffer terminal as before. Mainline: idle, unless `/etc/j701f-mainline-terminal` exists.
- Runlevel `default` is now `dbus elogind sddm`. `seatd` and `user.burak-alpine` were removed from it: elogind/PAM creates `/run/user/1000` at login, and the Plasma session brings its own D-Bus (`plasma-dbus-run-session-if-needed`) and PipeWire (`/etc/xdg/autostart/pipewire.desktop`). The OpenRC user services from the previous section remain defined but are no longer started at boot.
- `system/sddm-autologin.conf` → `/etc/sddm.conf.d/10-j701f-autologin.conf`: autologin `burak-alpine` into session `plasma-mobile`, `Relogin=true`. NetworkManager is installed but **not** enabled; Wi-Fi is still the supervised `j701f-wifi` wpa_supplicant service.
- Verified over SSH after a cold boot: `openrc default exit=0`, logind session `c1 … seat0 tty7 active`, `kwin_wayland`, `plasma-keyboard`, `ksplashqml`, `plasma-mobile-initial-start` (first-run wizard) running; about 1.3 GiB RAM free shortly after start. `rc-status` shows `sddm` as `stopped` although its session is up (start-notification quirk; not investigated). KWin's renderer was not confirmed from logs. **Nobody has reported what the screen shows.**
- The `touchfix` image is in BOOT (`boot-update-touchfix`, level-low + Empty-packet patch). Measured afterwards: the attention line still reads low permanently and `mip4_ts` takes about **5,500 interrupts per second** while idle (about 1 % of one core in the IRQ thread). The probe still logs `Unknown event format 32896` (0x8080) and packet-info reads return `0x80` (alert bit, size 0), also after an unbind/bind long after boot. So the driver/chip handshake is not right: either the alert is never acknowledged or the MMS438 firmware differs from what `melfas_mip4` expects. The user saw touch working on the eleventh image, which had the same trigger and very likely the same condition, so touch may work despite the storm — to be confirmed by the user. A real fix needs the vendor `melfas_mms400` interrupt/alert handling compared against the mainline driver (vendor source is in the pinned SIMPLE archive under `drivers/input/touchscreen/melfas_mms400/`).

### Touch root cause and fix (Claude, 2026-10-09) — chip answers correctly; user test pending

The user confirmed the "Welcome to Plasma Mobile" screen is displayed (so KWin output through simpledrm works) and that touch did not respond. Measured on the `touchfix` image: absolute ranges X 0–32768 / Y 0–32896, `fw_version=8000 8080 8080 8080`, empty `ic_name`, no input events — every I2C read returned `0x80`.

Cause: with LDO34 `regulator-always-on` the rail comes up at PMIC probe and `melfas_mip4` queried the MMS438 a few tens of milliseconds later, while it was still booting. The controller then stays in a state where it answers `0x80` to everything and holds the attention line low (the interrupt storm and the earlier "Empty packet" flood were symptoms). The vendor driver enables the supply itself and sleeps 50 ms first. Whether the eleventh image worked by timing luck is not known.

Fix, in BOOT as `boot-update-touchfix2`: `kernel/patches/linux-mip4-vdd-supply.patch` adds an optional `vdd` supply to the driver (enable, 300 ms delay, then query); the DT gives `vdd-supply = <&vdd_ldo34>` and drops `regulator-always-on`. Measured after boot: `ic_name=M4H0`, `fw_version=EEEE 0608 0012 0012`, no `Unknown event format` message, attention line high, **0 interrupts while idle**. Trigger is level-low. Actual touch input in Plasma is for the user to confirm.

### Second touch cause: missing Y resolution (Claude, 2026-10-09) — fixed in BOOT; user confirmation pending

After `touchfix2` the user still had no touch in Plasma. Measured: correct ranges (X 0–720, Y 0–1280) but resolution X = 10, Y = 0, zero interrupts, and **no process had `/dev/input/event0` open**. KWin's log: `Libinput: event0 - MELFAS MIP4 Touchscreen: kernel bug: kernel has only x or y resolution, not both.` libinput rejects such a device; with nobody opening it the driver never enables its interrupt (`IRQF_NO_AUTOEN`).

Live check: setting the Y resolution to 10 through `EVIOCSABS` and restarting the session made `kwin_wayland` and `elogind` hold the device, and the interrupt counter then rose to 608 while the user used the phone. (`rc-service sddm restart` does not work because OpenRC believes sddm is stopped; killing `kwin_wayland` makes sddm relogin.)

Permanent fix, in BOOT as `boot-update-touchfix3`: `kernel/patches/linux-mip4-z-resolution.patch` mirrors the known axis resolution onto the missing one in `mip4_query_device`. After a cold boot: KWin and elogind hold `event0` without intervention, no "kernel bug" line in the session log, `ic_name=M4H0`, idle interrupt count 0. Three local mip4 patches now exist (`linux-mip4-empty-packet-debug`, `-vdd-supply`, `-z-resolution`); they are applied in file-name order.

### Plasma shell start: Xwayland was missing (Claude, 2026-10-09) — shell processes verified

User reports: touch works in Plasma (KWin logs touch coordinates); the lock screen asked for a PIN — the `burak-alpine` password was a random one nobody recorded, so the user was told to set one with `sudo passwd burak-alpine` (Claude did not set or see it). After login: KDE splash, then a black screen.

Cause: `plasma_session` was running but neither `ksmserver` nor `plasmashell` existed. `ksmserver` uses the Qt `xcb` platform and failed with `could not connect to display`; KWin had logged `kwin_xwl: /tmp/.X11-unix does not exist` and Xwayland was not installed. `plasmashell` itself started fine when launched by hand in the session environment.

Fix: `apk add xwayland` (`xcb-util-cursor` was already present) and `/sbin/j701f-start` now creates `/tmp/.X11-unix` (mode 1777) on mainline (`system/start` updated). After the next boot `Xwayland :0`, `ksmserver --no-lockscreen` and `plasmashell` are running; about 660 MiB RAM reported available with the shell up. What the screen shows is for the user to confirm.

Other session-log noise seen and not addressed: no cursor theme / Breeze decoration plugin, no UDisks2, no ModemManager, no `org.freedesktop.locale1`, `/dev/fuse` absent (document portal), PipeWire screencast context not connected, RTKit absent.

### Plasma Mobile in use; power key, navigation and open items (Claude, 2026-10-09)

The user confirms Plasma Mobile works: home screen, touch, and the `foot` terminal opened from the shell.

- **Unexpected "reboots" were the power key.** Twice an SSH session was closed by the phone and uptime restarted; Claude first suspected a crash (pstore at `0x67900000` was empty after the restart, so RAM does not survive that path). The user then reported that one short press of the power key shut the system down and they powered it on again: elogind's default `HandlePowerKey=poweroff`. Fixed with `system/elogind-powerkey.conf` → `/etc/elogind/logind.conf.d/10-j701f-powerkey.conf` (`HandlePowerKey=ignore`, long press powers off); `busctl` shows the manager property as `ignore` after a SIGHUP. Interrupted by such a shutdown: the user's `apk add firefox-esr` (not installed afterwards).
- Navigation: Plasma Mobile is gesture-driven by default (swipe up from the bottom edge). `qdbus6 org.kde.plasmashell /Mobile org.kde.plasmashell.openHomeScreen` returns to the home screen from SSH (needs the session's `DBUS_SESSION_BUS_ADDRESS`, read from `/proc/<plasmashell>/environ`). The phone's capacitive back/recents keys (vendor `coreriver,tc300-keypad` at I2C 0x20 on `i2c@13850000`) have no driver enabled in the mainline build; the physical Home key reaches the kernel through `gpio-keys` (`KEY_HOMEPAGE`) but is not bound to anything in Plasma.
- `apk add plasma-workspace-wallpapers breeze` was started at the user's request and was still downloading when this note was written (the link runs at about 40 KB/s); check `apk info -e plasma-workspace-wallpapers breeze`.
- **No thermal or frequency management on mainline:** `/sys/class/thermal` has no zones, there is no cpufreq policy and no power-supply device, although `EXYNOS_THERMAL`, `CPUFREQ_DT` and `S3C2410_WATCHDOG` are built. The CPUs run at whatever frequency the bootloader left, with no throttling and no battery reporting. No overheating has been observed, but nothing would act on it.

### Remote screenshots and wallpaper (Claude, 2026-10-09)

The user is away from the phone and works through remote control until they are home: **no physical access, so nothing that could leave the phone unbootable or off the network should be done until they say otherwise** (no new BOOT images, no changes to Wi-Fi, sshd, init or the session start path).

- Wallpapers: `plasma-workspace-wallpapers` and `breeze` are installed (37 entries in `/usr/share/wallpapers`); `plasma-apply-wallpaperimage /usr/share/wallpapers/Next` was applied.
- Screenshots without Spectacle: `tools/kwin-screenshot.c` (libdbus) calls `org.kde.KWin.ScreenShot2.CaptureWorkspace` and writes raw `ARGB32_Premultiplied` pixels (720x1280, stride 2880, QImage format 6). On the phone it is built as `~/.local/bin/kwin-screenshot` and authorised by `~/.local/share/applications/j701f-kwin-screenshot.desktop` (`X-KDE-DBUS-Restricted-Interfaces=org.kde.KWin.ScreenShot2`). elogind's `busctl` cannot pass file descriptors, which is why a helper was needed. The host converts raw → PNG with a few lines of Python.
- First capture showed the lock screen. To capture the home screen Claude ran `sudo loginctl unlock-session <id>` (the user asked for the screenshot; their password was not used or seen). Results: `build/screenshots/plasma-mobile-lockscreen.png` and `plasma-mobile-home.png` — status bar, Foot and Settings icons, navigation panel with three buttons, "Next" wallpaper. This is the first direct visual evidence, from KWin's own framebuffer, of the Plasma Mobile session on the phone.

### Plasma usability packages and the missing action drawer (Claude, 2026-10-09) — in progress

User requests while away: install what Plasma needs for normal use, and add the swipe-down control centre if it is still missing. The user also said risky kernel flashing is allowed remotely **only when they explicitly say so** (they will repair at home if it goes wrong); no such instruction has been given yet.

- The action drawer does not open: `qdbus6 org.kde.plasmashell /Mobile org.kde.plasmashell.openActionDrawer` leaves `isActionDrawerOpen` false and screenshots show no drawer, although the top panel containment (`org.kde.plasma.mobile.panel`) and the quick-setting packages exist. Session log: `module "org.kde.plasma.private.batterymonitor" is not installed` (caffeine quick setting). Missing before this step: `powerdevil bluedevil kscreen polkit-kde-agent-1 udisks2`. Cause not established; the first attempt is installing those.
- **Suspend is disabled first:** `system/elogind-nosleep.conf` → `/etc/elogind/sleep.conf.d/10-j701f-nosleep.conf` (`AllowSuspend=no` etc.); logind now answers `CanSuspend "no"`. Reason: powerdevil could suspend an idle phone, resume is untested on this kernel, and the user has no physical access.
- Started on the phone in the background: `apk add powerdevil bluedevil kscreen polkit-kde-agent-1 udisks2 rtkit qmlkonsole kclock kalk font-noto-emoji` (183 packages, about +258 MiB installed; log `/var/log/j701f-apk-plasma.log`). After it finishes the session must be restarted (`sudo kill $(pidof kwin_wayland)`) and the drawer re-tested with `tools/kwin-screenshot.c` + `tools/raw-to-png.py`.
- Not installed on purpose because of the slow link: a QtWebEngine browser (Angelfish), Discover, a file manager. `firefox-esr` is the user's own pending install.

### Queued work and prepared-but-unwritten kernel changes (Claude, 2026-10-09)

- On the phone, `apk add firefox-esr` is queued behind the running Plasma package installation by a root `nohup` waiter (log `/var/log/j701f-apk-firefox.log`). The user's own earlier Firefox attempts never completed; no Firefox apk process was running when they asked to cancel it.
- `kernel/dts/exynos7870-j7velte-wifi.dts` now overrides the Home key to `KEY_LEFTMETA` (Plasma Mobile's home action; gpio-keys has no scancodes, so a udev hwdb remap is not possible). **Source only: no image has been built or written with it.** The current BOOT image is still `touchfix3`.
- Capacitive back/recents keys: vendor node `coreriver,tc300-keypad` at 0x20 on `i2c@13850000`, firmware `tc350k_j7ve`, `use_bitmap = 1`, interrupt `gpa1-4`, supply `vtouch_2.8v` (fixed regulator on `gpd1-6`). Mainline `tm2-touchkey` (`coreriver,tc360-touchkey`) reports a keycode per event rather than a bitmap, so it may not match; `CONFIG_KEYBOARD_TM2_TOUCHKEY` is off. Not attempted while the user has no physical access.
- Kernel writes remain on hold until the user explicitly asks for one.

### Action drawer works; packages and Firefox installed (Claude, 2026-10-09)

- Installed and verified with `apk info -e`: `powerdevil bluedevil kscreen polkit-kde-agent-1 udisks2 rtkit qmlkonsole kclock kalk font-noto-emoji`, then `firefox-esr` (140.12.0) from the queued waiter. 6.9 GiB free before Firefox.
- **The swipe-down control centre opens.** `tools/inject-swipe.py` writes a single-finger swipe into `/dev/input/event0` (evdev injection as root; the kernel has no uinput); a swipe from y=6 to y=800 gives `isActionDrawerOpen = true` and `build/screenshots/action-drawer-swipe.png` shows the quick-settings grid (Wi-Fi, Bluetooth, Sound, Battery 0 %, Screenshot, Shut Down, …). The D-Bus method `openActionDrawer` emits `openActionDrawerRequested` but does **not** make the drawer visible, so Claude's earlier "it does not open" result came from an invalid test. Whether the drawer was already reachable by swipe before the extra packages is not known; the user had reported it missing.
- Restarting the session: killing only `kwin_wayland` makes the wrapper restart KWin but leaves the session without `plasmashell`/`ksmserver`. What worked: kill the user's session processes (`startplasmamobile`, `plasma_session`, `kwin_wayland`, …) with `pkill -u burak-alpine -f …`; sddm then relogs in. `org_kde_powerdevil` now runs; logind still answers `CanSuspend "no"`.
- KWin support information: `Compositing Type: OpenGL ES 2.0`, `OpenGL renderer string: Mali-T830 MC1 (Panfrost)`, Mesa 26.1.6 — the compositor is GPU-accelerated.
- Quick settings that cannot work yet on this kernel: Battery (no power-supply device), Sound (no sound card), Mobile Data, brightness. Wi-Fi shows "Off" because NetworkManager is not running; the connection is the supervised `j701f-wifi` service.

### Migration to Linux 7.1 started (Claude, 2026-10-09) — host work only so far

Decision with the user: move the mainline base from the pinned 6.15 branch to 7.1 now, because the remaining hardware work (DSI/panel in particular) lives in newer kernels and little 6.15-specific work has accumulated. The user accepts remote kernel writes as long as a failure cannot require Odin; they repair anything else when home.

- `kernel/inputs.json`: `panfrost` now points at kernel.org `linux-7.1.13.tar.xz` (checksum verified) with patch globs `exynos7870-7.1/*.patch` then `linux-*.patch`; the previous entry is kept as `panfrost-6.15` and its last artifacts as `build/kernel/panfrost-6.15/`. `tools/build-kernel.py` applies the globs listed in the entry.
- `kernel/patches/exynos7870-7.1/`: six commits fetched from the exynos7870-mainline `exynos7870/7.1` branch (config fragments, DSIM MFLUSH_VS, DSIM PLL interrupt, dw_mmc DMA threshold x2). All six and the three local mip4 patches apply cleanly to 7.1.13. Not taken: a6lte DT, zinitix and rmi4 touch changes.
- `mainline-bringup.config` additions for 7.1: the upstream fragments build DRM, Panfrost, simpledrm, Exynos DRM/DSIM, the USB DRD PHY, ramoops and the S2MU005 fuel gauge as modules; they are forced built-in (`TYPEC=y` is needed for the PHY to become `y`). Also `FUSE_FS`, `INPUT_UINPUT`, `ZRAM`.
- The current board DT (`exynos7870-j7velte-wifi.dts` chain) compiles against the 7.1 `exynos7870.dtsi` and passes the project verifier unchanged. 7.1's dtsi adds `dsi@14800000`, `display-controller@14830000` (DECON), a MIPI PHY and an IOMMU; it still has no power domains, TMU, MUIC or cpufreq nodes. The first 7.1 image keeps simple-framebuffer and leaves DECON/DSI disabled.
- **Remote safety net installed on the phone:** `system/netguard` → `/sbin/j701f-netguard`, started `once` from `/etc/inittab` (old copy `/etc/inittab.before-netguard`). On a non-3.18 kernel with no `wlan0` address after 300 s it logs and reboots into 3.18 (RECOVERY). `/etc/j701f-netguard-off` disables it. Residual risk it does not cover: a kernel that hangs before `/init`.
- The 7.1 kernel was compiling when this was written; nothing 7.1 has been packaged or written to the phone.

### Linux 7.1.13 is the normal boot (Claude, 2026-10-09) — verified over Wi-Fi SSH

The user approved writing the 7.1 kernel remotely.

- First full-defconfig build gave a 44 MiB Image because the 7.1 exynos7870 fragment leaves every arm64 SoC family enabled; all `ARCH_*` platforms except `ARCH_EXYNOS` are now switched off in `mainline-bringup.config`. Image 27,814,400 bytes, FIT 13.3 MiB, container 13.8 MiB (BOOT is 32 MiB). The FIT layout puts the FDT at `0x41c00000`.
- **`boot-update-k71`:** S-BOOT accepted it; 7.1 booted Alpine and Plasma, USB ACM+NCM enumerated (`bcdDevice 7.01`), Panfrost 1.6.0, eMMC, touch, 8 CPUs — but no `wlan0`. After 300 s `j701f-netguard` rebooted into 3.18 exactly as designed (`/var/log/j701f-netguard.log`), which kept the phone reachable with nobody near it. Cause read over the ACM shell on a second 7.1 boot: `pwrseq-mmc1: deferred probe pending: pwrseq_simple: reset control not ready`. In 7.1 `mmc-pwrseq-simple` obtains a single reset GPIO through the `reset-gpio` driver, which the fragments build as a module.
- **`boot-update-k71b` (now in BOOT):** `CONFIG_RESET_GPIO=y`. Verified: `uname -r` = `7.1.13-BURAK-PANFROST-01`, brcmfmac firmware 7.45.98.118 loaded, `netguard: wlan0 has an address after 10s`, phone at 192.168.1.158, OpenRC runlevels exit 0, `card0 card1 renderD128`, MELFAS touchscreen present with 0 idle interrupts, `/dev/fuse` and `/dev/uinput` exist, KWin reports `Mali-T830 MC1 (Panfrost)`; screenshot `build/screenshots/plasma-on-7.1.png`.
- Same as on 6.15 and still open: simple-framebuffer display (DECON/DSI disabled), no thermal/cpufreq/battery/audio, eMMC timing not re-measured on 7.1, S2MU005 MUIC handled by the userspace script, touch keys, Home key remap is in this image but untested by hand.
- Rollback material: `build/kernel/panfrost-6.15/` (last 6.15 kernel artifacts) and `build/kernel/boot-update-touchfix3/` (last 6.15 BOOT image); 3.18 remains in RECOVERY.

### First benchmarks on 7.1 (Claude, 2026-10-09)

Run at the user's request over SSH on `7.1.13-BURAK-PANFROST-01`, Plasma session running, phone idle otherwise. `glmark2` is not packaged for Alpine 3.24; `mesa-demos` and `sysbench` were installed instead.

| Test | Result |
| --- | --- |
| `es2gears_wayland -fullscreen` (720x1280, under KWin) | 4.5–6.6 FPS; with `vblank_mode=0` 7.1–7.3 FPS |
| `sysbench cpu --cpu-max-prime=10000`, 1 thread | 421 events/s |
| same, 8 threads | 3,372 events/s (8.0x, all cores scale) |
| `sysbench memory`, 1 MiB blocks | 1,122 MiB/s |

Screenshot of the gears on the phone: `build/screenshots/benchmark-gears.png`.

**The on-screen frame rate is far too low for a usable desktop.** The scene is trivial and the earlier off-screen Panfrost probe passed, so the limit is very probably the presentation path, not shader throughput: Panfrost renders, then every frame goes through Mesa's kmsro/prime path into simpledrm's shadow buffer and is copied by the CPU to the firmware framebuffer, with no vblank. Not measured separately: KWin's own compositing cost, the GPU clock (fixed at the firmware's 343 MHz, lowest vendor step) and the CPU clock (no cpufreq driver; single-thread score suggests the cores are not at their top frequency). This raises the priority of the real DECON/DSI/panel driver and of GPU/CPU frequency control above what the earlier "accelerated compositor works" note implied.

### Correction: the low frame rate was measured with the output switched off (Claude, 2026-10-09)

The 4.5–7.3 FPS figures in the previous section are **not** the phone's rendering performance. Follow-up measurements:

- A 300x300 windowed `es2gears` ran at the same 5–6 FPS as fullscreen, with the CPU 95 % idle and Panfrost's per-client busy time at 0 %: something was pacing frames, not computing them.
- `/sys/kernel/debug/dri/0/state` (simpledrm) showed the CRTC `active=0` with no mode. powerdevil, installed earlier the same day, had turned the output off after the idle timeout (nobody touches the phone while the user is away), and KWin throttles clients on a disabled output.
- After `kscreen-doctor --dpms on` plus an injected tap (`active=1`, mode `720x1280` 60 Hz): **`es2gears_wayland -fullscreen` 44.3–44.6 FPS with vsync, 220–248 FPS with `vblank_mode=0`.**

So Panfrost through KWin onto simpledrm is usable: about 44 FPS composited, with headroom when unsynchronised. The earlier conclusion that the simpledrm path makes the desktop unusable is withdrawn. Why vsynced output sits at 44 rather than 60 FPS is not explained (simpledrm has no real vblank; KWin estimates). CPU numbers stand: sysbench 421 events/s single thread, 3,372 with 8 threads; clocks seen in `clk_summary`: G3D PLL 343 MHz.

Practical note for remote work: take screenshots/benchmarks only after waking the output (`kscreen-doctor --dpms on`, or `tools/inject-swipe.py` for a tap); logind may also have locked the session (`loginctl unlock-session`).

### Driver stage 1: battery gauge and touch keys (Claude, 2026-10-09) — `boot-update-periph` in BOOT

User goal for this phase: work through the missing drivers one at a time (frequency, thermal, battery, keys, camera…) and send a screenshot after each stage. New helpers: `tools/build-mainline-image.sh NAME DTS` (whole host pipeline up to a prepared BOOT update) and `tools/phone-screenshot.sh OUT.png [drawer]`.

- `kernel/dts/exynos7870-j7velte-periph.dts` (includes the Wi-Fi tree): `&i2c0` with `fuel-gauge@3b` (`samsung,s2mu005-fuel-gauge`, alert `gpa0-3`, `simple-battery` 3000 mAh) and `&i2c2` with `touchkey@20` (`coreriver,tc360-touchkey`, interrupt `gpa1-4`, fixed regulator `vtouch_2.8v` on `gpd1-6`, keycodes APPSELECT/BACK). `CONFIG_KEYBOARD_TM2_TOUCHKEY=y`.
- **Battery works:** `/sys/class/power_supply/s2mu005-fuel-gauge`: `status=Charging`, `capacity=98`, `voltage_now=4351928`, `current_now=16357`; Plasma's status bar shows 98 % with the charging icon (`build/screenshots/stage-battery.png`). No temperature attribute. There is still no S2MU005 **charger** driver; the phone charges from USB under hardware/bootloader defaults.
- **Touch keys: driver bound, behaviour unverified.** `input: tm2-touchkey` registered, one interrupt at probe and `invalid keycode index -1`, so the chip answers on I2C; whether presses produce APPSELECT/BACK needs a finger. Home key is `KEY_LEFTMETA` in this image, also not hand-tested.
- Survey of the rest in 7.1.13: **no CPU clock controller** for Exynos7870 (no `cpucl` nodes in the dtsi) so cpufreq needs a new CMU driver; **no Exynos7870 TMU** variant in `exynos_tmu.c`; **no camera** (FIMC-IS) driver for this SoC family in mainline at all.

### Driver stage 2: SoC temperature, read-only (Claude, 2026-10-09) — `boot-update-thermal` in BOOT

- Measured first through `/dev/mem` on 7.1: TMU at `0x10130000` has `CONTROL=0x8903` (core left running by firmware), `TRIMINFO=0x40144`, `CURRENT_TEMP=0x148`. With the vendor data for this SoC (9-bit code, one-point trimming at 25 °C) that is 29 °C.
- `kernel/patches/linux-tmu-exynos7870-readonly.patch` adds `drivers/thermal/samsung/exynos7870_tmu_ro.c`, compatible `j701f,exynos7870-tmu-readonly`: it reads TRIMINFO once and CURRENT_TEMP on demand, **writes no register**, sets no trips and arms no hardware reset. Chosen over adapting `exynos_tmu.c` because that driver reprograms gain/reference and can arm a thermal-trip reset; a wrong guess there could power the phone off with nobody near it.
- `kernel/dts/exynos7870-j7velte-thermal.dts`: sensor node plus a `soc-thermal` zone polled every 5 s, no trip points.
- Verified: `/sys/class/thermal/thermal_zone0` type `soc-thermal`, 33.0 °C shortly after boot, 36.0 °C right after a 20 s 8-thread `sysbench`, 30.0 °C idle later (`build/screenshots/stage-thermal.png`, a `foot` window opened on the phone showing kernel, temperature, battery, Wi-Fi and input devices).
- Limits: one sensor only (the vendor tree multiplexes CPUCL0/CPUCL1/G3D on this block; which one the firmware left selected is not known), **monitoring only — nothing throttles**, and there is still no cpufreq to throttle with.

### Driver stage 3: CPU frequency — measured, not implemented (Claude, 2026-10-09)

- Read-only measurement through `/dev/mem` on 7.1: `CMU_CPUCL0` (`0x10900000`) and `CMU_CPUCL1` (`0x10800000`) both have `PLL_CON0 = 0xa15b0501` → M=347, P=5, S=1 → 26 MHz × 347 / (5 × 2) = **902 MHz on all eight cores**, fixed since boot. Rails at the time: BUCK1 737.5 mV, BUCK2 775 mV, BUCK3 768.75 mV. SoC temperature 30 °C idle.
- Mainline 7.1 has no Exynos7870 CPU clock controller (no `cmu_cpucl*` nodes, no CPU clock in the clk driver), so `cpufreq-dt` has nothing to drive. Doing this properly needs: a CMU_CPUCL0/1 clock driver that parks the cluster on the MIF switch clock while the PLL relocks (vendor sequence in `S5E7870-dfs.c`/`S5E7870-pll.c`, kept under `build/kernel/vendor-pd-reference/`), an OPP table whose voltages come from the vendor ASV tables for this chip's group, and the cluster-to-BUCK mapping.
- **Not attempted remotely on purpose.** A wrong PLL sequence or an under-volted OPP hangs the CPU immediately, before `/init`, which is the one failure the `netguard`/90 s fallbacks cannot recover; the user has no physical access. To be done with the user at the phone.

### Camera and remaining keys (Claude, 2026-10-09)

- **Camera:** not achievable with current mainline. The Exynos7870 ISP path (FIMC-IS, CSIS, the sensor drivers) exists only in the vendor 3.18 tree; `drivers/media/platform/samsung/` in 7.1 has `exynos4-is`, `exynos-gsc`, `s3c-camif`, `s5p-*` only, and the pinned board trees for the sibling phones describe no camera. This would be a large porting project of its own, not a driver to enable.
- **Touch keys / Home key:** drivers are in the running image (stage 1); both need a hand on the phone to confirm.

State at the end of this pass: BOOT = `boot-update-thermal` (Linux 7.1.13, Wi-Fi, Panfrost, touch, battery gauge, read-only temperature, touch-key driver bound), RECOVERY = 3.18 fallback, `netguard` active, suspend disabled.

### Watchdog and CPU-frequency data (Claude, 2026-10-09)

**SoC watchdog works; BOOT holds `boot-update-wdt2`.** `kernel/dts/exynos7870-j7velte-wdt.dts` adds `watchdog@10170000` (`samsung,exynos7-wdt`, as in the vendor tree; clock `CLK_GOUT_PERI_WDT_CPUCL0_PCLK`, 30 s). Tested on the phone: fed by `busybox watchdog` it ran for minutes; with the feeder stopped the phone reset after 34 s and booted 7.1 normally. The loader's kernel command line now ends with `s3c2410_wdt.tmr_atboot=1`, so the timer runs from probe and the kernel feeds it; verified `watchdog active, reset enabled` with uptime past the timeout.

**CPU frequency: measured only.** Under the vendor 3.18 kernel on this phone (`build/kernel/vendor-opp-measurement.txt`) the CPU rail is BUCK1:

| MHz | 546 | 676 | 757 | 839 | 902 | 1014 | 1144 | 1248 | 1352 | 1482 | 1586 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BUCK1 mV | 625.00 | 668.75 | 693.75 | 712.50 | 737.50 | 781.25 | 825.00 | 868.75 | 906.25 | 956.25 | 1006.25 |

On mainline both CPU clock controllers (`0x10900000`, `0x10800000`) read `PLL_CON0=0xa15b0501` (902 MHz), the CPU and switch-user muxes are on input 0, bus dividers are `ACLK=1 PCLK=7 ATCLK=7 PCLKDBG=7 CNTCLK=3`, and PMIC register `0x1b` reads `0x36` (737.5 mV, matching the 902 MHz row). 7.1 has no clock driver for these controllers. `tools/cpufreq-prototype.py` is an untested userspace sketch of the vendor switching sequence; it has never been executed on the phone. No frequency has been changed on mainline.

### Driver stage 3 done: CPU frequency scaling with thermal throttling (Claude, 2026-10-09) — `boot-update-cpufreq2` in BOOT

Supersedes the "measured only" paragraph above. The userspace prototype was never run; the same sequence was implemented as a kernel driver and delivered through the normal guarded BOOT update, with the watchdog as the safety net.

- `kernel/patches/linux-cpufreq-exynos7870-j701f.patch` adds `drivers/cpufreq/exynos7870-cpufreq.c` (compatible `j701f,exynos7870-cpufreq`, built with `CONFIG_CPUFREQ_DT`). One policy for all eight cores. Per transition: raise BUCK1 first when going up; per cluster select the CMU switch clock on the switch-user mux, move the CPU mux to it, write PLL lock time and PMS, wait for lock, move back; lower BUCK1 afterwards when going down. PMS uses P=5 with S=1 up to 902 MHz and S=0 above. Voltages are the vendor-kernel measurements plus 12.5 mV. Bus dividers are untouched. The driver refuses to register if the boot PLL state is not the expected 902 MHz on both clusters.
- First image (`boot-update-cpufreq`, limits pinned to 902 MHz): the cpufreq core itself made one 902 → 1014 → 902 round trip at registration because 26 MHz × 347 / 10 is 902.2 MHz, "unlisted"; `get()` now reports the table value. Manual tests through `scaling_setspeed` (`build/kernel/mainline-cpufreq-steps.txt`):

| MHz | 546 | 902 | 1144 | 1248 | 1352 | 1482 | 1586 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BUCK1 mV | 637.5 | 750.0 | 837.5 | 881.25 | 918.75 | 968.75 | 1018.75 |
| sysbench 1 thread, events/s | 254 | 421 | 534 | 583 | 631 | 692 | 741 |
| sysbench 8 threads, events/s | 2,026 | 3,367 | 4,272 | 4,658 | 5,052 | 5,541 | 5,929 |
| SoC °C right after | 33 | 34 | 36 | 38 | 39 | 41 | 44 |

  Linear scaling on one and on eight threads shows both PLLs follow and that BUCK1 feeds all eight cores. Up and down transitions (1586 → 546 → 902 → 1586 → 902) completed without errors.
- Second image (`boot-update-cpufreq2`, current): default policy 546–1352 MHz with `schedutil`; raise `/sys/module/exynos7870_cpufreq/parameters/max_khz` for the 1482/1586 MHz steps, or set min and max to 902000 for the old fixed behaviour. The driver is a cooling device (`cpufreq-cpu0`). `kernel/dts/exynos7870-j7velte-cpufreq.dts` gives the `soc-thermal` zone trips: passive 70 °C mapped to the cpufreq cooling device, hot 85 °C, critical 105 °C (kernel power-off). Verified after boot: governor `schedutil`, range 546000–1352000, `time_in_state` spread over the steps, cooling device and three trips present; screenshot `build/screenshots/stage-cpufreq.png`.
- Not tested: behaviour at the trip temperatures (the phone never exceeded 44 °C in these short runs), long sustained load, the top two steps under `schedutil`, GPU frequency (still fixed at 343 MHz), and whether leaving the bus dividers unchanged is right at the highest steps (no fault seen).

### Driver stage 4: keys (Claude, 2026-10-09) — `boot-update-keys2` in BOOT

- **Touch-key event format fixed.** The vendor driver for this part (`drivers/input/keyboard/tc300k.c`, `use_bitmap`) reports recents/back presses in bits 0/1 and releases in bits 4/5 of register 0. Mainline `tm2-touchkey` expects an index plus one release flag, so it logged `invalid keycode index -1` and would never have reported a release. `kernel/patches/linux-tm2-touchkey-bitmap-events.patch` adds that decoding behind the DT property `j701f,bitmap-events`; the probe-time warning is gone.
- **Key codes chosen for Plasma Mobile:** recents is `KEY_PROG1` (Qt "Launch (1)"), back is `KEY_BACK`, Home is `KEY_LEFTMETA`. Plasma has no binding for `KEY_APPSELECT`; the user's `~/.config/kglobalshortcutsrc` now has `Mobile Task Switcher = Meta+C, Launch (1)`. Input devices report `tm2-touchkey: [148, 158]`, `gpio-keys: [114, 115, 116, 125]`.
- **Verified by injecting key events into the real input devices** (`tools/inject-key.py`, root, evdev write): `KEY_LEFTMETA` on `gpio-keys` returns to the home screen with an app open; `KEY_PROG1` on `tm2-touchkey` opens the task switcher (`isTaskSwitcherVisible` true, `build/screenshots/stage-keys.png`). `KEY_BACK` was not exercised.
- **Still unverified:** the physical link — that a finger on the capacitive keys or a press of the Home button produces these events (chip sensitivity, the bitmap decoding against real data, GPIO polarity). Needs the user at the phone. `system/touchkey.hwdb` was written as an alternative remap but is not installed and not needed with this image.

### Where the driver pass stands (Claude, 2026-10-09)

| Item | State | Evidence |
| --- | --- | --- |
| Battery gauge | working | `capacity`, `status`, voltage in sysfs and in Plasma's status bar |
| SoC temperature | working, with passive/hot/critical trips | 30–44 °C tracked across load tests |
| CPU frequency | working, 546–1352 MHz by default, 1586 MHz verified | step table above; `schedutil` |
| Watchdog | working, armed from boot | stop-feeding test reset the phone in 34 s |
| Home / recents / back keys | drivers, key codes and session bindings in place; physical press untested | injected events |
| Charger | no driver in 7.1; phone charges on hardware defaults | gauge shows Charging/Full |
| GPU frequency | fixed at the firmware's 343 MHz | not started |
| Real display driver (DECON/DSI/EA8061S) | not started; needs the user present | simple-framebuffer in use |
| Audio, modem, Bluetooth, sensors | not started | — |
| Camera | no mainline driver exists for this SoC's ISP | vendor 3.18 only |

### Driver stage 5: Bluetooth and accelerometer (Claude, 2026-10-09) — `boot-update-extra` in BOOT

- `kernel/dts/exynos7870-j7velte-extra.dts` (top of the include chain now): `&serial1` with `brcm,bcm43430a1-bt` on the vendor's pins (enable `gpd4-0`, device wake `gpa1-2`, host wake `gpa1-6`, same as j6lte; no pinctrl states, after the Wi-Fi `pin-val` lesson), and `&i2c7` with `st,lis2hh12` at 0x1d (vendor `k2hh-i2c`, interrupt `gpa2-3`). Config: `BT`, `BT_HCIUART`, `BT_HCIUART_BCM`, `IIO_ST_ACCEL_3AXIS`, `IIO_ST_ACCEL_I2C_3AXIS` built in.
- Verified after boot: `Bluetooth: hci0: BCM43430A1 (001.002.009)`, `/sys/class/bluetooth/hci0` exists. The driver found no `brcm/BCM43430A1*.hcd` patch file (none on the build host), so the controller runs ROM firmware; no scan or pairing was attempted, and `bluetoothd` is not set up.
- Verified: IIO device `lis2hh12` reads x≈-700, y≈0, z≈16,800 raw at scale 0.000598, i.e. about 10 m/s² on Z with the phone lying still. The mount matrix (from the vendor axis map) is not checked against real orientation; nothing uses the sensor for rotation yet (`iio-sensor-proxy` not installed).
- Back key: an injected `KEY_BACK` on the touch-key device was accepted, but Claude's attempt to observe its effect in a client was inconclusive. Still to be tried by hand.
- Screenshot of the on-phone summary: `build/screenshots/stage-extra.png`.

### What remains, and why (Claude, 2026-10-09)

Not doable from here, by nature:
- **Camera.** No mainline driver exists for the Exynos7870 ISP/CSIS chain or is described for any sibling board; it would be a port of the vendor FIMC-IS stack.
- **Physical confirmation** of touch, Home, recents and back presses, and of accelerometer orientation: needs a person at the phone.
- **Real display driver** (DECON/DSI + a new EA8061S panel driver): a failed first attempt blanks the screen; to be done with the user present. Zeroth step is researched above.

Possible but not started (each is its own piece of work): GPU frequency scaling (the G3D PLL has no rate table in the clk driver and needs a glitch-free switch during relock; 343 MHz measured adequate for the compositor), an S2MU005 charger driver (none in 7.1), a kernel MUIC driver to replace `muic-usb-path`, audio, modem/telephony, Bluetooth userspace and firmware patch, sensors beyond the accelerometer, eMMC high-speed modes, suspend.

### GPU frequency scaling: assessed, deliberately not attempted remotely (Claude, 2026-10-09)

- 7.1 models the G3D clock tree (`fout_g3d_pll` 343 MHz → `mout_g3d` → `dout_g3d_bus` → `gout_g3d_clk`; alternative parent `mout_g3d_switch_user` fed by `gout_mif_cmu_g3d_switch` at 399.75 MHz), but the PLL has no rate table and nothing parks the GPU on the switch clock while the PLL relocks. Panfrost devfreq would call `clk_set_rate()` on a live GPU clock.
- BUCK2 reads 775 mV with two users. Under the vendor kernel BUCK2 also moved with CPU frequency while the GPU was idle (662.5 → 712.5 mV), so it is probably not a GPU-only rail; an OPP table must not go below the boot voltage until that is understood. Vendor GPU steps for reference: 343/450/545/676/728/845/1001 MHz at 600/637.5/681.25/743.75/762.5/837.5/931.25 mV.
- Why not now: Panfrost starts devfreq at every boot with the `simple_ondemand` governor. If a transition wedges the G3D bus, the watchdog resets the phone, the next boot does the same, and the result is a reset loop that only the user at the phone can break. The CPU work avoided this by staying at the boot frequency until told otherwise; an equivalent opt-in for the GPU needs driver changes first. At 343 MHz the compositor measured 44 FPS vsynced and over 220 FPS unsynchronised, so this is not urgent.

## GPU frequency scaling (2026-10-09, image `gpufreq`)

Working on Linux 7.1.13. BOOT now holds candidate `gpufreq` (`build/kernel/boot-slot.json`).

- `kernel/patches/linux-g3d-exynos7870-scaling.patch`: (1) rate table for the G3D PLL (P=13, S=1, M = MHz; 343/450/545/676/728/845/1001 MHz) and `CLK_SET_RATE_PARENT` on `mout_g3d` and `dout_g3d_bus`, so Panfrost's `clk_set_rate()` reaches the PLL; (2) local driver `drivers/clk/samsung/clk-exynos7870-g3d-park.c` (`j701f,exynos7870-g3d-park`): a clock notifier on `fout_g3d_pll` moves the GPU onto the 399.75 MHz CMU_MIF switch clock while the PLL relocks, and holds a `DEV_PM_QOS_MAX_FREQUENCY` request on the GPU so nothing scales until `/sys/module/clk_exynos7870_g3d_park/parameters/max_khz` is raised (boot default 343000).
- `kernel/dts/exynos7870-j7velte-gpufreq.dts` (includes `-extra.dts`): OPP table on `&gpu` plus the park node. Voltages never go below the 775 mV BUCK2 has at boot (343-728 MHz at 775 mV, 845 at 850 mV, 1001 at 943.75 mV = vendor value + 12.5 mV); the vendor's lower values (600 mV ...) are not used because BUCK2 may feed more than the GPU.
- `system/gpufreq-limit` -> `/etc/local.d/j701f-gpufreq.start` (service `local` added to runlevel default): 40 s after boot raises the limit to 1001000. It writes `/var/lib/j701f-gpufreq.pending` first and removes it 180 s later; if that file exists at boot (the phone reset during a raise) the GPU stays at 343 MHz until the file is removed.

Measured with `vblank_mode=0 es2gears_wayland` (governor `simple_ondemand`): 343 MHz ~250 FPS, 728 MHz ~537, 845 MHz ~628, 1001 MHz ~727-816. 150 s at 1001 MHz: SoC sensor 38 C, no Panfrost faults, 54 transitions without a mux timeout; idle returns to 343 MHz / 775 mV.

Not done: GPU as a thermal cooling device (needs `#cooling-cells` on `&gpu` and a cooling map), lower idle voltages, long-duration soak.

## GPU thermal throttling and CPU at 1586 MHz (2026-10-09, image `gputhermal`)

BOOT now holds candidate `gputhermal`. `kernel/dts/exynos7870-j7velte-gputhermal.dts` (includes `-gpufreq.dts`) gives `&gpu` `#cooling-cells` and adds it to the 70 C passive trip's cooling map next to `&cpu0`. Result: `cooling_device0 = devfreq-11400000.gpu` (7 states) bound to `thermal_zone0` as well as `cpufreq-cpu0`. Checked by writing the GPU cooling state by hand: state 3 drops the devfreq `max_freq` from 1001 to 676 MHz, state 0 restores it.

`system/gpufreq-limit` (`/etc/local.d/j701f-gpufreq.start`) now also raises the cpufreq driver's `max_khz` to 1586000, under the same pending-stamp guard; verified after a reboot.

Load test, 240 s of `sysbench cpu --threads=8` plus unsynced `es2gears_wayland`: all eight cores at 1586 MHz and the GPU at 1001 MHz throughout, SoC sensor 54 -> 60 C and still rising slowly, 5146 events/s, no faults. The 70 C trip was therefore not reached; throttling at the trip itself is still untested on real heat.

## Firefox ESR and video playback (2026-10-09)

`firefox-esr` 140.12.0 was already installed. With hardware WebRender the window is black: Mesa/Panfrost on the Mali-T830 fails WebRender shaders (`ERROR: Failed to choose spill node` in the Firefox output). Workaround installed on the phone: `/usr/lib/firefox-esr/browser/defaults/preferences/j701f.js` with `pref("gfx.webrender.software", true);`. With it pages render (YouTube's consent page was reached and left untouched) and a 480p VP9 WebM from Wikimedia Commons plays in the window (two KWin screenshots 20 s apart show different frames: `build/screenshots/firefox-video-{1,2}.png`).

Open issues: the Firefox toolbar stays an empty skeleton in screenshots; a direct `.m4v` (H.264) URL from download.blender.org showed only the skeleton (not investigated); no sound because there is no audio driver yet; with 1.6 GB RAM two Firefox instances thrashed, so a 1 GiB zram swap was enabled by hand (`/sys/block/zram0/disksize`, `mkswap`, `swapon -p 10`) and is NOT persistent across reboots. Started over SSH with `MOZ_ENABLE_WAYLAND=1`. Note: `pkill -f firefox-esr` over SSH kills the invoking shell too; kill by `/usr/lib/firefox-esr/` instead.

## Browser GPU acceleration attempt (2026-10-09) - NOT solved for Firefox

- `/tmp` was a 16 MB tmpfs and Firefox filled it with (deleted, still open) media-cache files; that is the likely reason the H.264 `.m4v` test never rendered (not re-tested). `system/start` (`/sbin/j701f-start`) now remounts `/tmp` with `size=256m`; applied live as well.
- Firefox ESR 140 with hardware WebRender (throwaway profile, `gfx.webrender.software=false`, `gfx.webrender.all=true`, Mesa 26.1.6): WebRender threads start, but only part of the page is drawn (headings yes, body text/images/toolbar no) and the kernel logs hundreds of `panfrost ... js fault` with `INSTR_INVALID_ENC` and `DATA_INVALID_FAULT`, plus Mesa's `Failed to choose spill node` on some runs. Same result with the GPU pinned at 343 MHz, so it is not the new frequency scaling. Also tried: `gfx.egl.prefer-gles.enabled=true` (same faults), `gfx.webrender.use-optimized-shaders=false` (same faults), both together (no faults in the first minute but an empty page, faults later). Conclusion: the Midgard shader compiler in Mesa emits bad code for WebRender's shaders; no Firefox setting fixed it. The software-WebRender pref from the previous section stays installed. A real fix means debugging or patching Mesa's Midgard backend.
- Angelfish 26.04.2 (QtWebEngine 6.11.1, already-installed engine; `apk add angelfish`): renders en.wikipedia.org completely, toolbar included, on `Mali-T830 MC1 (Panfrost) OpenGL ES 3.1` with zero GPU faults (`build/screenshots/angelfish-1.png`). But the 480p VP9 WebM loads (10:34 shown), and after an injected tap on play the view stays black with an idle CPU - video playback in Angelfish does not work yet; cause unknown (no media errors with `--enable-logging=stderr`; missing audio sink is one suspect). Launching it over SSH needs `DBUS_SESSION_BUS_ADDRESS` copied from plasmashell's environment.
- There is no mainline video-decoder (MFC) support wired up for this SoC here, so video decoding is on the CPU in any browser.

## VLC as default video player; audio assessment (2026-10-09)

- `apk add vlc-qt` (VLC 3.0.23); `xdg-mime default vlc.desktop` for every video MIME type in `vlc.desktop`. VLC's Qt5 interface only starts through Xwayland here (needs `DISPLAY`/`XAUTHORITY` from the session; inside Plasma that is already set). `~/.config/vlc/vlcrc` got `avcodec-hw=none` (there is no hardware decoder). `/usr/lib/vlc/plugins/plugins.dat` was regenerated and must stay mode 644.
- Local test files generated on the host with ffmpeg (`~/Videos/test480.mp4`, `test720.mp4`, H.264 + AAC, 90 s): 480p plays at ~16 % CPU, 720p at ~30-34 %, 0-2 late frames, no Panfrost faults. The user saw a Wikimedia HTTPS stream freeze after ~15 s and VLC close the video on seek; the VLC log for that stream has `http stream error: ... Stream closed`, so the freeze looks network/stream related. Seeking on a local file is NOT verified: MPRIS over D-Bus reported `Stopped`/0 even while VLC was decoding, so it could not be used as a check.
- `tools/phone-screenshot.sh` produced a PNG that image readers call truncated while VLC showed the test pattern (`build/screenshots/vlc-*.png`); not investigated.
- Audio on mainline: nothing exists yet. `CONFIG_SOUND=m` with no modules installed, so there is no ALSA at all. The vendor tree (`build/kernel/j701f-live.dts`) uses the COD3026X codec inside the S2MPU05 PMIC (`codec,cod3026x`, I2C 0x04), `samsung,exynos7870-lpass` at 0x148F0000, `samsung,i2s-v5` at 0x148A0000/0x148B0000 and machine driver `samsung,universal7870-cod3026x`. Linux 7.1.13 has no COD3026X codec driver and the vendor source for it is not in this repo. Needed: audio clocks (AUD PLL / MI2S in CMU_DISPAUD), LPASS glue, Samsung I2S node, a ported codec driver, a machine driver/card, then mixer routing. Possible shortcut without any of that: Bluetooth audio (controller `hci0` already works; needs bluez + PipeWire and a paired headset).

## Audio stage 1: clocks, LPASS, audio DMA, I2S (2026-10-09, image `audio1`)

The user gave standing permission to read Samsung's kernel (or other custom-ROM kernels) and port or adapt code when mainline lacks a driver. Reference files for audio are in `build/kernel/vendor-audio-reference/` (`SOURCE.txt`, `SHA256SUMS`): COD3026X codec, `exynos-audmixer` (S1402X), `lpass-exynos7870.c`, `universal7870-cod3026.c`, vendor I2S, vendor `exynos7870.dtsi`, pwrcal S5E7870.

Audio path on this phone (vendor tree): AP I2S0 `0x148a0000` -> internal audio mixer S1402X `0x14880000` -> COD3026X codec inside the S2MPU05 PMIC (I2C address 0x04). Audio DMA is a PL330 at `0x14890000`; the wrapper block at `0x148f0000` holds the software resets.

Done in this stage, BOOT = `audio1`:
- `kernel/patches/linux-audio-exynos7870-lpass.patch`: (1) the audio PLL is now `pll_36xx` (fractional; the vendor calls it PLL1431x) with a rate-table entry. Confirmed on hardware: the bootloader leaves it at 98,304,019 Hz, which only a fractional PLL can produce (K=32426). The table entry currently uses K=32425 (98,303,995 Hz); align it to K=32426 next time the patch is touched. (2) `sound/soc/samsung/exynos7870-lpass.c` (`j701f,exynos7870-lpass`): enables the audio clocks from DT, pulses the four resets in DISPAUD_CFG, repeats the vendor pad-retention release in the PMU, then populates its child nodes.
- `kernel/dts/exynos7870-j7velte-audio.dts` (includes `-gputhermal.dts`): `&cmu_dispaud` okay, LPASS node with assigned clock rates, `adma` PL330, `i2s0` (`samsung,exynos7-i2s`).
- `tools/build-j701f-dtb.py --allow-audio` and a third argument to `tools/build-mainline-image.sh` (`tools/build-mainline-image.sh audio1 kernel/dts/exynos7870-j7velte-audio.dts --allow-audio`). The image script now stops on the first failing step (it used to continue, which once sent `run-boot-update.sh` off without an image).
- Config: `SOUND/SND/SND_SOC=y`, `SND_SOC_SAMSUNG=m`, `SND_SAMSUNG_I2S=m`. The modules are NOT installed in `/lib/modules`; they are in `build/kernel/audio-modules/` and on the phone in `~/j701f-audio-modules/`, loaded by hand: `insmod exynos7870-lpass.ko; insmod snd-soc-s3c-dma.ko; insmod snd-soc-idma.ko; insmod snd-soc-i2s.ko`. Build them with the same make environment as `tools/build-kernel.py` plus the `.ko` targets.

Result after loading by hand: clocks at 98.3 MHz (PLL, MI2S) and 49.15 MHz (mixer), `dma-pl330 14890000.dma-controller: Loaded driver for PL330 DMAC-341330 ... Num_Chans-4`, `samsung-i2s` bound to `148a0000.i2s` and `148a0000.i2s-sec`. No sound card yet (no mixer, codec or machine driver).

Incident: the first `audio1` image had LPASS and I2S built in and the I2S node carried `#clock-cells`; it boot-looped (the user saw a "translation" fault before the reset; no log was captured). The user booted RECOVERY with the key combination and `gputhermal` was written back (`tools/prepare-boot-update.py` had to be re-run first because the prepared update checks the current BOOT hash). The module-based image has neither property and does not crash, so the cause is one of: built-in probe ordering, or the I2S clock-provider path enabled by `#clock-cells`. Not narrowed down further. Rule adopted: new audio drivers stay modules loaded by hand until they have survived a manual load.

Next stages: (2) port the S1402X audio mixer (`exynos-audmixer.c`, 2462 lines), (3) port the COD3026X codec (`cod3026x.c`, 4314 lines) on the PMIC I2C bus, (4) machine driver / sound card and mixer routing for speaker, headphones and microphones.

## Audio stage 2: COD3026X playback codec, mixer, sound card (2026-10-09, image `audio3`)

BOOT = `audio3`. A sound card `J701F` now exists with one playback PCM (`HiFi cod3026x-aif-0`), and PipeWire shows it as "Built-in Audio Stereo". `speaker-test` (hw:0,0, 48 kHz S16) and `pw-play` both run to completion without errors. **Whether sound is audible from the speaker has not been confirmed by a person yet** - only the user can hear it.

- `kernel/patches/linux-audio-j701f-codec-card.patch` (applies after the LPASS patch), all in `sound/soc/samsung/`:
  - `j701f-cod3026x-regs.h`: the `#define` lines of the vendor `cod3026x.h`.
  - `j701f-cod3026x.c` (`j701f,cod3026x`, I2C): playback-only port of the vendor codec: default setup, DAC, speaker / headphone / earpiece power sequences (the codec's "auto power" register 0x17), output-offset handling. Controls: `Speaker Volume` (0-15), `Headphone Volume`, `Earphone Volume`, `DAC Gain`, `SPK|HP|EP ... On`, `SPK|EP|HPL|HPR Mixer DACL/DACR`. Speaker path is the default; headphones/earpiece need their switches set by hand. No capture, mic bias, jack or button detection; all codec interrupts are masked.
  - `j701f-audio.c` (`j701f,exynos7870-audio`): the sound card. It also owns the internal S1402X mixer at `0x14880000` (reset, AP interface 32fs/I2S/16 bit, slots, master clock out to the codec, digital mixer enable) and the vendor's PMU "reg-alive" bit (`0x10480080` bit 0 cleared). I2S clocking as in the vendor machine driver: RFS 512, BFS 32, op clock from MI2S.
- Device tree (`exynos7870-j7velte-audio.dts`): codec node on `&hsi2c0` with `reg = <(0x04 | I2C_TEN_BIT_ADDRESS)>` and `vdd-supply = <&vdd_ldo25>`; `sound@14880000` under the LPASS node; I2S now `compatible = "samsung,s5pv210-i2s"`.
- Modules, still loaded by hand: `sudo sh ~/j701f-audio-modules/load.sh` (repo: `system/audio-load`; it also restores `asound.state` saved with `alsactl store -f asound.state 0`).

Findings worth keeping:
- The codec really is at I2C address 0x04 on the PMIC bus (i2c-0); it answers to raw transfers. 0x04 is a reserved 7-bit address, hence the ten-bit flag; mainline `i2c-exynos5` ignores the flag on the wire. The device shows up as `0-a004`.
- The I2S controller uses the old "v5" register layout (vendor `samsung,i2s-v5`: BFS at bit 1, RFS at bit 3, RCLKSRC bit 10, CDCLKCON bit 12). With `samsung,exynos7-i2s` (v7 layout) the stream opened but every write ended in `-EIO` because the controller never clocked. `samsung,s5pv210-i2s` selects the matching layout in mainline.
- Mixer system clock must be 24.576 MHz (512 x 48 kHz). Asking the divider for exactly 24576000 gives /5 (19.66 MHz) because the PLL runs at 98,304,019 Hz; request 24576100 like the vendor does.
- The codec's output-offset registers (0xd4/0xd5, factory values 0x12/0x0f on this phone) survive a warm reboot. A driver that leaves them at 0 (speaker path) makes the next boot read 0 as the "factory" value. The driver now writes the factory values back when the outputs go idle.
- Codec state during speaker playback: 0x17=0x14, 0x37=0x0c, 0x40=0x79, 0x41=0xa8, 0x76=0x26.
- Host `/tmp` (tmpfs) filled up with per-image U-Boot build directories and the U-Boot link died with SIGBUS (make error 135); `/tmp/j701f-uboot-embedded-source/out-uboot-j701f-*` can be deleted at any time. `tools/build-mainline-image.sh ... | tail` hides its exit status: check that `boot-update-<name>/boot-mainline.img` exists before `tools/run-boot-update.sh`.

Not done: confirmation by ear, headphone and earpiece tests, capture/microphones, jack detection, voice call/Bluetooth/FM paths, sample rates other than 48 kHz, suspend handling, installing the modules for automatic loading.

## Audio stage 3: speaker playback confirmed by ear (2026-10-09, image `audio4`)

BOOT = `audio4`. The user heard the test tones from the built-in speaker ("played the notes, very loud", level 12/15), preceded by pops and followed by hiss. What was missing after stage 2, in the order found:

1. The I2S lines between the SoC mixer and the codec were never muxed: `pinctrl-0 = <&i2s_pmic_bus>` (gpz1-0/2/3/4, function 2) on the `sound` node. Without it: silence.
2. Vendor property `bck-mcko-mode` on the S1402X node of this phone: mixer `HQ_CTL` needs `BCK4_MODE` (bit 1) in addition to `MCKO_EN` (bit 2), i.e. the codec master clock goes out on the AIF4 BCLK line. With 1+2 the user heard only pops (amplifier switching, no signal).
3. Mixer `DMIX1` bit 3 (vendor control "CH1 Mixer En"): routes the AP interface into the digital mix. All mixer routing registers are 0 after reset. With this set: tones.

Follow-up changes in `linux-audio-j701f-codec-card.patch` (modules only, no reflash):
- Codec: the "DACL/DACR Switch" controls on the output mixers are gone. They sat on the same register bits (0x36/0x37) that the vendor power sequences set and clear, so the first playback left them off and DAPM then saw no path. Output selection is by `SPK SPK On` (default on), `HP HP On`, `EP EP On` only.
- Card: `ignore_pmdown_time` so the speaker amplifier powers down right after a stream stops (it hisses while idle). After playback 0x17 reads 0.
- `system/audio-autoload` -> `/etc/local.d/j701f-audio.start`: loads the modules at boot via `~/j701f-audio-modules/load.sh` with the same pending-stamp guard as the GPU/CPU limits (`/var/lib/j701f-audio.pending`). Verified: after a reboot the card is present without manual steps, and `pw-play` works twice in a row at 30 % (PipeWire volume maps to the codec's `Speaker Volume`, 5/15).

Still open: pops when the amplifier switches on; the result of the latest quiet test has not been reported by the user yet; headphones, earpiece, microphones, jack detection, call audio untested/unported.

Unrelated observation in dmesg on this boot: `EXT4-fs (mmcblk0p24): warning: mounting fs with errors, running e2fsck is recommended` - the root filesystem has recorded errors (several hard resets today). Not repaired; needs an fsck with the filesystem unmounted.

## Audio stage 3b: volume cap, start mute, stamp cleanup (2026-10-09, modules only)

User feedback on the previous section: playback is clean, KDE's own sound effects are clean, no hiss at the end; pops when a sound starts remain; above 50-60 % in the desktop volume control the speaker is far too loud and distorted.

- `j701f-audio.c`: `snd_soc_limit_volume(card, "Speaker Volume", 8)`. The control now reports `Limits: 0 - 8`, so 100 % in PipeWire equals the old ~55 %.
- `j701f-cod3026x.c`: `.mute_stream` keeps the DAC soft-muted (register 0x50 bit 1) until the stream has started; muted at probe. This is an attempt at the start pops, not a confirmed fix. If the pops persist the next suspects are the amplifier turn-on itself (vendor sequence: PGA gain to 0, auto-power on, wait 135 ms, gain back) and the fact that the I2S clocks only start at trigger time here, after DAPM has powered the codec.
- `system/stamps-stop` -> `/etc/local.d/j701f-stamps.stop`: removes the two "pending" stamps on an orderly shutdown. Before this, an ordinary reboot within 3 minutes of boot left `j701f-gpufreq.pending` behind and the next boot stayed at 343 MHz GPU / 1352 MHz CPU ("previous raise did not survive" in dmesg) although nothing had crashed.

Test after these changes: melody three times at 60 % and once at 100 % through `pw-play`, all without errors; the audible result is with the user.

User confirmation for stage 3b (2026-10-09 evening): the 100 % test was clean, and after a reboot the start pop did not occur. Speaker playback is considered working. The user asked for no more loud test tones tonight.

## Audio: volume keys (2026-10-09, codec module only)

User report: the volume keys show the OSD and play the feedback sound but the level does not move; dragging the slider works. Cause: `Speaker Volume` had no dB scale, so PipeWire saw a bare 0-8 integer and each 5 % key step rounded back to the same hardware step. `j701f-cod3026x.c` now carries the vendor dB scales (speaker -6 dB + 1 dB/step, headphone -57 dB + 1 dB/step, earpiece 0 dB + 1 dB/step). Checked without playing sound: `wpctl set-volume` 0.50 / 0.55 / 0.60 / 0.65 now each read back unchanged, and `amixer` shows `[-6.00dB]`. The vendor comment gives the speaker PGA's real range as 0-9 (-6 to +3 dB), which explains the distortion above 9; the cap stays at 8 (+2 dB). Not yet confirmed with the physical keys. The same reboot confirmed the stamp cleanup: GPU limit back at 1001 MHz after an orderly reboot.

## Wiki, music player (2026-10-09)

- A bilingual MkDocs Material wiki now lives in `wiki/` (`mkdocs.yml`; English `page.md`, Turkish `page.tr.md`; build with `build/wiki-venv/bin/mkdocs build --strict`). User rule: every project change is also noted in the wiki; see `wiki/maintaining.md` and the note in `docs/next-goals.md`.
- `apk add elisa` (26.04.2); `xdg-mime default org.kde.elisa.desktop` for common audio types. Test track `~/Music/Erik Satie - Gymnopedie No. 1.ogg` (6.5 MB, CC0, from https://commons.wikimedia.org/wiki/File:Gymnopedie_No._1..ogg). Not played by Claude: the user asked for no more loud tests that evening.

## Priorities set by the user, and eMMC stage 1 (2026-10-09 night, image `emmc1b`)

User's order of work from here: (1) performance - eMMC speed, USB, hardware video decoding, GPU, the real display driver; (2) basic phone features - Bluetooth, the rest of audio, screen brightness, GPS, power domains, suspend, vibration, charger control; (3) camera last. Modem and FM radio are not wanted for now (the phone has FM, no NFC).

eMMC: was in legacy timing, 25 MHz, 21.9 MB/s sequential read (`dd` of 200 MB from SYSTEM). `kernel/dts/exynos7870-j7velte-emmchs.dts` (includes `-audio.dts`, now the top of the chain) adds `bus-width = <8>` and `cap-mmc-highspeed`. The dw_mmc Exynos driver then also negotiates DDR on its own: `mmc0: new high speed DDR MMC card`, timing "mmc DDR52", 49.97 MHz, **60.4 MB/s** 20 s after boot (CPU still capped at 1352 MHz) and **81.6 MB/s** on a second run. Not done: HS200/HS400 (vendor tree has `mmc-hs200-1_8v`, `mmc-hs400-1_8v`, enhanced strobe, HS200 timing `<3 0 3 0>`, DDR200 timing `<1 0 4 0>` delay line 0x60).

Offline filesystem check in the initramfs: `kernel/diagnostic/alpine-handoff` now copies `e2fsck`, the musl loader and its libraries out of the root during the read-only inspection mount, unmounts, and runs it on the partition (`apk add e2fsprogs` on the phone). Mode comes from `/etc/j701f-fsck-mode` in the root: absent = `-p`, `-fn` = forced read-only report, `-fy` = forced full repair. Result in dmesg (`j701f: e2fsck <mode> exit status N`) and `/run/j701f-fsck.log`.
- `-p` refused: exit 4, "Inodes that were part of a corrupted orphan linked list found. UNEXPECTED INCONSISTENCY".
- `-fn` report saved as `build/kernel/fsck-dryrun-2026-10-09.log`: eight orphaned/half-deleted inodes (9296, 9297, 9302, 9304, 272976, 273027, 273028, 622593), block and inode bitmap differences for them, wrong free counts. No directory or file-content errors reported. Typical leftovers of hard resets.
- The repair (`-fy`) has NOT been run: it changes the user's filesystem and waits for the user's go-ahead. To run it: `echo -fy | sudo tee /etc/j701f-fsck-mode`, reboot, read the log, then remove the file.

Filesystem repair done (2026-10-09, user: "onar gitsin"). A small backup was taken first: `build/phone-backup/etc-home-config-2026-10-09.tar.gz` (/etc, ~/.config, ~/.local/share, audio modules, SDDM state; 21 MB). One boot with `/etc/j701f-fsck-mode` = `-fy`: `e2fsck -fy exit status 1` (errors corrected), the eight orphaned inodes cleared, free block/inode counts corrected, "FILE SYSTEM WAS MODIFIED", 89014 files. The following mount shows no "mounting fs with errors" warning. Log: `build/kernel/fsck-repair-2026-10-09.log`. Mode file removed again (back to `-p`). Also: `tools/run-boot-update.sh` now clears the two reset-guard stamps before its deliberate reboot into the vendor system (it had left `j701f-gpufreq.pending` behind and the next boot stayed at 343 MHz).

## eMMC HS200 attempt: failed, reverted (2026-10-09 night)

`kernel/dts/exynos7870-j7velte-emmchs200.dts` (`mmc-hs200-1_8v`, SDR timing `<3 0>` after the vendor's HS200 drive phase) as image `emmc2`: the phone did not reach Alpine and fell back to the vendor kernel after 90 s, twice. The second time the kernel log was read over the USB serial shell inside that 90 s window (`build/kernel/emmc-hs200-failure-2026-10-09.txt`): the card comes up, the read-only inspection mount works, then the host re-initialises the card (400 kHz -> 52 MHz -> 199.875 MHz) and every WRITE fails with I/O errors ("lost async page write" from e2fsck/journal), ending in `EXT4-fs: error loading journal`.

BOOT is back on `emmc1b` (DDR52, 60-80 MB/s). Afterwards `e2fsck -p` replayed the journal and a forced `-fn` pass reported no errors, so the lost writes did no lasting damage - but that was luck, not design.

Rules from this: (1) do not try an eMMC timing mode on the partition the system boots from with a read-write mount; a future HS200/HS400 attempt needs an initramfs-only test (no fsck, no mount, read tests and a write test on a scratch area) and probably the vendor's per-speed pin drive strengths (`pinctrl-2..6`, `clk-drive-number = <6>`), fine tuning and `ciu_clkin` table, none of which mainline dw_mmc-exynos has for this SoC. (2) The 90 s initramfs fallback plus the USB serial shell is enough to capture the log of a failed root mount: poll `/dev/ttyACM0` right after the update.

The DTS chain top for builds is `exynos7870-j7velte-emmchs.dts`; `-emmchs200.dts` is kept only as a record of the failed attempt.

## Incident: phone hung in reboot after a PMU regmap dump (2026-10-09 night) - NEEDS A HAND ON THE PHONE

What happened (Claude's mistake): to see which power domains are on, Claude read `/sys/kernel/debug/regmap/dummy-system-controller@0x0000000010480000/registers`. That file walks every PMU register; one of them faults on read. The kernel oopsed in `regmap_mmio_read32le` and killed the reading process "with irqs disabled / preempt_count 1", i.e. with the PMU regmap spinlock still held. The system kept running, but the following `sudo reboot` never completed: restart goes through the PMU regmap. The s3c2410 watchdog driver stops the watchdog in its shutdown hook, so nothing reset the SoC. State when Claude stopped: USB still enumerated from the old boot ("J701F mainline RAM diagnostic", no re-enumeration), no serial shell response, no Wi-Fi.

To recover: hold Volume Down + Power for about 7-10 s (forced restart). BOOT holds the good `emmc1b` image; nothing was being written when it hung (a `sync` ran before the reboot), and the boot-time `e2fsck -p` will tidy up if needed.

Changes made because of it:
- `kernel/patches/linux-wdt-s3c2410-keep-on-shutdown.patch`: module parameter `keep_on_shutdown`; when set, the shutdown hook re-arms the watchdog for one more period instead of stopping it. `kernel/diagnostic/j701f-embedded-ramboot.c` adds `s3c2410_wdt.keep_on_shutdown=1` to the kernel command line.
- Image `wdtkeep` (DTS `-emmchs.dts`) is BUILT and prepared in `build/kernel/boot-update-wdtkeep/` but NOT installed and NOT tested - the phone was unreachable. Install with `tools/run-boot-update.sh wdtkeep` once the phone is back, then check that an ordinary `reboot` and `poweroff` still behave (a power-off that takes longer than 30 s would now end in a reset).
- Rule: never read a whole MMIO regmap through debugfs on this SoC, and never dump the PMU. Read single known registers, from a driver.

Power-domain facts gathered before the incident (vendor live tree): `pd-g3d@10484000`, `pd-dispaud@10484020`, `pd-cam0@10484040`, `pd-mfcmscl@10484060`, each 0x20 long. Their on/off state on mainline is still unknown.

Hardware video decoder (MFC), read-only findings, nothing built: vendor node `mfc0@12C30000`, size 0x10000, SPI 0x162, `samsung,mfc-v6` with `ip_ver = <0x0f>`, clock `aclk_mfc`, in the MFCMSCL power domain. Mainline `s5p-mfc` knows v5/v6/v7/v8/v10, Exynos3250/5433 and FSD; `exynos7870.dtsi` has `cmu_mfcmscl` (disabled in our tree) but no MFC node and no power-domain driver for this SoC. Open questions before any attempt: is the MFCMSCL domain powered at boot (if not, enabling `cmu_mfcmscl` would fault at boot = boot loop), which mainline variant matches `ip_ver 0x0f`, and the decoder needs a firmware file from Samsung's package. The clock-controller probe is built in, so this must NOT be tried while nobody is near the phone.

## After the forced restart: watchdog-through-shutdown, vibrator, microSD, proximity (2026-10-09 night, image `phone1`)

The user force-restarted the phone; it came up on `emmc1b` with a clean filesystem (`e2fsck -p` 0).

- Image `wdtkeep` installed and checked: `/sys/module/s3c2410_wdt/parameters/keep_on_shutdown` = Y, an ordinary `reboot` completes normally. Power-off was not tested (needs someone to switch the phone back on); a hang during reboot has not been provoked on purpose.
- Image `phone1` = `kernel/dts/exynos7870-j7velte-phone1.dts` (includes `-emmchs.dts`; **now the top of the chain**), built with `tools/build-mainline-image.sh phone1 kernel/dts/exynos7870-j7velte-phone1.dts "--allow-audio --allow-sd"`. Config additions: `INPUT_REGULATOR_HAPTIC=y`, `VCNL4000=y`. `tools/build-j701f-dtb.py` gained `--allow-sd`. Audio modules rebuilt for this configuration: `build/kernel/audio-modules-phone1/` (copied to the phone).
  - **Vibrator**: vendor `sec_vib` just switches regulator `VDD_MOTOR_3.3` (LDO32), so `compatible = "regulator-haptic"` with `haptic-supply = <&vdd_ldo32>`. Result: `input: regulator-haptic`; a 250 ms FF_RUMBLE effect was uploaded and played without error. Whether the motor physically buzzed is NOT confirmed (nobody was holding the phone).
  - **microSD (mmc2)**: same pins/supplies as mainline J6 and this phone's vendor tree (gpr4-0..5, fixed 2.8 V regulator on gpc0-0, LDO2 for I/O), card detect `cd-gpios = <&gpa0 1 GPIO_ACTIVE_LOW>`, `cap-sd-highspeed` only. Result: `mmc2: new high speed SDHC card`, `mmcblk2 ... 29.3 GiB` (a card is in the slot), 22.2 MB/s sequential read. eMMC stays `mmcblk0` thanks to the aliases. UHS modes not enabled; hot-plug not tested; the card's contents were not mounted or touched.
  - **Proximity**: Capella CM36672P at 0x60 on `i2c8` (0x138e0000), interrupt gpa0-5, `compatible = "capella,cm36672p"` (mainline `vcnl4000` IIO driver). Result: `iio:device1 vcnl4000` with `in_proximity_raw`; it read 0 three times with nothing near the sensor. Needs a hand over the sensor to verify, and nothing in the desktop uses it yet.
- `tools/run-boot-update.sh` returned 1 once because the prepared `phone1` update expected `emmc1b` in BOOT while `wdtkeep` had just been installed; re-running `prepare-boot-update.py` fixed it (known pitfall).

No mainline driver exists for the S2MU005 charger (only the fuel gauge, `s2mu005-battery.c`); charger control needs a port from the vendor kernel.

## Power-domain state and hardware video codec, first attempt (2026-10-09 night, image `mfc1`)

Power domains: `tools/kmod/j701f_pdinfo.c` is a tiny out-of-tree module that reads only the CONFIGURATION/STATUS pair of the four domains (build with `make -C <kernel src> O=<out> ARCH=arm64 LLVM=1 M=<dir> modules`). Result on mainline: g3d, dispaud, cam0 and mfcmscl all read configuration 0xf, status 0x3000f - **all four are left on by the bootloader**. So CAM0 and MFCMSCL burn power for nothing today, and their clock controllers can be touched without faulting.

BOOT = `mfc1`: `kernel/dts/exynos7870-j7velte-mfc.dts` (includes `-phone1.dts`; now the top of the chain; build flags `"--allow-audio --allow-sd --allow-mfc"`), `&cmu_mfcmscl` okay, node `video-codec@12c30000` with `compatible = "samsung,mfc-v10"`, SPI 354, clock `CLK_GOUT_MFCMSCL_MFC` named "mfc". Kernel command line gained `cma=96M` (CmaTotal 98304 kB). `kernel/patches/linux-mfc-v10-clock.patch` gives mainline's v10 variant its clock (it names none). Modules (not in /lib/modules; `build/kernel/mfc-modules/`, on the phone `~/j701f-mfc-modules/`), load order: mc, videodev, videobuf2-common, videobuf2-v4l2, videobuf2-memops, videobuf2-dma-contig, s5p-mfc. Firmware: the vendor's `/vendor/firmware/mfc_fw.bin` (778,268 bytes, sha256 8eb7c152...) extracted on the host from `system.img.lz4` in the user's Samsung package (`build/kernel/vendor-mfc-firmware/`, proprietary - keep out of any public repository), installed on the phone as `/lib/firmware/s5p-mfc-v10.fw`. `apk add ffmpeg v4l-utils linux-firmware-s5p-mfc` (the Alpine firmware package has v6/v7/v8/v12 but no v10).

Result: the driver probes ("preallocated 8 MiB buffer", decoder `/dev/video0`, encoder `/dev/video1`), the clock tree shows 333 MHz, but opening the device fails: `Interrupt (dev->int_type:0, command:12) timed out`, `Failed to load firmware`, `Timeout while resetting MFC` - the codec's firmware never reports that it started. **Hardware video decoding does not work yet.** Not investigated further. Suspects: the v10 register/boot sequence does not match this IP (vendor says "mfc-v6" + ip_ver 0x0f and uses a separate driver, `drivers/media/platform/exynos/mfc`), the vendor firmware expects that driver's memory layout, or a missing second clock/reset. Next step is to read the vendor driver's start-up sequence for this ip_ver.

## Video codec: why the firmware does not start - diagnosis so far (2026-10-09 night)

Reference files from the vendor driver (`drivers/media/platform/exynos/mfc`, same commit as the other references) are in `build/kernel/vendor-mfc-reference/`. Findings:

- The vendor driver uses `regs-mfc-v10.h` for this SoC, so `samsung,mfc-v10` is the right mainline variant. The reset / RISC_ON / CLOCK_OFF=0 sequence is the same in both drivers (the vendor additionally writes 0x3f7 to SW_RESET first).
- A temporary diagnostic line in the module (not in any patch file; `s5p_mfc_ctrl.c`, printed where "Failed to load firmware" is reported) showed after the timeout: `RISC_ON 0x1 RISC_BASE 0xb9d00000 R2H 0x0 H2R 0x0 FWVER 0x0 CLKOFF 0x0 BUSRST 0x0`, firmware buffer 1 MiB at physical 0xb9d00000, and `/proc/interrupts` shows 0 interrupts on SPI 354. So register access works and the firmware image is where the base register points, but the codec's internal processor never runs it.
- In the vendor tree the codec is the only client of `sysmmu@12C90000` (interrupt SPI 0x160, its own clock) inside `iommu-domain_mfc`, and the normal firmware lives in a reserved region `mfc_nfw` at 0xae600000 (2 MiB); the vendor driver always goes through that IOMMU. Mainline here has no node for that SysMMU and `CONFIG_EXYNOS_IOMMU` is off.

Most likely cause (not proven): the codec's memory accesses pass through that SysMMU, and with its clock gated or the unit unconfigured nothing gets through. Next attempt: `CONFIG_EXYNOS_IOMMU=y`, a `sysmmu@12c90000` node (`samsung,exynos-sysmmu`, SPI 352, clock from `cmu_mfcmscl`), `iommus = <&sysmmu_mfc>` on the codec node, then load the modules again. Both are built-in/boot-time changes, so it needs a new image and someone able to press the recovery key combination.

The modules on the phone are still loaded by hand only; the codec is not used by any application.

## Bluetooth user space, patch firmware, address (2026-10-09 night, image `bt1`)

BOOT = `bt1`; DTS top is now `kernel/dts/exynos7870-j7velte-bt.dts` (includes `-mfc.dts`); build flags unchanged (`"--allow-audio --allow-sd --allow-mfc"`).

- `bluez` was already installed; `rc-update add bluetooth default`. With the ROM firmware a scan already found nine nearby devices.
- Patch firmware: `apk add linux-firmware-brcm` on the phone, `BCM43430A1.hcd` decompressed and copied to `build/kernel/j701f-wifi/firmware/`; `tools/build-mainline-image.sh` now puts it into the initramfs as `brcm/BCM43430A1.hcd` and `brcm/BCM.hcd` (the driver is built in and asks for firmware before the root is mounted; the kernel also has no zstd firmware loading). Log: `BCM43430A1 'brcm/BCM43430A1.hcd' Patch`, then `BCM43438A1 37.4MHz Raspberry Pi 3-0141`, `build 0508`. This is linux-firmware's generic file, not Samsung's own patch; it works for scanning, nothing more is proven.
- Address: `local-bd-address = [02 4c 57 1f 70 02]` (= 02:70:1F:57:4C:02, locally administered, one above the Wi-Fi address; EFS is not read). Before this the controller was AA:AA:AA:AA:AA:AA.
- Config: `CRYPTO_AES=y` (it was a module that is not installed, hence "Unable to create CMAC crypto context", which blocks LE pairing), `BT_HIDP=y`, `BT_RFCOMM=y`, `BT_RFCOMM_TTY=y`. The CMAC message is gone.
- Verified: controller powered, address set, scan finds devices. NOT done: pairing, audio over Bluetooth (PipeWire's Bluetooth module may need `pipewire-spa-bluez`), Wi-Fi/Bluetooth coexistence under load.
- During this work the home Wi-Fi itself lost 20-30 % of pings from the PC as well as from the phone, so slow `apk` downloads that evening were a network problem, not the phone.

Correction to the Bluetooth section (image `bt2`, now in BOOT): in `bt1` the device-tree address was NOT applied - with the patch file loaded the controller reports 43:43:A1:12:1F:AC, which `btbcm` does not list as a default address, so `local-bd-address` was ignored. `kernel/patches/linux-btbcm-43430a1-patched-default-addr.patch` adds that value to the list. With `bt2`: `BCM: Using default device address (43:43:a1:12:1f:ac)` followed by controller address 02:70:1F:57:4C:02; a scan finds eight devices.

## Hardware video codec WORKS (2026-10-09 night, image `mfc2`)

BOOT = `mfc2` (DTS top still `exynos7870-j7velte-bt.dts`). The cause of "firmware never starts" was confirmed by reading the SysMMU in front of the codec (`0x12c90000`, version register 0x60040029): CTRL = 0x3, STATUS = 0x1, i.e. it comes out of reset **enabled and blocked** with no page table, so the codec's processor could not fetch a single byte. With CTRL written to 0 (bypass) the firmware answers at once: 12 interrupts, the device opens, `v4l2-ctl --list-formats-out` lists H.264, H.264 MVC, H.263, MPEG-1/2/4, Xvid, VC-1, VP8, HEVC and VP9.

- `kernel/patches/linux-mfc-exynos7870.patch` (replaces `linux-mfc-v10-clock.patch`): the v10 variant gets its "mfc" clock, and `s5p_mfc_sysmmu_bypass()` in `s5p_mfc_ctrl.c` writes 0 to the SysMMU control register before the codec's processor is released. The SysMMU's registers are the optional second `reg` entry of the codec node (`<0x12c90000 0x1000>` in `-mfc.dts`). This is a stop-gap: no IOMMU driver, the codec addresses physical memory directly (CMA, `cma=96M`).
- Measurement, `~/Videos/test720.mp4` (1280x720, 30 fps, 90 s, H.264), decode to null: hardware (`ffmpeg -c:v h264_v4l2m2m`) real 11.3 s, **user 1.2 s + sys 1.1 s**; software (`-threads 4`) real 14.6 s, **user 53.0 s**. About 24 times less CPU time, and 2700 frames in 11 s is roughly 8x real time.
- Loading: `sudo sh ~/j701f-mfc-modules/load.sh` (repo `system/mfc-load`; modules in `build/kernel/mfc-modules/`). Not loaded at boot. `/dev/video0` (decoder) and `/dev/video1` (encoder) are root-only for now.
- Not done: letting applications use it (device permissions, VLC/Firefox/GStreamer configuration - ffmpeg needs the `h264_v4l2m2m` decoder selected explicitly), other codecs than H.264, the encoder, long-run stability, and replacing the bypass with real IOMMU support.
- The same SysMMU reset state is worth remembering for the scaler/JPEG block (`sysmmu@12C80000`) and probably the camera.

Video codec follow-up (same night, no new image): `system/video-udev.rules` -> `/etc/udev/rules.d/60-j701f-video.rules` gives `/dev/video*` to group `video` (the user is a member), and `/etc/local.d/j701f-audio.start` (`system/audio-autoload`) now also runs `~/j701f-mfc-modules/load.sh` under the same reset guard, so the codec is available after boot (the autoload itself has not been through a reboot yet). As the normal user: 1280x720 and 1920x1080 H.264 decode fine with `ffmpeg -c:v h264_v4l2m2m`; **640x360, 848x480 and 854x480 fail** every time ("Error submitting packet to decoder: Out of memory", then I/O error; kernel: `vidioc_qbuf: Call on QBUF after unrecoverable error`, `vidioc_try_fmt: Unsupported format for destination`). Not a memory shortage (CmaFree about 55 MB at the time). Cause not found - a limitation to fix before a player is pointed at the decoder, since most web video is below 720p. `apk` has `mpv` (not installed) as a candidate player with V4L2 decoding.

Power domains: turning the unused CAM0 domain off was considered and not tried: on USB power the fuel gauge reports about 10 mA with status Full, so a saving could not be measured, and the vendor's power-down sequence for a domain is more than one register write.

## Video codec: low resolutions fixed, mpv uses it (2026-10-09 night, image `mfc3`)

BOOT = `mfc3`. The 360p/480p failure was an address problem, found with the driver's debug level (`echo 2 > /sys/module/s5p_mfc/parameters/debug`): the error interrupt 0x37 came on the very first command (sequence header) with the stream buffer at 0xb9c40000 while the firmware base was 0xb9d00000. Without an IOMMU every buffer address must be above the firmware base; small stream buffers were being placed in free CMA space below it, large ones (720p and up) happened to land above.

Fix: a dedicated memory region for the codec, so the driver's preallocation (which holds the firmware) is the first and lowest allocation in it.
- `-mfc.dts`: `/reserved-memory/video-codec@a8000000`, `compatible = "shared-dma-pool"`, `reusable`, 96 MiB at 0xa8000000, and `memory-region = <&mfc_mem>` on the codec node. `cma=96M` was removed from the kernel command line again (global CMA back to 32 MiB).
- `linux-mfc-exynos7870.patch`, third part: `s5p_mfc_configure_common_memory()` calls `of_reserved_mem_device_init()` (mainline only honours `memory-region` in the two-port layout of the oldest codec version).
- `tools/build-j701f-dtb.py`: a reserved region may now omit `no-map` if it is a `reusable` `shared-dma-pool`.

Result, decoder loaded automatically at boot, normal user: 640x360, 848x480, 854x480, 1280x720 and 1920x1080 H.264 all decode without errors.

Player: `apk add mpv` (0.41); `system/mpv.conf` -> `/etc/mpv/mpv.conf` with `hwdec=v4l2m2m-copy`. mpv's log shows `Using underlying hw-decoder 'h264_v4l2m2m'`. Checked with `--vo=null` only; nobody has watched a video through it yet. VLC remains the default video application (user's choice) and still decodes in software.

## Audio: main microphone capture (2026-10-09 night, modules only, BOOT still `mfc3`)

`linux-audio-j701f-codec-card.patch` updated; modules in `build/kernel/audio-modules-phone1/` and on the phone.
- Codec (`j701f-cod3026x.c`): capture stream "AIF Capture" (48 kHz, S16, stereo), DAPM chain `IN1L -> MIC1_PGA -> ADC` with supplies `VMID` (vendor `cod3026x_capture_init/deinit`: ADC digital power and reset, VMID fast charge 5k for 140 ms then 50k, IGEN) and `MIC1 Bias` (internal bias 1 + bias LDO, register 0x10), the vendor `cod3026_power_on/off_mic1` sequence, ADC unmute 120 ms after power-up. Bias voltages as in the vendor tree (bias1 = 1, bias2 = 1, LDO = 3). New controls: `MIC1 Boost Volume` (0-3), `MIC1 Volume` (0-31), `ADC Gain`.
- Card (`j701f-audio.c`): no longer playback-only; mixer `DOUTMX1` channel-1 select = 1 (vendor "CH1 DOUT Select" = AIF4IN, the codec's input) so recorded audio reaches the AP.
- Result: `/proc/asound/pcm` shows `playback 1 : capture 1`. Test: 5 s `arecord -D hw:0,0 -f S16_LE -r 48000 -c 2` with boost 2 / MIC1 20 while a quiet 1 kHz tone played from the speaker for about 2.5 s in the middle. Per-second 1 kHz amplitude in the recording: 0, 1028, 822, 653, 6; 3 kHz stays below 20. The microphone path records the phone's own speaker, so it works; levels and quality have not been judged by ear and no gain defaults were tuned.
- Not ported: MIC2 (second microphone), MIC3 (headset microphone, bias 2), line in, jack and button detection, call audio.

## Charger status driver (2026-10-10, image `chg1`)

BOOT = `chg1`; DTS top is now `kernel/dts/exynos7870-j7velte-charger.dts` (includes `-bt.dts`), same build flags.

- `kernel/patches/linux-power-j701f-s2mu005-charger.patch`: `drivers/power/supply/j701f-s2mu005-charger.c`, always built as a module (`obj-m`). I2C client at 0x3d on `i2c4` (`j701f,s2mu005-charger`). **Read only**: it writes no charger register. Power supply `s2mu005-charger` (type USB) with ONLINE (STATUS0 bit 7, VBUS OK), STATUS and CHARGE_TYPE (STATUS0 low nibble, vendor state table), HEALTH (STATUS1 bits 6:4, 3 or 5 = good as in the vendor driver), INPUT_CURRENT_LIMIT (CTRL2) and CONSTANT_CHARGE_CURRENT (CTRL7). No interrupt: STATUS0 is polled every 5 s and `power_supply_changed()` is called when it changes.
- Reference files: `build/kernel/vendor-charger-reference/` (vendor `s2mu005_charger.c/.h`, `s2mu005-private.h`).
- Loaded at boot by `/etc/local.d/j701f-audio.start`, which now also inserts every module in `~/j701f-misc-modules/` (repo copy `build/kernel/misc-modules/`).
- Result with the USB cable in: `S2MU005 charger status 0xb7`, ONLINE=1, STATUS=Full, HEALTH=Good, input limit 500 mA, charge current 450 mA; UPower lists `line_power_s2mu005_charger` next to the battery. Unplugging and a charging (not full) battery have not been observed, since the phone stays on the cable.
- The initramfs still sets the MUIC switch through raw I2C transfers to the same address; that keeps working with a kernel client bound. The MUIC itself still has no kernel driver, and the charger's limits are not adjustable from Linux.

## Power domain experiment: CAM0 off (2026-10-10, modules only, BOOT still `chg1`)

- `tools/kmod/j701f_pdinfo.c` gained `off=<domain>` / `on=<domain>` module parameters (write CONFIGURATION 0 or 0xf, wait up to 100 ms for the low STATUS nibble). `insmod j701f_pdinfo.ko off=cam0`: `cam0 -> 0x0: status 0x170000 after 1 ms`; the system stayed up. So an idle domain on this SoC can be switched with the single PMU register write.
- `tools/kmod/j701f_cam0_off.c` -> `build/kernel/misc-modules/j701f_cam0_off.ko`, in `~/j701f-misc-modules/` on the phone and therefore loaded at boot behind the reset guard: switches CAM0 off at load, back on at unload. Verified after a reboot: `CAM0 power domain off, status 0x170000`, everything else present (sound card, /dev/video0, charger, GPU limit).
- The saving is NOT measured: the phone is on USB power and the fuel gauge shows about 10 mA with status Full. Remove this module before any camera work.
- Not done: a real genpd driver (MFCMSCL could be off while the codec idles; G3D and DISPAUD are in use). The mainline `samsung,exynos5433-pd` driver uses the same register layout and value (0xf), which is what these writes mimic.

Unrelated observations from the same boot:
- One `WARNING: drivers/gpu/drm/panfrost/panfrost_mmu.c:478 at panfrost_mmu_map` (the `drm_gem_shmem_get_pages_sgt()` failure check) from `QSGRenderThread` at 43.7 s, right after a burst of Panfrost shrinker "Purging ..." lines while the desktop was starting and the module loads were allocating CMA memory. No GPU fault or timeout followed and the desktop came up normally. Seen once; if it recurs, look at memory pressure during boot (two CMA areas now: 96 MiB for the codec, 32 MiB global).
- `tools/phone-screenshot.sh` produced truncated PNGs since the display scale became 160 % (KWin now returns 450x800, stride 1800; the script assumed 720x1280). It now passes the size reported by `kwin-screenshot` to `raw-to-png.py`. The earlier "truncated PNG while VLC was open" note was this, not VLC.

## Audio: MIC2/MIC3 inputs, and the MUIC check in the charger driver (2026-10-10, modules only, BOOT still `chg1`)

Codec (`linux-audio-j701f-codec-card.patch`): one generic microphone power sequence for the three inputs (vendor `cod3026_power_on/off_mic1..3`, no bypass mode), DAPM switches `MIC1 On`, `MIC2 On`, `MIC3 On` on the vendor MIC_ON register 0x78 (bits 4/5/6; MIC1 is the default), `MIC3 Bias` supply (internal bias 2 for the headset microphone, register 0x10 + CTRM_MCB2 in 0x18), MIC2 on bias 1 as in the vendor `mic-bias-mode`, gain controls `MIC2/MIC3 Volume` and `Boost Volume`.

Silent check only (the user does not want sound tests; nothing was played): 2 s recordings with boost 2 / gain 20, DC removed, second half analysed:
- MIC1 only: rms 32.6, peak 580 (room noise).
- MIC2 only: rms 1.0, peak 4.
- MIC3 only (no headset plugged): rms 1.2, peak 4.
So MIC1 picks up the room; MIC2 and MIC3 deliver essentially digital silence. For MIC3 that is expected without a headset. For MIC2 it is **undecided**: either this phone has no microphone on that input, or the MIC2 path is not working. It needs a test with sound (and the user's go-ahead) or the phone's schematic/vendor mixer paths.

Charger module (`linux-power-j701f-s2mu005-charger.patch`): at probe it now reads the MUIC registers CTRL1 (0xb2) and SW_CTRL (0xb5) and rewrites them to 0x13/0x24 only if they differ. Log on this boot: `MUIC already on the USB path (0x13/0x24)`. The initramfs step that sets them first is unchanged, so this is a check/restore, not yet a replacement: a real MUIC driver would also need cable-type detection and its interrupt.

Still untested for lack of a listener or a plug: headphone and earpiece outputs, the headset microphone with a headset, jack detection (not written).

## Cable type, a failed power-domain experiment, and parallel work with Codex (2026-10-10)

- Charger module: `POWER_SUPPLY_PROP_USB_TYPE` from the MUIC's DEV_TYPE1 register (0x4a; bit 2 USB/SDP, bit 5 CDP, bit 6 DCP; the ADC register is 0x49). With the phone on a PC port: `usb_type` = `Unknown [SDP] DCP CDP`, DEV_TYPE1 = 0x04. Wall charger and charging-port cases need the owner to change the cable.
- MFCMSCL power domain: with `s5p_mfc` unloaded, `j701f_pdinfo off=mfcmscl` then `on=mfcmscl` both followed within 1 ms. After reloading the driver the SysMMU was back at 0x3 (so the domain really lost its state), the first decode worked, the second **hung** and later ones failed until a reboot. Cause not analysed; the clock controller's registers are in that domain and the clock framework knows nothing about the cycle. Conclusion: this domain cannot be switched by a bare PMU write; it needs a real power-domain driver that the clock controller and the codec are tied to. After a reboot four decodes in a row were fine again. CAM0 (nothing in it is used) stays off.
- Parallel work: on 2026-10-10 the owner said Claude and ChatGPT Codex will work at the same time, both with full authority except playing sound. Protocol: `tools/coord.sh` (locks `phone` / `kbuild`, board, message inbox), `docs/coordination/README.md`, `STATE.md`, `CODEX-START.md`, `BOARD.md`, `messages/`.

## Audio: headset jack reporting (2026-10-10, codec module only, BOOT still `chg1`)

`j701f-cod3026x.c`: the jack-detection block is set up with the vendor defaults (DET_ON 0x42 then 0x43, MIC_DET 0xff, DET_TIME 0xff, KEY_TIME 0xf2, MICBIAS2 0x0b), a jack "Headset Jack" is created on the card (`snd_soc_card_jack_new`, SND_JACK_HEADSET) and STATUS1 (0x0b; bit 0 plug, bit 1 microphone) is polled every 500 ms. No interrupt, no button handling, and **no automatic switch between speaker and headphones** - only the state is reported (ALSA control `Headset Jack`, input device `J701F Headset Jack`).

Checked with nothing plugged in: `headset jack: removed (STATUS1 0x0)`, control value off, input device present. Insertion has not been observed (needs a headset in the socket). A wrong reading with a plug in, and the automatic routing, are the next steps once someone can plug one in.
## Device optimisation, first pass (2026-10-10 night, image `pfshrink`)

New goal from the user: make the phone feel usable (application start-up, Angelfish black areas while scrolling, memory). Wiki digest: `wiki/reference/performance.md`.

- **Image `pfshrink`** = `chg1` + `kernel/patches/linux-panfrost-shrinker-switch.patch`: module parameter `/sys/module/panfrost/parameters/shrinker_purge` (default 1 = upstream behaviour; 0 makes the shrinker's count callback return 0). DTS top unchanged (`charger`).
- **Black areas diagnosis:** kernel log shows bursts of Panfrost "Purging" lines plus `WARN_ON(bo->base.madv != PANFROST_MADV_WILLNEED)` in `panfrost_gem_open` while Angelfish runs under memory pressure. Mesa marks cached BOs DONTNEED; some are still shared with KWin. A/B on the phone: purge on = 20-40 purges and 3-7 WARNs per browser run; purge off = 0 purges, still 3-5 WARNs, Shmem about 90 MB higher. Screenshots showed no black area in either run, so the visual fix is NOT confirmed, only the purging is gone. The WARN itself (a DONTNEED BO opened by another context) is a Mesa/Panfrost sharing issue and is still there.
- **`system/tune` -> `/etc/local.d/j701f-tune.start`:** zram0 1200M (lzo-rle; zstd and lz4 are not built), swap priority 100, swappiness 100, page-cluster 0, root remounted noatime, read_ahead_kb 512, `shrinker_purge=0`.
- **earlyoom** installed and in the default runlevel (`system/earlyoom.conf` -> `/etc/conf.d/earlyoom`): prefers web renderer processes, avoids KWin/plasmashell/PipeWire/sshd.
- **Session:** `system/session/webengine-env.sh` -> `~/.config/plasma-workspace/env/j701f-webengine.sh` (`QTWEBENGINE_CHROMIUM_FLAGS`: low-end device mode, renderer-process-limit 3, 4 raster threads, GPU rasterisation). Per-user autostart overrides hide DiscoverNotifier and the Evolution alarm notifier. `AnimationDurationFactor=0.5` in kdeglobals.
- **Measurements:** Angelfish cold start 10.2 s with six restored tabs, 7.5-7.9 s with two, 5.8 s warm; CPU sits at 1586 MHz during start (CPU-bound), GPU stays near 343 MHz while scrolling. plasma-settings is busy about 7 s after start, foot about 1 s. Browser PSS with three tabs 782 -> 764 MB with the flags.
- I removed my own leftover test tabs from Angelfish's `tabs.json` (backup next to it as `tabs.json.claude-backup`); the user's two tabs remain.
- Not done: freezing background applications, hardware video decode in the browser, a standard benchmark.

## Panfrost purge mode 2 (2026-10-10 night, image `pfshrink4`)

Correction to the section above: `shrinker_purge=0` was a mistake. Evidence and the replacement:

- Per-client GPU memory (`/proc/PID/fdinfo`, `drm-resident-memory` / `drm-purgeable-memory`): plasma-keyboard alone held 241 MB resident, 220 MB of it purgeable, pinned for good with purge off (`Unevictable` 325-590 MB after boot).
- A one-second memory sampler during session start (`~/bootmem-sampler.sh` on the phone, log `~/bootmem.log`) shows a transient GPU allocation spike: Shmem 1259 MB with purge off, about 870 MB with purging. With purge off one boot ended with `MESA: error: DRM_IOCTL_PANFROST_CREATE_BO failed (err=12)` in `~/.local/share/sddm/wayland-session.log` and no plasmashell.
- WARN call traces: `Chrome_InProcGpu` and `QSGRenderThread` (both inside Angelfish) in `drm_gem_prime_fd_to_handle -> panfrost_gem_open`: dma-buf imports of BOs that are in DONTNEED.
- `linux-panfrost-shrinker-switch.patch` is now an int parameter: 0 never purge, 1 upstream (default), 2 = the shrinker skips BOs with `handle_count > 1` or a live `dma_buf`, and `panfrost_gem_open()` moves a DONTNEED (not yet purged) BO back to WILLNEED and off the shrinker list (lock order resv -> shrinker_lock -> mappings.lock, as in the madvise ioctl); a purged BO opened by a second client logs one ratelimited line instead of a WARN.
- `system/tune` writes 2. Measured on `pfshrink4`: two Angelfish runs with a 700 MB anonymous-memory hog and 18 injected swipes: 0 WARNs, 0 "purged buffer opened" lines, 36-61 purge messages, page rendered (`build/screenshots/af-pressure-mode2-v3.png`). Same test in mode 1: 3 WARNs. One minute after boot: MemFree about 1000 MB and Shmem 115 MB (purge off: 485 MB and 568 MB).
- Still not visually confirmed that the black areas are gone; the automated captures never showed one.
- Images on the way: `pfshrink2` was built without rebuilding the kernel (my slip: `tools/build-mainline-image.sh` only packages; `python3 tools/build-kernel.py panfrost --jobs 11` must run first), `pfshrink3` had the shrinker half only. The shared kernel now also carries Codex's three DSIM patches (inactive: DSIM is disabled in the `charger` DTS).
- `tools/run-boot-update.sh`: the 3.18 side got DHCP leases outside the scanned range (.200, .72, .71) tonight; the script now asks the USB serial shell for the wlan0 address first, accepts `J701F_PHONE_IP`, and scans .140-.230.
- Open: which client causes the start-up GPU spike (sample `drm-total-memory` per client during boot).

## Background-application freezer (2026-10-10 night, userspace only)

User request: applications that stay in the background for long should sleep or be closed to save RAM.

- `system/session/freezer/`: `j701f-freezer.py` (session D-Bus service `org.j701f.Freezer`, python3 + py3-dbus + py3-gobject3, the latter installed tonight), `freezer.js` (KWin script the daemon loads through `org.kde.KWin /Scripting`; reports `windowActivated`, `windowAdded`, `unresponsiveChanged` with pid as string), autostart entry, configuration file.
- Policy: SIGSTOP the whole process tree of a window's pid after `idle_seconds` (300) out of the foreground, SIGCONT on activation, on KWin's "unresponsive" signal, when the home screen (plasmashell) is in front, on daemon exit, and for leftovers at daemon start. Never stopped: shell, KWin, keyboard, terminals, dialer, spacebar, anything with an uncorked PulseAudio/PipeWire stream (`pactl -f json list sink-inputs/source-outputs`, a query only), names in `exclude`.
- While the screen is locked or off the active "window" belongs to kwin_wayland itself; it is treated as an ordinary foreground, so applications behind a locked screen do get stopped.
- Phone test with `idle_seconds = 25`: plasma-settings and kclock went to state T, activation through a KWin script continued the activated one within 2 s, `closeWindow()` on the stopped kclock: continued by the unresponsive signal and gone after 3 s, no kwin_killer_helper dialog.
- dbus-python note: `loadScript` is overloaded on the bus; without `signature='ss'` the call raises TypeError.
- Not measured: real memory/battery effect. Known cost: a stopped application receives no messages and finishes no download.
- Start-up GPU spike attributed with a per-client fdinfo sampler: plasmashell 560 MB resident / 510 purgeable for a moment, plasma-keyboard 243 / 223. With purge mode 2 a boot now ends without touching swap.

## Angelfish start-up profile and page-cache prewarm (2026-10-10 night)

- `perf` installed on the phone (`apk add perf`; `perf_event_paranoid=-1`, `kptr_restrict=0` set by hand for that boot only). `perf record -a -F 199` over a cold Angelfish start: 77 % of all samples idle, QtWebEngineProcess 7.7 %, angelfish 4.9 %, ThreadPoolForeground 3.6 %; libraries are stripped, so no useful symbols. `/proc/stat` over 14 s: about 1.4-1.6 cores busy on average, iowait 4.2 s cold against 0.5 s warm.
- Timestamped log (stdout through a line stamper), warm: 1.4 s "Migrations finished" (exec + musl dynamic linking; libQt6WebEngineCore.so is 171.6 MiB), 2.4 s Vulkan-instance failure message (WebEngine init), 3.2 s QML up, 4.6 s "Adblock ready", 5.4 s first "WebView completed", then about 0.25 s per restored tab. Cold: 7.0 s to the first view.
- `system/tune` now starts a background subshell that, 75 s after boot, reads libQt6WebEngineCore/Quick, QtWebEngineProcess, the resource paks and the angelfish binary with `nice cat` (2.4 s). After `drop_caches` plus that read the start took 5.4 s, the same as warm.
- This corrects my earlier "start-up is CPU-bound" statement (Codex questioned it): the CPU is at 1586 MHz but mostly one thread at a time.

## CPU idle (core power-down) experiment (2026-10-10 night, image `cpuidle1`)

First step towards suspend. Until now the cores only did WFI: upstream `exynos7870.dtsi` has no idle states.

- Vendor reference saved in `build/kernel/vendor-cpuidle-reference/` (DT idle states, `cpuidle-exynos64.c`, `exynos-powermode.c`, `exynos-pmu.c`, `psci.c`). Vendor C2: PSCI CPU_SUSPEND with `arm,psci-suspend-param = <0x0010000>`, and before the call `exynos_cpu_down()` clears bits 3:0 of the core's PMU CPU_CONFIGURATION register (0x2000 + 0x80 * ((cluster << 2) | core)); `exynos_cpu_up()` sets them again on an early wake-up.
- New DTS top `kernel/dts/exynos7870-j7velte-cpuidle.dts`: one `arm,idle-state` (`local-timer-stop`, param 0x0010000, latencies 100/500/2000 us instead of the vendor's 35/90/750) for all eight cores.
- `kernel/patches/linux-cpuidle-psci-exynos7870-default-off.patch`: on `samsung,exynos7870` the PSCI idle driver registers every deep state with `CPUIDLE_FLAG_OFF`. A boot never enters the state; a core is opted in with `echo 0 > /sys/devices/system/cpu/cpuN/cpuidle/state1/disable`. This is what made the experiment safe to run unattended: every hang below ended in a watchdog reboot into a normal system.
- `tools/kmod/j701f_cpupd.c` (built to `build/kernel/misc-modules/j701f_cpupd.ko`, on the phone in `~/j701f-cpuidle/`, deliberately NOT in `~/j701f-misc-modules`, which is loaded at every boot): CPU PM notifier doing the vendor's PMU write, counters in `/sys/module/j701f_cpupd/parameters/`.
- Results:
  - One opted-in core never enters the state: with the hrtimer broadcast device the only candidate always owns the broadcast timer (-EBUSY). At least two cores are needed.
  - Plain PSCI without the PMU write, cores 1-7: hang within seconds, watchdog reboot.
  - With the module, cores 4-7 for 90 s: 4087 entries, fine. Cores 1-7 for 90 s: about 9000 entries, fine; later about 60000 more during a 5-minute measurement, fine.
  - With the module and core 0 included: fine for 20 s once (cpu0 2788 entries, 73 rejected), then four hangs after 20-80 s. Core 0 takes every device interrupt, so the suspicion is an interrupt arriving during the power-down sequence; not investigated further.
  - Benefit: not measurable with what the phone offers while on USB power (SoC temperature 33.9/33.6 C off against 35.3/33.0 C on, i.e. noise; the fuel gauge shows charger current).
- Decision: left off. The image stays in BOOT because the state is inert unless opted in. Before using it daily: understand the core-0 hang (try moving interrupts, compare `wakeup_from_c2()` and the vendor's cluster handling), and measure on battery.
- The stamp guards did their job on every watchdog reboot ("previous load did not survive"): audio and the frequency raise stayed off until I removed `/var/lib/j701f-*.pending` and rebooted cleanly.

## Start-up memory: no more swapping while the desktop starts (2026-10-10 night)

- With zram and swappiness 100 from the first second, the kernel answered the home screen's GPU allocation spike by swapping out 270-290 MB of the desktop in some boots (SwapFree 913 of 1200 MB at 58 s).
- `system/tune` now sets swappiness 10 at boot; a background job waits 75 s, runs the shrinkers once (`echo 2 > /proc/sys/vm/drop_caches`, which makes Panfrost purge the released buffers: Shmem 374 -> 101 MB), reads the browser engine into the page cache and only then sets swappiness 100.
- Verified with the boot sampler: SwapFree stays at 1195 MB through start-up, plasmashell up, no `CREATE_BO` error.

## VLC uses the hardware H.264 decoder (2026-10-10 night, userspace only)

- VLC 3.0.23 on Alpine has only X11 video outputs (runs through Xwayland, vout "gl"); FFmpeg has `h264_v4l2m2m`. `~/.config/vlc/vlcrc`: `avcodec-codec=h264_v4l2m2m` (backup `vlcrc.claude-backup-hwdec`). VLC's avcodec module falls back to the default decoder when the forced one does not match the stream ("Decoder `h264_v4l2m2m' can't handle VP80", then `codec (vp8) started`), so other formats and audio are unaffected.
- Silent tests only (`--no-audio`, `-I dummy`/`-I rc`, environment `DISPLAY`/`XAUTHORITY` from plasmashell). test720.mp4 (1280x720, 30 fps), 12 s window: software 3081 jiffies (256 % of a core) and 582 "picture is too late" warnings; hardware 448 jiffies (37 %) and 0. Seeks to 20 s, 5 s, 25 s through the rc interface: no crash, 0 late pictures, four harmless "buffer deadlock prevented" lines.
- This is very likely the cause of the user's earlier report (video froze after 15 s in VLC, closed on seeking): software decoding could not keep up.
- Dependency: without the MFC modules loaded, H.264 in VLC has no decoder. Audio path with this option was not exercised (no sound tests).

## Suspend-to-idle works (2026-10-10 night, images `susp1`, `susp2`)

- `/sys/power/state` offers `freeze mem disk`, `mem_sleep` is `[s2idle]` only (PSCI 0.1 from the DT, no SYSTEM_SUSPEND). RTC `s5m-rtc` (s2mps15-rtc) has a wake alarm; its interrupt is the PMIC line on gpa0-2 (`/sys/power/pm_wakeup_irq` = 39 after every test).
- Safety net: `kernel/patches/linux-wdt-s3c2410-keep-on-suspend.patch` (`/sys/module/s3c2410_wdt/parameters/keep_on_suspend`, default 0): suspend/resume callbacks only refresh the watchdog instead of stopping it, so a hang resets the phone; the sleep must then stay under the 15 s timeout. Config fragment gained `CONFIG_PM_DEBUG`, `CONFIG_PM_SLEEP_DEBUG`, `CONFIG_PM_ADVANCED_DEBUG` (pin in `kernel/inputs.json` updated; the rebuilt audio/MFC/charger modules are byte-identical, so the copies on the phone were kept).
- Test harness (scratch, on the phone results in `~/j701f-cpuidle/suspend-*.txt` and `*-dmesg.txt`): root script sets `pm_test`, writes `freeze` to `/sys/power/state`, saves dmesg, and reboots if the gateway does not answer 25 s later. For the first rounds the extra modules were kept from loading by renaming `~/j701f-audio-modules/load.sh`.
- `pm_test=freezer`: fine. `pm_test=devices` on `susp1`: every driver suspended (574 ms) and resumed (227 ms), but `brcmfmac: brcmf_ops_sdio_suspend: Failed to set pm_flags 1` and afterwards `error while changing bus sleep state -110`; network dead, the script rebooted. Fix in the new DTS top `kernel/dts/exynos7870-j7velte-suspend.dts`: `keep-power-in-suspend` on `&mmc1`, plus `wakeup-source` on the power and home keys (image `susp2`). Also copied the four Broadcom firmware files to `/lib/firmware/brcm/` on the root filesystem: the PM firmware cache asked for them ("Direct firmware load ... failed with error -2") because they only existed in the initramfs.
- On `susp2`: `devices` and `platform` pass with Wi-Fi alive (`processors` and `core` are not valid for s2idle and return an error at once). Real sleeps: 6 s (watchdog kept), 60 s (watchdog stopped as upstream does, "watchdog enabled" on resume), 8 s with audio, MFC, charger and CAM0 modules loaded. plasmashell and KWin alive afterwards, screenshot `build/screenshots/after-suspend.png`.
- With `pm_print_times` on, resume seemed to take 4-5 s; that was the debug output being flushed to the serial console. With it off: 244.20 -> 244.65, about 0.45 s.
- Codec driver: the headset poll (delayed work every 500 ms) ran during suspend and failed with -108 on the suspended I2C adapter. `j701f-cod3026x.c` now queues it on `system_freezable_wq` (patch file and module updated; the new module is on the phone and loads from the next boot).
- Remaining message on resume: `tm2-touchkey 3-0020: failed to read i2c data: -6` (once).
- Not done on purpose: no automatic suspend. Wi-Fi is not a wake-up source, so a sleeping phone cannot be reached over SSH; waking by power/home key is configured (`wake enabled for irq 69 (gpa0-0)`, `70 (gpa1-7)`) but nobody could press a key tonight. Power saving unmeasured; the cores only do WFI in s2idle (the PSCI state is off and has no `enter_s2idle`).

## Display path analysis: where the frame rate goes (2026-10-10 morning, images `fbmem1`-`fbmem3`)

Correction first: several of my earlier "scroll" runs tonight did not scroll the page I thought. A URL given to Angelfish on the command line opens as a background tab behind the restored ones, so the injected swipes scrolled the first restored tab. The memory-pressure results (purges, WARNs) stand as browser-under-pressure runs; they say nothing about a particular page. And any graphics number taken while the lock screen was up or the screen had dimmed is invalid (see below).

- Raw GPU: `EGL_PLATFORM=surfaceless peglgears` 3462 FPS. Through KWin: `es2gears_wayland` 38 FPS windowed or full screen (mesa-demos installed for this). So the output path, not the GPU, sets the frame rate.
- KWin opens `/dev/dri/card0` (simpledrm) and `renderD128` (Panfrost): multi-GPU CPU copy. With `KWIN_LOG_PERFORMANCE_DATA=1` (set temporarily through `~/.config/plasma-workspace/env/`, removed again, CSV deleted): render start to end 3.2 ms; render end to page flip 49.5 ms; flip to flip 26.5 ms.
- `perf record -a`: 95 % idle; the busy part is the DRM commit worker in `drm_fb_xrgb8888_to_argb8888_line`, `memcpy_toio` and `memcpy`.
- simpledrm has two paths. With only `reg` the framebuffer is I/O memory (temp line buffer + `memcpy_toio`). New DTS top `kernel/dts/exynos7870-j7velte-fbmem.dts` adds `memory-region = <&{/reserved-memory/bootloader-fb@67000000}>` to the simple-framebuffer node ("preferring "memory-region" over "reg"" in dmesg): flip to flip 23.0 ms, 44 FPS.
- Verification without eyes on the panel: `/dev/mem` at 0x67000000 (720x1280x4, BGRA, alpha 255 everywhere) dumped and compared with a KWin screenshot taken at the same time: mean absolute difference 0.1 of 255 (`build/screenshots/fbchk-*-devmem.png`). The same check right after `--dpms on` reads black for a moment; wait a few seconds.
- Tried and dropped: mapping the framebuffer cacheable with a `dcache_clean_poc()` after each update (`kernel/patches/staged/linux-simpledrm-j701f-cached-framebuffer.patch`, image `fbmem2`). Pixels correct, frame rate unchanged (42 FPS): the time is in the scalar per-pixel loop, not in the stores. Tree restored, image `fbmem3` = `fbmem1` DTS on the clean kernel; that is what is in BOOT.
- Frequency: GPU pinned at 1001 MHz changes nothing. CPU `performance` governor: 51.5 FPS. FPS against `scaling_min_freq`: 546 MHz 41.7, 902 47.0, 1144 48.9, 1352 50.2, 1586 51.1. `system/inputboost` (`/usr/local/sbin/j701f-inputboost`, started by the tune script as root): raises `scaling_min_freq` to 1144000 while events arrive from the touchscreen, touch keys or hardware keys, back to 546000 after 1.5 s. Verified with an injected swipe.
- **Software brightness.** `kscreen-doctor -o` shows "Brightness control: supported, set to 100% and dimming to 30%" once the session has been idle. In that state, or with brightness set to 50 % through `org.kde.ScreenBrightness`, the same es2gears run gives 20 FPS instead of 42; back at 100 % it is 42 again. KWin applies brightness in an extra pass because the output has no backlight. My first scroll numbers (18 callbacks/s, GPU "saturated") were taken dimmed.
- Scroll benchmark: Codex's `bench/scroll` page, scratch copy on the phone with an auto-start script, a local server on 127.0.0.1:8765 and the viewport check relaxed (Angelfish hides its toolbar while scrolling, which the original page rejects as "Viewport or scale changed"); tabs.json swapped for a single-tab file during the run and restored afterwards. At full brightness on `fbmem3`: 45 callbacks/s, median 16.7 ms, p95 33.4 ms, one interval over 50 ms in 12 s; identical with my WebEngine flags, without GPU rasterisation, and with no flags.
- Session unlock for tests: `loginctl unlock-sessions` and `org.freedesktop.ScreenSaver.SimulateUserActivity`.
- Open: a cheap brightness (a software gamma LUT in the simpledrm copy would let KWin drop its extra pass) or, properly, the panel driver; the remaining 44 -> 60 FPS needs zero-copy scanout.

## Software gamma LUT tried and dropped (2026-10-10 morning, image `fbmem4`; BOOT is `fbmem5`)

- Idea: advertise a 256-entry GAMMA_LUT on the simpledrm CRTC and apply it in the framebuffer copy, so that KWin would not need its own brightness pass. `kernel/patches/staged/linux-simpledrm-j701f-software-gamma.patch`, DT property `j701f,software-gamma`, runtime switch `/sys/module/drm_sysfb_helper/parameters/j701f_software_gamma` (off by default so that a bug could not turn into a boot loop).
- Result on the phone: "software gamma LUT enabled" in dmesg, no crash, but KWin 6.6 does not use the legacy gamma LUT for SDR brightness. At 50 % and 20 % the framebuffer content was already darker with the LUT ignored (mean green 130 -> 96 -> 65) and es2gears stayed at 20.7-21.0 FPS with the LUT ignored or applied; 43.8 at 100 %.
- Tree restored, patch moved to `staged/`, property removed; image `fbmem5` is byte-identical to `fbmem3` (same SHA-256) and is what BOOT holds. Brightness is back at 100 %.
- What would work instead (not started): a kernel backlight device (`/sys/class/backlight`) whose value the simpledrm copy applies with the per-pixel loop from that patch. Plasma drives a real backlight device through powerdevil and then leaves the picture alone. The proper fix is still the panel driver.

## Faster framebuffer copy (2026-10-10 morning, image `fbfast1`)

- `kernel/patches/linux-sysfb-j701f-fast-argb-copy.patch`: for XRGB8888 -> ARGB8888 with both sides in ordinary memory, `drm_sysfb_xrgb8888_to_argb8888_fast()` ORs the alpha into two pixels per 64-bit word, source straight to framebuffer (the generic helper copies each line to a temporary buffer first). Falls back to the generic helper otherwise.
- es2gears full screen, unlocked and undimmed: 44 -> 49.5 FPS at the 546 MHz floor; 53.3 at 902, 54.2 at 1144, 55.1 at 1586 MHz. GPU floor 343..1001 MHz makes no difference (54.8-55.2). perf: the copy is now about 4.5 ms per frame (was about 8).
- Pixels verified again through `/dev/mem` against a screenshot (difference 0.1 of 255, alpha 255).
- `system/inputboost` hold time raised from 1.5 to 3 s.

## Software backlight: brightness without the frame-rate penalty (2026-10-10 morning, images `bl1`, `bl2`)

- `kernel/patches/linux-zz-simpledrm-j701f-software-backlight.patch` (on top of the fast-copy patch; `zz` for the sort order of a from-scratch apply). DT property `j701f,software-backlight` on the simple-framebuffer node: simpledrm registers backlight device `j701f-panel` (raw, 0-255), reports its connector as DSI, and the plane update scales every pixel by level/255 through a 256-entry table when the level is below 255. A level change calls `drm_sysfb_plane_redraw()` (modeset locks, vmap of the plane's current framebuffer, full copy) so a still picture changes too.
- First version wrote 32-bit pixels straight into the uncached framebuffer mapping: 24 ms per frame (25 FPS at 50 %). `bl2` converts into a 180-pixel stack buffer and lets `memcpy()` write it: 48-51 FPS at 50 % and 20 %, 49 at 100 %.
- Userspace side: with the connector type DSI, KWin calls the output `DSI-1` and "Built-in Screen" (the saved scale 1.6 carried over; backup of the output configuration in `~/.config/kwinoutputconfig.json.before-dsi`). Plasma still used KWin's own dimming until `polkit` was installed (`apk add polkit polkit-elogind`, `rc-update add polkit default`): powerdevil's backlight helper is a KAuth helper and every call had been failing with "Did not receive a reply". After that `org.kde.ScreenBrightness` 50 % gives sysfs 128 and a framebuffer exactly half as bright (mean green 130 -> 65), i.e. only one of the two mechanisms is active.
- Pixels at 100 % verified against a screenshot through `/dev/mem` (0.1 of 255). No oops in dmesg.
- The scaling is linear in pixel value, so 50 % on the slider is darker than a real backlight at 50 %.
- With polkit present the other powerdevil helpers (charge threshold and so on) can now be reached as well; not looked at.

## Angelfish start-up regression bisected (2026-10-10 midday, image `bl5` in BOOT)

- Trigger: the same `prof3.sh` measurement (kill, start `angelfish about:blank`, time stamps on its log) gave 7.06 s to the first "WebView completed" on `bl2`, against 5.38 s in the night. Three runs per image from here on; the first run after a boot is always slower and is ignored.
- Raw speed is the same everywhere (`performance` governor: 800k-iteration Python loop 1045/1059 ms, 64 MiB touch 36 ms, 200 fork+exec 240/249 ms, 20 Python starts 1563/1576 ms on `susp2` and `cpuidle1`), and it scales linearly with the frequency limit, so this is not the CPU.
- Results (time to "Migrations finished" / first view): `pfshrink4` 1.6 / 6.4-6.9 (two runs); `cpuidle1` 1.4 / 6.0; `susp2` 2.0 / 7.1; `bl2` 2.0-2.1 / 7.0-7.1; `bl3` (`CONFIG_PM_ADVANCED_DEBUG` removed) 2.0 / 6.8-7.0; current kernel + `cpuidle.dts` 1.4 / 5.9; + `keep-power-in-suspend` only 1.45 / 6.0-6.2; + wake-up keys only 1.4-1.5 / 6.0-6.3; + both (`suspend.dts`) 2.1 / 7.1-7.3; `bl4` (power key only) 2.2-2.3 / 7.3; `bl5` (no wake-up keys, full display layer) 1.8 / 6.6-6.7; the same without the backlight property 1.9 / 6.7-6.8.
- So: (1) `keep-power-in-suspend` together with a `wakeup-source` key costs about 1.1 s; either alone is free. Not understood. `suspend.dts` no longer marks any key as a wake-up source. (2) The `memory-region` framebuffer path costs about 0.7 s compared with the slow path; the backlight/DSI part is innocent. Not understood either; kept, because it is what gives 49 instead of 38 FPS.
- `CONFIG_PM_ADVANCED_DEBUG` was not the cause but is off again anyway (config pin updated).
- Other failed guesses, for the record: Wi-Fi power save (on in both), polkit, the freezer daemon, WebEngine flags, `QT_VULKAN_LIB` (the "Failed to create Vulkan instance" line costs nothing measurable), CPU frequency floor (1586 MHz floor: 7.05 -> 6.8 s).
- The 5.4 s of the night was never reproduced today, even on the old image; treat it as an outlier.
- Temporary images `tdt1`-`tdt6` are bisect builds only.

## Angelfish start-up: where the main thread's time goes (2026-10-10 midday, `bl5`)

- `perf record -a` over the first 7.5 s of a start: main thread 3.7 s of CPU (6.2 % of eight cores), WebEngine processes 2.0 s, QSGRenderThread 1.1 s, QQmlThread 0.9 s, KWin 0.7 s; 83 % idle. Main thread by library: musl's `ld-musl` 0.9 s (dynamic linking and malloc), Qt Qml 0.7 s, Qt Core 0.7 s, kernel 0.5 s.
- `LD_PRELOAD=/usr/lib/libmimalloc.so.2` (package mimalloc2, installed, NOT enabled anywhere): 6.85-6.99 s -> 6.46-6.56 s to the first view, at the price of about 50 MB more resident memory (301-324 -> 349-373 MB). Not adopted: too little for the memory it costs on this phone.
- The ad blocker initialises on its own thread (`std::async`), so switching it off would not shorten the start.
- Conclusion: no cheap lever left in start-up; what helps is not closing applications (the freezer keeps them cheap).

## Copy variant rejected; frequency floor while the screen is on (2026-10-10 afternoon, BOOT `bl7` = `bl5`)

- Tried the fast XRGB->ARGB copy with a stack buffer and `memcpy()` (as in the dimmed path) instead of direct 64-bit stores (image `bl6`): slower, 47.0 against 49.5 FPS at the 546 MHz floor and 53.4 against 54.2 at 1144 MHz. Reverted; tree and both patch files regenerated from the scratch copies, image `bl7` has the same SHA-256 as `bl5`.
- Host note: `/tmp` reached 80 % and the U-Boot step of the image build failed again; `rm -rf /tmp/j701f-uboot-embedded-source/out-uboot-j701f-*` (run through `bash -c`, the interactive shell does not expand that glob when nothing matches).
- `system/inputboost`: the frequency floor is now 902 MHz while any DRM connector reports DPMS "On" (polled every 3 s through `/sys/class/drm/card*-*/dpms`) and 546 MHz when the screen is off; touch still raises it to 1144 MHz for 3 s. Verified: screen on 902000, touch 1144000, after 902000, DPMS off 546000.

## Angelfish start-up: render loop (2026-10-10 afternoon, userspace only)

- With the 902 MHz screen-on floor the default start is 6.0-6.5 s (three plus two runs). Hidden behind the lock screen (`loginctl lock-sessions`): 5.7-6.0 s. `QSG_RENDER_LOOP=basic`: 5.49, 5.50, 5.56 s.
- Scroll benchmark (scratch copy of `bench/scroll`): 52.7 callbacks/s default, 52.3 with `basic`; median 16.7 ms both, longest interval 33.4 against 50 ms (one run each).
- Applied to Angelfish only: `~/.local/share/applications/org.kde.angelfish.desktop` with `Exec=env QSG_RENDER_LOOP=basic angelfish %u`; `kbuildsycoca6` run; launching through `gtk-launch org.kde.angelfish` shows the variable in the process environment.

## Render loop on other applications: no gain (2026-10-10 afternoon)

- Time until the process goes quiet after launch, default against `QSG_RENDER_LOOP=basic`, two runs each: plasma-settings 4.3-5.0 s against 4.3 s; kalk 6.8-7.0 s against 6.5 s; kclock never goes quiet (it animates). Not worth a session-wide setting, which would also change the home screen; the override stays on Angelfish only.
- kalk start profile: 3.9 s of main-thread CPU in 7 s, spread over Qt Qml, Qt Core, musl, libxml2 and libqalculate; no single symbol above 0.2 % of the samples. Nothing cheap to fix.

## Native display trial candidate refreshed (2026-10-10 afternoon, NOT flashed)

- Codex's trial tree was based on `charger.dts`. Rebased copies, content otherwise unchanged: `kernel/dts/exynos7870-j7velte-display-prepared2.dts` (base `suspend.dts`) and `kernel/dts/exynos7870-j7velte-display-trial2.dts`. The `fbmem` layer is deliberately not underneath: the trial disables the simple-framebuffer node, so the software backlight and fast copy do not apply to it.
- `tools/build-mainline-image.sh displaytrial3 kernel/dts/exynos7870-j7velte-display-trial2.dts "--allow-audio --allow-sd --allow-mfc"`: built, QEMU entry reached, unit tests OK. `tools/validate-display-trial.py --dtb build/kernel/j701f-displaytrial3/exynos7870-j7velte-diagnostic.dtb --handoff-dir build/kernel/handoff-displaytrial3`: "PASS: 24 native-display software checks". Panel and probe modules rebuilt against the current kernel with `tools/build-display-prototype.py --worker claude`.
- Nothing was written to the phone. The trial still needs the owner watching the screen and Codex's procedure in `docs/j701f-display.md` ("First takeover route"): no graphical session, root-only DSIM timing parameter, manual panel load with `allow_init=1`. Without a native brightness implementation the trial image has no brightness control at all.

## First user feedback and the fixes for it (2026-10-10 afternoon, userspace only, BOOT `bl7`)

The user tried the phone: YouTube in Angelfish plays with picture and sound, the brightness slider works (a little late), scrolling Wikipedia is "much better than before, not extremely smooth, but it was not on Android either". Missing: rotation, Plasma not seeing Wi-Fi, Elisa not playing the test track, Discover listing every package.

- **Rotation.** `iio:device0` is `lis2hh12`. Installed `iio-sensor-proxy` and `qt6-qtsensors`, service in the default runlevel; needed `udevadm control --reload; udevadm trigger -s iio` before the proxy stopped exiting with "No sensors". `net.hadess.SensorProxy` then reports the accelerometer (and the proximity sensor: `ProximityNear false`). `autoRotation` in `~/.config/kwinoutputconfig.json` changed from `InTabletMode` to `Always` with the session stopped; after the reboot `autoRotatePolicy` is 2 and KWin logs orientation readings. Direction not verified (no mount matrix; flat on the table the raw z value is about -16500).
- **Wi-Fi in Plasma.** `system/wifi` (`/sbin/j701f-wifi`, previous version kept as `/sbin/j701f-wifi.before-nm`) starts NetworkManager on mainline when `/etc/j701f-wifi-nm` exists, with a 90 s fallback to the original wpa_supplicant path; 3.18 is unchanged. Packages `networkmanager-wifi`, `networkmanager-cli`. The NM profile was generated on the phone from `/etc/wpa_supplicant/wlan0.conf` (hex SSID decoded, PSK copied without being printed). `/etc/NetworkManager/conf.d/j701f.conf`: no MAC randomisation while scanning, permanent MAC for connections. Switched live and across a reboot: same address 192.168.1.158, `nmcli` shows wlan0 connected.
- **Elisa.** The track I had downloaded was FLAC in an Ogg container, 22.05 kHz, no tags. libVLC decodes it (checked with `--aout adummy`, no sound), so the empty title was the missing tags. Replaced by a tagged `.flac` (original moved to `~/.local/share/j701f-replaced/`); Elisa's database now has title, artist and album. Playback itself not tested by me (no sound tests).
- **Brightness lag.** Measured from the D-Bus call to the backlight file: first change after about 95 ms (360 ms for the first call after a pause, when the KAuth helper has to start), settled after 200-230 ms in 3-4 steps. The kernel side is immediate; the time is powerdevil's helper round trips. Left as it is.
- **Discover** uses the Alpine apk backend, which lists all packages. Not changed.

## Roadmap 0.1 (rotation) and a dimming regression fixed (2026-10-10, images `bl8`, `bl9`)

- Rotation still did not work for the owner. Cause found: iio-sensor-proxy used the accelerometer's buffer with the `lis2hh12-trigger` data-ready interrupt, and that edge interrupt stops (349 interrupts, then nothing), so the readings froze. `system/accel-udev.rules` -> `/etc/udev/rules.d/81-j701f-accel.rules` sets `IIO_SENSOR_PROXY_TYPE=iio-poll-accel`; the proxy now logs fresh "Accel read" values twice a second. The Plasma Mobile "Auto-rotate" tile (`org.kde.plasma.quicksetting.screenrotation`) is installed and enabled in `plasmamobilerc`; it shows only when the sensor is available at shell start, hence a reboot. KWin reports `tabletModeAvailable` and `autoRotatePolicy` 2. Rotating by command (`kscreen-doctor output.DSI-1.rotation.left`) works: geometry 800x450. Physical turning still to be confirmed by the owner.
- While measuring: at the owner's brightness (89 %, backlight 228) es2gears started at about 50 FPS and settled at 31.8 after a few seconds; at 100 % it held 54. The table-lookup dimming loop cost about 10 ms a frame, enough to push KWin onto every second refresh.
  - `bl8`: dimming as two 64-bit multiplications per pixel pair, stored as whole words (arithmetic checked on the host for all 256 levels, at most 1.43/255 off exact scaling): steady 41.4 FPS dimmed, 53.5 plain.
  - `bl9`: `kernel/patches/linux-zzz-sysfb-j701f-neon-copy.patch` adds `drm_sysfb_j701f_neon.c` (built with `CC_FLAGS_FPU`), used inside `scoped_ksimd()` 32 lines at a time for both the plain and the dimmed copy: 50.4-51.3 FPS at backlight 228/128/52, 55.1-55.7 at 255. Pixels at 100 % verified through `/dev/mem` (0.1 of 255).
- Brightness restored to the owner's 89 % afterwards.

## Roadmap 0.2: an application store (2026-10-10, userspace only)

- Discover's `alpineapk-backend` exposes a single category ("Alpine Linux packages"), so it cannot show applications only; with the AppStream catalogue present its home page even reports "Unable to load applications". Left installed, unchanged.
- Installed `alpine-appstream-downloader` (catalogue in `/var/lib/swcatalog`, 830 components; its directories came out mode 700 under sudo and had to be made world-readable), `gnome-software`, `gnome-software-plugin-apk2`; service `apk-polkit-server` added to the default runlevel.
- GNOME Software 50.3 shows the catalogue (carousel, "Editor's Choice", icons). With GTK's default renderer Mesa logs "Failed to choose spill node" and parts of the window are black (`build/screenshots/gnome-software.png`); with `GSK_RENDERER=cairo` it is correct (`gnome-software-cairo.png`). Set session-wide through `system/session/gtk-env.sh` and in a launcher override.
- `system/tune` refreshes the catalogue in the background when it is older than a week.
- Not tested: installing an application through it (would change the system; left to the owner).

## Roadmap stage R started: recovery design and UI skeleton (2026-10-10, computer only)

- `docs/recovery-design.md`: what the two slots hold today (RECOVERY is the vendor kernel booting the same root filesystem, not a recovery), the target (frozen mainline kernel + self-contained initramfs + one static LVGL program on the simpledrm framebuffer, USB shell and SSH always on), the screens mapped to roadmap items R.1-R.7, the write allow-list (BOOT, RECOVERY, files), and the five-step path that keeps today's fallback until the new recovery has proved it can write BOOT. Three questions for the owner at the end.
- `recovery/ui/` (`main.c`, `lv_conf.h`, `Makefile`): home screen with the seven tiles; the computer build renders into memory and writes a PPM (`recovery-ui --snapshot`), the phone build (`make TARGET=phone`, not built yet) uses `/dev/fb0` and evdev. Snapshot: `build/screenshots/recovery-home.png`.
- LVGL 9.2.2 fetched by shallow git clone (a GitHub tarball download kept truncating on this network); provenance in `docs/third-party.md`.
- Nothing was run on or written to the phone for this.

## Recovery UI: pages and the Kernel page (2026-10-10, computer only)

- `recovery/scripts/sysinfo.sh`: read-only summary as `label|value` lines (running kernel, BOOT slot and the first 16 hex digits of its SHA-256, installed image name if recorded, battery, memory, root filesystem, pstore). Every probe is optional so it also runs on the computer.
- `recovery/ui/main.c`: generic page with a back button; the Kernel tile opens a page filled from that script. `recovery-ui --snapshot FILE.ppm kernel` renders it (`build/screenshots/recovery-kernel.png`).
- Not on the phone yet: Codex held the phone for the first native display trial.

## Recovery UI: Power page (2026-10-10, computer only)

- `recovery/scripts/power.sh system|recovery|download|off`, with `J701F_RECOVERY_DRYRUN=1` printing instead of acting; checked in dry-run for all four actions and a wrong argument (exit 2). `recovery` needs the project's `reboot-recovery` helper and says so when it is missing.
- UI: Power page with four buttons, each behind a Yes/Cancel box; the result line shows the script's output. Snapshot `build/screenshots/recovery-power.png`.
- Still only on the computer. Next: native build on the phone and a run on the real screen with dry-run forced, once Codex's display trial has released the phone.

## Recovery UI: Terminal page (2026-10-10, computer only)

- Shell on a pseudo-terminal (`forkpty`, `TERM=dumb`), output shown as plain text with escape sequences dropped (last 6000 characters kept), input typed on LVGL's on-screen keyboard and sent a line at a time. The page's delete event closes the pty and hangs up the shell.
- Test hook `recovery-ui --snapshot FILE.ppm terminal` types a command through the page's own input path; the snapshot shows `recovery-terminal-ok` and `Linux` (`build/screenshots/recovery-terminal.png`).
- Known rough edges: the tty echoes the command a second time, the font is proportional, no cursor keys or Ctrl combinations yet.

## Recovery: BOOT writer with rollback, tested on files (2026-10-10, computer only)

- `recovery/scripts/flash-boot.sh info | write IMAGE [SHA256] | rollback`. The target is found by partition name BOOT (65536 sectors, non-removable mmcblk0); nothing else can be written. Checks before writing: Android boot header, size, optional SHA-256. It keeps an exact copy of the slot first, writes, reads back; if the read-back differs it writes the kept copy back and fails. `rollback` writes the kept copy and verifies the whole slot.
- `tests/test_recovery_flash.py`: eight tests on temporary files (successful write keeps the previous contents and records the hash; rollback restores byte for byte; wrong header, too large, too small, missing file and wrong hash are refused with the slot untouched; unknown sub-command exits 2). All pass. Never run against a device.
- Not wired into the UI yet.

## Recovery UI: Files page, browse only (2026-10-10, computer only)

- LVGL's file explorer on its POSIX driver (`lv_conf.h`: `LV_USE_FS_POSIX`, letter A mapped to `/`, `LV_USE_FILE_EXPLORER`). Tapping a file stores and shows its path; view, copy and "flash this image" are not there yet. `J701F_RECOVERY_FILES` sets the start directory for tests. Snapshot `build/screenshots/recovery-files.png`.

## Recovery: backup script, tested on directories (2026-10-10, computer only)

- `recovery/scripts/backup.sh create ROOT DEST [PATH...] | verify ARCHIVE | restore ARCHIVE EMPTY_DIR`: tar.gz of paths relative to the mounted root (default `etc`, the user's `.config` and `.local/share`) plus a `.sha256` file; `restore` checks the hash and refuses any target directory that is not empty, so it cannot overwrite an installed system.
- `tests/test_recovery_backup.py`: four tests (round trip with an unselected file staying out, non-empty target refused, damaged archive detected by verify and restore, absolute or `..` paths and unknown sub-commands refused). Twelve recovery tests pass together with the flash tests.
- Not wired into the UI yet.

## Recovery UI: flashing wired to the Kernel page (2026-10-10, computer only)

- The Kernel page has "Flash the selected image" (the file chosen on the Files page) and "Roll back to the previous image", each behind a Yes/Cancel box; both go through `flash-boot.sh` and show its last line. Helper scripts are found through `J701F_RECOVERY_SCRIPTS` (default `../scripts`).
- Test hook `--snapshot FILE.ppm flash:IMAGE` drives the same code path. With `J701F_RECOVERY_TARGET` pointing at a 1 MiB random file the page reported "WRITTEN AND VERIFIED", the file then began with the new image, and `boot-previous.img` and `boot-slot.txt` appeared in the state directory (`build/screenshots/recovery-flash.png`).
- Still never run against a block device.

## Recovery UI on the phone's own screen (2026-10-10, no slot written)

- Native static build on the phone (`make TARGET=phone`, 1.36 MB static-pie) in `~/j701f-recovery-build/`.
- Test run as an ordinary program with the desktop stopped for about a minute, three times. Stopping the session needs what Codex found: `rc-service sddm stop` reports "already stopped" while SDDM lives on, so stop its `supervise-daemon` and then write `1` to `cgroup.kill` of KWin's session scope (`/c1`, `/c2`, ... - the number changes). Afterwards `rc-service sddm zap; rc-service sddm start` brings the desktop back (it prints "failed to start" yet starts); a dead-man reboots if plasmashell is not back after 170 s. Desktop returned every time.
- Evidence is the framebuffer memory read through `/dev/mem` (`build/screenshots/recovery-on-phone.png`, `recovery-on-phone-2.png`): home screen with "running on Linux 7.1.13-BURAK-PANFROST-01", the Power page, the Terminal page with a shell prompt, the Files page listing the phone's root directory, and the back button working. All actions were in dry-run (`J701F_RECOVERY_DRYRUN=1`, a non-existent test target).
- Problems seen: (1) the first injected tap after start did nothing in all three runs, so the Kernel page was never opened on the phone; (2) taps of about 36 ms are sometimes missed (LVGL polls the touch device), 150 ms taps work; (3) the software backlight stays at whatever level the desktop left (it looked very dim until set to 255).
- `sysinfo.sh` fixed to resolve the by-partlabel symlink before reading the partition size.

## Recovery mode of the initramfs prepared (2026-10-10, computer only; not built into an image yet)

- `kernel/diagnostic/recovery-main` (new) and four lines in `kernel/diagnostic/init`: when the initramfs contains `/bin/recovery-ui`, `/init` runs `recovery_main` before the normal hand-over. That function cancels the 90 s timed reboot, creates the BusyBox applet links the recovery scripts need, keeps the USB serial shell running next to the UI, restarts the UI if it exits, and returns (so that the hand-over to Alpine runs) when `/run/boot-system` appears. For trials it boots the system by itself after 240 s if nobody touched the screen or opened the USB shell and `/run/stay-recovery` does not exist.
- UI: the "Boot system" tile creates that flag and exits (dry run: only says so); any tile press marks the recovery as in use.
- `tools/build-mainline-initramfs.py`: extra `recovery-main` and `--recovery-scripts DIR` (installs `*.sh` under `/recovery/scripts/`). `tools/build-mainline-image.sh`: `J701F_RECOVERY_UI=path` builds the recovery variant.
- All 191 host tests pass. Waiting for the phone (Codex is on a DSIM PLL test) to rebuild the UI binary natively and fetch it.

## Owner feedback round two: one folder on the phone, store speed, recovery keyboard (2026-10-10)

- **One folder.** The owner wants project files under a single folder in his home directory and allowed deleting the old staged images. On the phone: 64 `~/j701f-boot-update-*` directories removed (root filesystem 4.9 -> 4.4 GB used); `~/j701f-boot-swap` -> `~/j701f/boot-swap`, module directories -> `~/j701f/modules/{audio,mfc,misc}`, `~/j701f-cpuidle` -> `~/j701f/experiments/cpuidle`, `~/j701f-recovery-build` -> `~/j701f/recovery-build`, early-stage leftovers -> `~/j701f/old/`. Paths changed in `tools/run-boot-update.sh`, `tools/prepare-boot-update.py` (the `--phone-dir` prefix check), `tools/build-mainline-image.sh`, `system/audio-autoload`, `system/audio-load`, `system/mfc-load`, `system/netguard`, and in the `load.sh` and boot-swap scripts on the phone. Verified after a reboot: 12 modules loaded, sound card, `/dev/video0`, charger. Boot-update directories prepared before this have to be prepared again.
- **Software store "very laggy".** It ran on GTK's Cairo software renderer. GTK 4.22's GL renderer shows black areas by default, but with `GSK_GPU_DISABLE=all` it drew correctly in two runs including after scrolling (`build/screenshots/gnome-software-gl-all.png`); single flags (occlusion, clear, blit, to-image, merge, mipmap) did not fix it, and my black-pixel metric was unreliable there because of dark banner pictures. `system/session/gtk-env.sh` and the launcher override now set `GSK_RENDERER=gl GSK_GPU_DISABLE=all`. Whether it feels smooth enough is the owner's call.
- **Recovery keyboard.** Keys were small islands with wide gaps; padding and gaps set to 6 px, dark key colours, readable control keys, dark input field (`build/screenshots/recovery-terminal.png`).
- Recovery UI rebuilt natively with these changes; the static binary is in `build/recovery-ui/phone/recovery-ui` (SHA-256 4ca3c0639f0398c6...).

## First boot of the recovery image, in BOOT as a trial (2026-10-10, image `rec1`; BOOT restored to `dsimdiag2`)

- `rec1` = shared kernel Image + `fbmem` DTB + initramfs with `/bin/recovery-ui` (native static build), `/recovery/scripts/` and the recovery mode of `/init` (`J701F_RECOVERY_UI=... tools/build-mainline-image.sh rec1 ...`, 14.9 MB). Written to BOOT through the usual 3.18 flow; RECOVERY untouched.
- Result over the USB serial shell: initramfs at 28 s, recovery mode active, UI process running, scripts present, `sysinfo.sh` reporting the BOOT slot and its hash. Screen contents fetched as gzip+base64 over the serial line (`build/screenshots/recovery-booted.png`).
- Two defects found and fixed in `kernel/diagnostic/recovery-main` (the fixes are not in `rec1` itself): the screen showed the boot diagnostics text instead of the UI because fbcon kept drawing over the UI's first frame (now the framebuffer console is unbound first; done by hand in the trial, after which the home screen was there); `sed`, `awk`, `pidof` were missing because only some applet links existed (now `busybox --install -s /bin`).
- Hand-over: 240 s without interaction -> "J701F_RECOVERY_AUTOBOOT", "J701F_RECOVERY_BOOTING_SYSTEM", Alpine came up with desktop, Wi-Fi and all 12 modules.
- Restoring BOOT: the USB shell of the running Alpine did not answer, so `run-boot-update.sh` waited in vain for 3.18; `reboot-recovery --execute` over SSH got it going. `dsimdiag2` written back and verified.
- Not exercised in the trial: touch on the booted recovery (nobody at the phone), flashing, backup.

## Owner decisions for the recovery, and the rotation direction (2026-10-10)

- Decisions: the new recovery will replace the vendor 3.18 fallback in RECOVERY once proven (the vendor image stays available as a file); it should be able to use Wi-Fi; UI in English and Turkish, English by default.
- Rotation: "it turns, but after the first turn it is always the opposite of normal; upright is upside down". The DT mount matrix `0, 1, 0; -1, 0, 0; 0, 0, -1` has determinant -1, i.e. it is a mirror; Z is right, so one in-plane axis must be wrong. `system/accel-udev.rules` now sets `ACCEL_MOUNT_MATRIX=0, 1, 0; 1, 0, 0; 0, 0, -1` for iio-sensor-proxy. Waiting for the owner to confirm; if landscape is now the wrong way round, the first row is the one to flip instead. The device tree itself still carries the old matrix.

## Recovery UI: two languages, own touch reader, Backup / Maintenance / file actions (2026-10-10, computer only)

Done while Codex had the phone; nothing of this has run on the phone yet.

- **Languages.** English and Turkish, English first; a button on the home screen switches. The choice is stored in the recovery's state directory (RAM), so it lasts until a reboot; `J701F_RECOVERY_LANG=tr` sets the starting language. LVGL's built-in Montserrat fonts have no Turkish letters: `recovery/ui/gen-tr-font.py` renders the twelve missing ones (Ç Ö Ü ç ö ü Ğ ğ İ ı Ş ş) at 20, 28 and 40 px from the very Montserrat-Medium.ttf that LVGL ships (SIL OFL) into `font_tr.c` in LVGL's font format, each font falling back to the built-in one of the same size. The generated file is committed so that the build on the phone needs no Python.
- **First tap lost.** Cause found by reading LVGL's `lv_evdev.c`: it drains the event queue and reports only the final state, so a press and release that arrive between two reads are never seen. `main.c` now reads the touchscreen itself (`touch_read`), stops at every change of state and asks LVGL to call again; the main loop sleeps at most 20 ms instead of 50.
- **Backup and Maintenance pages** run `recovery/scripts/storage.sh` (new): `mount-root` mounts the installed system `ro,noload` at `/mnt/root` (no journal replay, so not one block changes), `mount-sd`, `backup` (-> `SD/j701f-backups`), `verify`, `copy FILE` (-> `SD/j701f-files`, never overwrites), `check` (`e2fsck -n`), `log`. `e2fsck` is not in the initramfs yet, so `check` refuses for now.
- **Files page:** mounts the system read-only when opened, "View" shows the first 2.5 kB of a file as text, "Copy to SD card" asks first.
- **Hand-over:** `recovery-main` unmounts `/mnt/root` and `/mnt/sd` before returning to `/init`; if that fails it reboots rather than letting `/init` mount the same filesystem a second time (which would share the read-only superblock).
- Tests: 17 in `tests/test_recovery_backup.py` + `tests/test_recovery_flash.py` (five new for `storage.sh`, one of them proving the check leaves an image byte-identical). Wiki: new page `reference/recovery(.tr).md`.

## Second recovery trial in BOOT: `rec2` (2026-10-10; BOOT restored to exact `dsimpll2` by the recovery itself)

- **Before the boot**, on the running system: new UI built natively on the phone and run on the real screen with injected taps (desktop stopped and restarted). The very first tap, a 20 ms one, switched the language to Turkish; Maintenance, Wi-Fi status and the kernel log page drew correctly (`build/screenshots/rui-phone2.png`).
- **Image `rec2`** (15.8 MB): as `rec1` plus the fixes, `e2fsck` with its libraries and the musl loader copied from the phone's Alpine into `/recovery/lib` (new builder option `--recovery-tools`, a `/bin/e2fsck` wrapper starts it through the loader), `wifi.sh`, `storage.sh`. Written to BOOT through 3.18 (which had DHCP address .85 this time: the scan in `run-boot-update.sh` now covers .20-.230).
- **On the phone:** the UI was on the panel by itself (no console text over it) and the owner used it by touch.
- **Wi-Fi and SSH** (`recovery/scripts/wifi.sh`): the driver and firmware are in the recovery; `wpa_supplicant`, `udhcpc`, `sshd`, the saved network and the host keys are used from the installed system mounted `ro,noload`, with RAM filesystems over its `/run` and `/tmp`. First attempt failed ("not associated after 40 s"): association was fine, but `wpa_cli` could not create its reply socket in the read-only `/tmp`. With the `/tmp` RAM filesystem: address .158, SSH login with the usual key, `sudo` works, root filesystem read-only as intended.
- **Filesystem check:** `e2fsck -n -f` on USERDATA ran in 2.7 s; only the free-block/inode counters differ, which is what a filesystem whose journal was not replayed shows. Nothing written.
- **Backup:** the SD card is `mmcblk2` on the mainline kernel (`storage.sh` looked for `mmcblk1`; it now takes whichever MMC device reports type SD). `/etc`, `.config`, `.local/share` -> 28 MB archive on the card in 17 s, verified (1330 entries). The archive stays on the owner's card in `j701f-backups/`.
- **Writing BOOT from the recovery (roadmap R.4):** `flash-boot.sh write` first refused silently: `/run` is 8 MiB and the copy of the current 32 MiB slot did not fit; nothing had been written. Now the state directory is its own 48 MiB RAM filesystem and the script says why it stops. Second attempt: "WRITTEN AND VERIFIED", BOOT SHA-256 `a2b11f5a...` = Codex's full `dsimpll2` partition image, previous contents kept for rollback. **First kernel write on this phone that did not go through the vendor 3.18 system.**
- **Hand-over:** `/run/boot-system` -> Wi-Fi down, both mounts released, Alpine up with a read-write root, desktop and all modules. Then one reboot onto `dsimpll2`; healthy.
- Not done: rollback from the menu, the Power page's actions, hardware keys, flashing through the touch UI (done through the same script over the USB shell). RECOVERY still holds the vendor fallback.

## Rotation, second correction (2026-10-10)

Owner's report with the matrix `0, 1, 0; 1, 0, 0; 0, 0, -1`: upright and upside-down are right, both landscape directions are reversed. So the second row was the right one to flip for portrait and the first row has to be flipped as well: `system/accel-udev.rules` now sets `0, -1, 0; 1, 0, 0; 0, 0, -1` (a proper rotation, determinant +1... times the Z flip of a face-up sensor). Installed on the phone; waiting for his confirmation before the device tree is changed to match.

## Third recovery trial in BOOT: `rec3` (2026-10-10; BOOT again exact `dsimpll2`, written by the recovery)

- `rec3` = `rec2` plus the fixes found in trial 2 (state area as its own RAM filesystem, `/tmp` for `wpa_cli`, SD detection by type) and the recovery's scripts and state bound into the SSH login (`/run/recovery/scripts`, `/run/recovery-state`). 3.18 had DHCP address .82 this time.
- Wi-Fi and SSH were up by themselves 15 s after the first probe; everything below was done over SSH without the cable.
- `flash-boot.sh write` (full `dsimpll2` image, expected SHA given) -> verified; `rollback` -> BOOT back at the `rec3` hash `7ad9c58f...`, verified; a second `write` was refused: the kept copy plus the new copy need 64 MiB and the area had 48. Enlarged to 80 MiB (in the source too), then written and verified: BOOT = `a2b11f5a...`.
- Hardware keys: volume-down twice and power, injected into `gpio-keys`, opened the Kernel page (`build/screenshots/rui-keys.png`); the key press also set the "somebody is here" marker, so the automatic boot did not fire.
- Found: an SSH login cannot create `/run/stay-recovery` (its `/run` is a separate RAM filesystem); `/run/recovery-state/stay` is now accepted as well.
- `power.sh system`: now takes Wi-Fi down and releases the mounts first and forces the reboot in the initramfs (there is no init system to ask). Run on the phone: rebooted into `dsimpll2`, desktop up, 15 modules.
- Still not exercised: flashing and rollback by tapping the buttons, the copy button, reboot to recovery / download mode and power off. RECOVERY untouched.
- **Blocking the RECOVERY install:** every existing update flow (mine and Codex's) reboots into 3.18 in RECOVERY and its guards check for exactly that image. A recovery-based update tool has to exist and be agreed with Codex first.

## Update tool for the future layout (2026-10-10, written, not run)

`tools/run-recovery-update.sh NAME`: stages `boot-mainline.img` on the running system, reboots into the recovery, logs in over Wi-Fi, lets `flash-boot.sh write IMAGE SHA` do the write (hash check, previous contents kept, read-back), asks for a clean reboot through `/run/recovery-state/reboot` (new hook in `recovery-main`), waits for the system and compares the BOOT hash. Each step was done by hand in trial 3; the script as a whole can only run once the recovery is in RECOVERY. Codex has been asked what his flows still need from the 3.18 side before that install.

## The graphical recovery is installed in RECOVERY (2026-10-10, owner's order; image `rec4`)

Owner, with Codex away for a long time: "install the recovery".

- **Kept first:** the whole 38 MiB RECOVERY slot as it was (vendor 3.18 fallback), SHA-256 `364f6834...`, on the phone (`~/j701f/recovery-install/recovery-slot-before.img`) and on the computer (`build/backups/recovery-slot-3.18-before-rec4.img`); its first 32 MiB are the known fallback image `0575c658...`.
- **Written** from the running system with guards (partition name, size, image hash, Android header) and read-back: `rec4` (`rec3` plus the 80 MiB state area, the SSH stay/reboot markers, the cleaner `power.sh`), image `424a5980...`, slot afterwards `5cda23bd...`. Record: `build/kernel/recovery-slot.json`.
- **Proved by `tools/run-recovery-update.sh dsimpll2`, its first complete run:** image staged, `reboot-recovery`, the recovery booted **from the RECOVERY slot**, Wi-Fi and SSH came up by themselves, `flash-boot.sh` wrote and verified BOOT (the same payload as before, so the slot is still exactly `a2b11f5a...`), clean reboot on request, system up with desktop and modules.
- **Consequences:** `tools/run-boot-update.sh` and every flow that reboots into 3.18 (Codex's included) no longer work; the old script now stops with a pointer. `tools/restore-vendor-recovery.sh` writes the kept slot back (written, not run). The phone-side `restore-3.18-to-boot.sh` files still refer to a state that no longer exists.
- Still the recovery's own safety net: 240 s without touch, key or the stay marker -> it boots the system.
- Not exercised yet: flashing/rollback/copy by tapping, reboot-to-recovery from inside the recovery, download mode, power off; the recovery with a damaged or unreadable installed system (then: no Wi-Fi, USB shell only).

## Video decoder, other formats (2026-10-10, started, parked for the install)

Silent decode-to-null tests of 8 s 720p samples made on the computer (`~/j701f/video-test/`): H.264 clean and bit-identical to software decoding over 60 frames. HEVC and MPEG-2: every frame comes back flagged as an error; the driver's debug output shows status `0xbe` = 190, "sync point not received", which the vendor driver treats as a warning - but the frames are also **not** identical to software decoding, so it is not only a flag. MPEG-4: firmware error 102 (header not found). VP8: error 34. Causes not found yet.

## Recovery `rec5`: the read-only mount really writes nothing now (2026-10-10, installed in RECOVERY)

- **Found in the kernel log of the installed recovery (pstore):** `EXT4-fs (mmcblk0p24): orphan cleanup on readonly fs` / `1 orphan inode deleted`. A mount with `ro,noload` skips the journal but ext4 still cleans up orphaned inodes when the block device is writable - so the "not one block changes" claim was wrong after an unclean reboot of the system (`reboot-recovery` does not unmount).
- **Fix:** `storage.sh` switches the USERDATA partition itself to read-only (`blockdev --setro`) before mounting; `recovery-main` switches it back (`--setrw`) after unmounting and before the hand-over. On `rec5`: `blockdev --getro` = 1 in the recovery, only the "mounted ... ro without journal" line in the log, hand-over to a read-write system works, `getro` = 0 there.
- `tools/install-recovery.sh NAME` (new): writes a recovery image into RECOVERY from the running system with the same guards as the first install, keeps the previous slot contents on the phone (`recovery-previous.img`) and updates `build/kernel/recovery-slot.json`. Used for `rec5` (slot `55d00eb1...`).
- Button tests by injected taps were started and abandoned: the screen dumps lagged behind the taps, and in one session the recovery ran "Reboot into recovery" (clean unmount, `reboot: Restarting system with command 'recovery'`, came back into the recovery) without my having aimed at that button. Either one of my blind taps hit the Power page and its confirmation, or the owner was trying the buttons at that moment. Asked him. As a side effect that path is now known to work.
- The 240 s automatic boot from the installed recovery was seen working (phone found back in the system by itself).

## Video decoder: cause of the HEVC / MPEG-2 corruption found; patch written, NOT built or tested (2026-10-10)

- PSNR against software decoding: MPEG-2 is garbage (5 dB) for the first 11 frames and fine (75 dB) from the second key frame on; HEVC (one key frame in the 8 s sample) is garbage throughout. So the first key frame is lost.
- Cause: after parsing the headers, upstream `s5p_mfc.c` keeps the first source buffer for decoding only for H.264 (`head_processed`); for every other codec the buffer - which with FFmpeg holds headers and the first picture together - is dropped. The vendor driver has the check for H.264 and HEVC.
- `kernel/patches/linux-zzzz-mfc-keep-first-frame-all-codecs.patch` makes the check codec-independent. **State: the patch file exists and applies (dry run); the kernel tree is unpatched, nothing was compiled, the module on the phone is the old one.** Next: `tools/build-kernel.py panfrost`, put the new `s5p-mfc.ko` into `~/j701f/modules` on the phone, repeat the PSNR test; then MPEG-4 (error 102) and VP8 (error 34), which may be the same thing or not.
- Samples and logs: `~/j701f/video-test/` on the phone.

## Recovery `rec6`: Home key (2026-10-10, installed in RECOVERY)

Owner, having tried the installed recovery by hand: volume up/down and power work, Home does not. Cause: the board's device tree reports the Home key as `KEY_LEFTMETA` (chosen for Plasma), and the UI only knew `KEY_HOMEPAGE`. `main.c` now accepts `KEY_LEFTMETA` and `KEY_HOME` as "select" too. Rebuilt on the phone, image `rec6` installed with `tools/install-recovery.sh` (slot `e914c570...`), checked in the booted recovery by injecting volume-down twice and the Home code: the Kernel page opened (`build/screenshots/rui-homekey.png`). Returned to the system through the SSH reboot marker. The real Home key press is for the owner to confirm.

## Owner's feedback (2026-10-10, evening)

- Rotation works (roadmap 0.1 confirmed). The device tree still carries the old mount matrix; the udev rule does the work.
- YouTube in Angelfish: picture quality good. Two small defects, noted, not urgent: (1) sound drops out for a fraction of a second now and then (last letter of a sentence clipped); (2) every 30-60 s a faint line, slight tearing or a brief black flash on screen. Neither has been investigated. First guesses, unverified: audio buffer underruns in the PipeWire/ALSA path under CPU load from software video decoding in the browser; tearing from the unsynchronised framebuffer copy (no vertical sync in the current display path).
- In the recovery: volume keys and power worked, Home did not (fixed in `rec6`, see above).

## Second roadmap proposed (2026-10-10, evening)

Owner's feedback: Home key works in the recovery; GNOME Software a little better but still stutters, its password prompt lags and rejects the correct password; the test videos in VLC now give sound only; Reddit scrolls acceptably in the browser but applications start slowly; he wants the computer to reach the phone's storage over USB, a set of phone-suited test applications, and Claude to continue Codex's display work ("the display is important"; sound is not a priority). `docs/roadmap-2.md` orders this as A regressions, B display, C USB storage, D speed, E applications, F carried over. Waiting for his approval; nothing of it has been started.

## Roadmap 2 approved; A.1 VLC shows no picture - my own regression, reverted (2026-10-10)

- Owner approved `docs/roadmap-2.md` ("continue from the new roadmap, full authority").
- Reproduced with a silent run on the session's X display and a dump of the framebuffer 8 s into playback: with `avcodec-codec=h264_v4l2m2m` in `~/.config/vlc/vlcrc` (set by me that morning) VLC 3.0.23 gets one picture from the hardware decoder, logs `main decoder error: buffer deadlock prevented` and shows a black window (0 of 9501 sampled pixels non-black). Same with one decoding thread, without direct rendering and with the X11 output. With the software decoder: picture (3006 of 9501), 32 % of one core at 720p.
- So the hardware decoder itself is fine (FFmpeg decodes the same file bit-exact) but VLC 3's avcodec module does not cope with FFmpeg's V4L2 wrapper. My earlier note "VLC uses the hardware decoder" was based on the log line "codec (h264_v4l2m2m) started" and the low CPU load; nobody had looked at the picture.
- Fix: the line is commented out again (`vlcrc.claude-hw-broken` keeps the broken file for reference). mpv remains the player that uses the hardware decoder (`hwdec=v4l2m2m-copy`).

## A.2 / A.3: the store rejected the correct password (2026-10-10)

- Cause: polkit's default administrator rule is "members of group wheel, else root". The phone's user is not in `wheel`, so every "Authentication required" dialog was asking for **root's** password; the user's own, correctly typed, was bound to fail. (PAM, the setuid helper and the KDE agent were all in order.)
- Fix: `system/polkit/49-j701f.rules` -> `/etc/polkit-1/rules.d/`: (1) the user is the administrator identity, so dialogs ask for his password; (2) the package actions of both stores (`dev.Cogitri.apkPolkit2.*`, `org.kde.discover.alpineapkbackend.pkgmgmt`) are allowed without a prompt for him in a local, active session - he has password-less sudo already, and the dialog is very slow to type in.
- Checked with `pkcheck` against the running session's `plasmashell`: both actions authorised (exit 0). Installing something through the store itself is for the owner to try.
- A.3 (why typing in the password dialog is so slow) is not explained; the dialog no longer appears for the store.

## A.4: video decoder patch built and measured (2026-10-10)

- `linux-zzzz-mfc-keep-first-frame-all-codecs.patch` applied by `tools/build-kernel.py`; the module alone built with `make ... M=drivers/media/platform/samsung/s5p-mfc modules` (lands in the source tree; copied to `build/kernel/mfc-modules/s5p-mfc-firstframe.ko`, tree cleaned again). Same vermagic, so it loads on the kernel in BOOT; installed as `~/j701f/modules/mfc/s5p-mfc.ko` (old one kept as `.before-firstframe`).
- 40 frames hardware against software, PSNR, 720p samples:

| Format | Before | After |
| --- | --- | --- |
| H.264 | identical | identical |
| HEVC | garbage throughout, every frame flagged | **identical**, no flagged frame in 240 |
| MPEG-2 | first 11 frames garbage | correct from the first frame (72.7 dB minimum; MPEG-2 decoders are not bit-exact with each other) |
| VP8 | did not start (error 34) | **identical** |
| MPEG-4 part 2 | does not start (error 102) | still does not start |

- MPEG-4 from an MP4 file keeps its headers outside the stream (in the container), and FFmpeg's V4L2 wrapper does not put them in front of the first frame; the firmware therefore finds no header. Not pursued: rare format, software decoding handles it.
- The image in BOOT is unchanged; a future kernel image only matters for built-in code, and this driver is a module.

## B.1 / B.2: display work taken over; Plasma ran on the native display driver (2026-10-10)

- Taken over from Codex (owner: "you can continue Codex's work; the display is important"). His state is described in `wiki/reference/display.md` and `docs/j701f-display.md`: RAM-only trials (device-tree overlay loaded by a module, simpledrm unbound, DECON + DSIM + EA8061S panel probed), a watchdog that always resets the phone back to the unchanged BOOT, a host controller `tools/run-native-display-trial.py` with evidence checks. None of that depends on the old 3.18 fallback, so it still works with the recovery installed.
- Two changes to his tools: the controller accepted only a lock held by `codex` (now either of us); `tools/native-display-gui.py` took `WAYLAND_DISPLAY` from the compositor's own environment, where it does not exist (now completed from the owner's `plasmashell`). His 37 native-display host tests still pass.
- Run `plasma-dsimpll2-01`: stopped at that missing variable before any display change; phone returned by watchdog.
- **Run `plasma-dsimpll2-02`: Plasma started on the native driver.** KWin opened `exynos-drm` as its display device and Panfrost as renderer, its framebuffer is a 720x1280 ARGB buffer allocated on the display device (no copy into the firmware framebuffer), all seven native hardware checks passed, the DSIM PLL locked at the first attempt. `es2gears_wayland` in the maximised 450x800 window, same clock policy: **54.4-55.8 frames per second on the copied framebuffer, 59.5-59.8 on the native driver** (the panel's 59.64 Hz, i.e. limited by vertical sync). KWin's own screenshot of the native session is a normal home screen (`build/screenshots/plasma-native-first.png`). What the panel physically showed was not seen by anybody. The phone was reset by the watchdog and came back on the unchanged BOOT with simpledrm.
- The controller still ends with "Plasma measurement incomplete": one of its own completeness checks (renderer string of the test program was "unknown") - the measurement itself is in `plasma-native*.{json,log}`.
- Missing before this can be the daily path: brightness (the native session has no backlight device at all; the software backlight belongs to simpledrm), blanking, and a way to start it at boot with a way back.

## B.3 / B.4: panel brightness and screen off/on on the native driver (2026-10-10, trials only)

- **Brightness.** `tools/kmod/ea8061s/panel-j701f-ea8061s.c` now registers a backlight device `j701f-panel` (the name the software backlight had). Level 1..255 is mapped linearly onto the AOR register 0xB2 over the range of the vendor's own table, 0x04e6 (darkest) .. 0x000c; sequence unlock / B2 / F7 03 / lock as in the vendor driver. The gamma stays the fixed initial one - no factory calibration is read. Codex's nine panel host tests were adapted (stand-ins for mutex and backlight) and pass; modules rebuilt with `tools/build-display-prototype.py --worker claude`.
- Trial `plasma-bl-01` (native Plasma, watchdog return): the device appears under the DSI panel, levels 128, 20, 1, 200, 255 were written and read back, no DSI or panel message in the kernel log, 59.5 frames per second. **Whether the panel really dims was not seen by anybody.**
- **Blanking.** Trial `plasma-dpms-01`: `kscreen-doctor --dpms off` -> CRTC inactive; `--dpms on` -> active again, the DSIM PLL locks at the first attempt, 58.7 / 59.6 frames per second afterwards. So the off/on path through panel power works in software terms; appearance unseen.
- **Starting it at boot:** `system/display-native/switch.sh` and `j701f-display.initd` are written (flag file with "once" or "always"; Volume Down held at boot skips it; a stamp makes a failed attempt fall back to the firmware framebuffer on the next boots; a hung or failed switch reboots). **They are in the repository only.** Installing a boot service on the phone was stopped by the session's permission check, so the owner is asked first. Until then the native display exists only inside the watchdog trials.

## Native display at boot, first "once" boot (2026-10-10, owner's permission given)

- Owner: "izin veriyorum" for installing the boot service (and the one MTP will need). Installed: `/usr/local/sbin/j701f-display-switch`, `/etc/init.d/j701f-display` in runlevel default (before sddm), modules and the kernel fingerprint in `~/j701f/modules/display/`.
- `/etc/j701f-display-native` = `once`, reboot: log "NATIVE display active (mode once)"; `card0` is `exynos-drm`; DECON and DSIM bound at 10 s uptime, PLL locked first time; KWin and plasmashell up; backlight `j701f-panel` on the panel; the flag file is gone and the pending stamp removed itself after 150 s. No DSI error in the kernel log.
- The phone was left running like this for the owner to look at. A reboot returns to the firmware framebuffer. Appearance, real dimming and real blanking: his answer pending.
- Six trial applications installed for E.1: audiotube, koko, kweather, kasts, marknote, pure-maps (about 310 MB together).

## C.1 / C.2: the computer reaches the phone's storage over USB (MTP) (2026-10-10)

- Method: MTP, served by uMTP-Responder 1.6.8 (GPL-3.0, github.com/viveris/uMTP-Responder, tag `umtprd-1.6.8`, commit `149efca9...`; not packaged in Alpine). Source fetched to `build/third-party/umtp-responder-src`, built natively on the phone in `~/j701f/umtp-build`, binary installed as `/usr/local/bin/umtprd`.
- The kernel already had FunctionFS for configfs gadgets. `system/usb-mtp/start.sh` (-> `/usr/local/sbin/j701f-usb-mtp`, started by `/etc/local.d/j701f-usb-mtp.start`) takes the initramfs's gadget off the bus, adds a function `ffs.mtp`, mounts it at `/dev/ffs-mtp`, starts `umtprd` and binds the gadget again; the serial shell and USB network stay. If binding with MTP fails it removes the function and binds the old gadget. `system/usb-mtp/umtprd.conf` (-> `/etc/umtprd/`): one storage, the user's home directory, read-write, files created as the phone's user.
- Checked from the computer: the USB device now has a third interface (class 6 Imaging, name "MTP"); the desktop claimed it at once; `kioclient ls 'mtp:/SM-J701F Linux/J701F/'` lists the home directory; a file copied to `Downloads` arrived intact, owned by the user, and read back identically.
- Not done: the SD card as a second storage (it is not mounted on the installed system at all yet), MTP in the recovery (C.3), behaviour across suspend. Hidden directories (`.config`, `.ssh`, ...) are visible to the computer - it is the whole home directory.

## D.1: first start-up table (2026-10-10, native display session)

`tools/app-start-bench.sh` (runs on the phone, silent): start, wait until the application and its children used almost no CPU for one second, report time, CPU time and memory (PSS); once after dropping the file cache, once warm.

| Application | cold | warm | CPU time | memory | note |
| --- | --- | --- | --- | --- | --- |
| Angelfish | 4.3 s | 12.5 s | 3.3 / 9.7 s | 84 / 204 MiB | the cold run was judged settled too early; the web engine's helper processes start late |
| Settings | 7.3 s | 4.8 s | 5.0 / 4.5 s | 128 MiB | |
| Calculator (kalk) | 9.3 s | 7.3 s | 6.7 / 6.2 s | 135 MiB | six seconds of CPU for a calculator |
| Clock | - | - | 7 s in 39 s | 118 MiB | never settles (animated) |
| GNOME Software | 21.3 s | 21.8 s | 21 / 24 s | 179 / 156 MiB | by far the heaviest start |
| AudioTube | 9.5 s | 8.8 s | 9.3 s | 208-223 MiB | |
| Koko (gallery) | 7.0 s | 4.3 s | 4.9 / 4.0 s | 100 MiB | |
| KWeather | - | - | 18.5 s in 39 s | 120 MiB | never settles: draws continuously, half a core for a weather page |
| Kasts | 7.8 s | 5.3 s | 5.5 / 4.9 s | 139 MiB | |
| Marknote | - | - | - | - | does not start at all: `Error relocating /usr/bin/marknote: _ZN5KMime7Message7subjectEb: symbol not found` (the Alpine package does not match its KMime library); removed again |
| Pure Maps | - | - | 12.5 s in 39 s | 175 MiB | never settles |

Reading: "settled" is a usable measure only for applications that stop drawing; three of them never do. The warm numbers are barely better than the cold ones, so reading files from storage is not what takes the time: the applications burn 4-7 s of processor time each before they are ready (21 s for GNOME Software). That points at what the toolkit does at start (QML compilation, shader compilation, theme loading) rather than at storage or memory. Not investigated further yet; the next step for D.2 is a profile of one small application (kalk).

## D.2: where a small Qt application's start goes (2026-10-10, one profile)

`perf record` of the first 10 s of `kalk` (300 samples per second), by library: **32 % in musl's dynamic loader** (`_dlstart` alone 16 %, plus symbol-name comparisons), 20 % Qt QML, 19 % Qt Core, 4 % libxml2, 4 % Qt Gui, 3.5 % Qt Quick, 3.4 % Mesa, 3.4 % the calculator's own library. The QML and shader caches exist and are used. So about a third of the 6 s is spent loading and relocating shared libraries and QML plug-ins - musl resolves every symbol at load time and has no prelinking - and the rest is the QML engine building the interface. Neither is a setting. Ideas not tried: keeping the big Qt/KDE libraries mapped by a preloaded helper process does not remove the relocation work per process; a zygote-style launcher would, but is a project of its own. One profile, one application: treat as a pointer, not a result.

## C.3: MTP in the recovery, image `rec7` installed (2026-10-10)

- `recovery/scripts/mtp.sh` (up / down / status): the same uMTP-Responder binary, carried with the C library's loader in `/recovery/lib` (it needs nothing else); configuration written to `/run` at start: the installed system's home directory **read-only** ("System (read-only)") and the SD card read-write ("SD card"). Started by `recovery-main` after Wi-Fi, stopped before the hand-over and by `power.sh`.
- `rec7` built, installed with `tools/install-recovery.sh`, booted with `reboot-recovery`. From the computer: device "SM-J701F Recovery" with both storages; the system's home directory lists; a file written to the SD card read back identically and was removed again; a write into the system storage was refused and nothing appeared on the phone.
- Returned to the system through the SSH reboot marker. While MTP holds the system mounted, the read-only filesystem check answers "busy"; `mtp.sh down` first.
- The native-display "once" boot the owner was asked to look at had been ended by this reboot, so it was armed and booted once more.

## D.3: GNOME Software's slow start is not the renderer (2026-10-10)

- A first comparison of GTK renderers seemed to show 9-11 s with GL against 22 s with Cairo. It was wrong twice over: the bench script was overwriting the renderer variables with the session's own (fixed: it no longer copies `GSK_*`), and the fast runs were launches that found an instance still running in the background and only woke it.
- Repeated properly: three identical runs 22.8 / 22.6 / 16.1 s; GL with optimisations off 22.8 and 22.3 s, Cairo 21.8 s (31 s of CPU), plain GL ("ngl") 22.6 s. **The renderer makes no difference to the start; the store spends about 22 s of processor time loading its catalogue**, whatever draws it.
- The session does have `GSK_RENDERER=gl GSK_GPU_DISABLE=all` (checked in plasmashell's environment).
- Options, none taken: keep the store running in the background after login (opens at once, costs about 140 MiB of the 1.6 GiB); accept it; or use Discover, whose start has not been measured the same way. Scrolling and typing stutter inside the store has not been measured at all.

## D.4: home-screen gestures counted in frames (2026-10-10, native display session)

- `tools/ui-frame-bench.sh` (on the phone, root, silent): injects a finger gesture back and forth and counts the frames the compositor presented by polling the framebuffer id of the primary plane in the DRM debug state about 14,000 times a second (this kernel has no tracing). Reported: frames per second during the tenths of a second in which anything moved, and the share of that time at 50-60.

| Gesture | While moving | Share of moving time at 50-60 |
| --- | --- | --- |
| Top panel pulled down and pushed up | 52-54 per second | 87-92 % |
| Application drawer up and down | 21-23 per second | 0 % |
| Home pages left and right | 24-25 per second | 0 % |

- A screenshot after the upward swipe shows the drawer open, so the gesture is real: **the application drawer and the page swipe animate at about a third of the refresh rate.** The compositor is not the limit (the top panel reaches 52-54 through the same compositor); the drawer is drawn by plasmashell. Cause not found.
- KWin's blur and contrast effects are **not** loaded on this phone. I unloaded and loaded them to compare; with blur loaded the top panel dropped to 45 per second (48 % at 50-60), the drawer did not change. They are unloaded again, as before.
- **Damage done and repaired:** during that back-and-forth plasmashell died with "The Wayland connection experienced a fatal error: Protocol error" (the effects own Wayland interfaces that plasmashell was using). The session was left without a shell for a few minutes until I started plasmashell again by hand from the session's environment. Do not load or unload KWin effects in a running session for a measurement.

## The slow drawer was a stale safety stamp: GPU stuck at 343 MHz for a whole session (2026-10-10)

- Looking for the cause of the 21-25 frames per second of the application drawer: plasmashell used almost no processor time during the gesture, a frame timeline showed 2-4 frames per tenth of a second during the animation - and `max_freq` of the GPU read **343 MHz**, the processor cap 1352 MHz.
- Cause: `/var/lib/j701f-gpufreq.pending`, dated 14:46. `/etc/local.d/j701f-gpufreq.start` raises the limits 40 s after boot behind that stamp and removes it 180 s later; a reset in between leaves the stamp, and every later boot then stayed at the boot-loader speeds "until someone removes the file". The reset in question was my own intended reboot shortly after a boot. Nothing announced it; the session simply ran slow.
- With the stamp removed and the limits raised by hand: drawer animation 5-6 frames per tenth of a second (55-60 per second) instead of 2-4; `ui-frame-bench.sh`: application drawer 33 per second "while moving" with 27 % of the time at 50-60 (the gesture phase follows the injected finger), home pages 42 per second and 56 %, top panel 54 as before.
- **Which of today's measurements were taken in the slow state:** everything in the boot that began at 14:47 - the GNOME Software renderer comparison and its 22 s, and the first D.4 table. The D.1 start-up table and the kalk profile were taken in the boot before (14:26), which began from a clean reboot. The 22 s for the store therefore needs to be measured again.
- Fixes: `system/gpufreq-limit` (installed) now removes a found stamp itself, so it costs one boot and the next tries again - a reset loop is still interrupted; `tools/run-recovery-update.sh` clears the stamps before its deliberate, unclean `reboot-recovery`. Codex's watchdog trials end in a hard reset by design and can leave the stamp too; his controller waits for stamps to clear before a trial but nothing protected ordinary use afterwards.
- Open: how often the owner's impression of a slow phone was this. Not knowable afterwards.

Repeated with the limits restored: GNOME Software 20.8 s cold / 14.1 s warm (21 / 17 s of CPU), kalk 9.5 / 7.0 s - start-up times are the same as before, as expected for work that is processor-bound; the stuck GPU limit had hurt animations, not starts. The store's slow start stands as measured.

## D.4 continued: task switcher, keyboard; the audio guard gets the same fix (2026-10-10)

- Frame timeline (frames per tenth of a second, GPU limit 1001 MHz) of the task-switcher gesture, a finger moving up from the bottom edge for half a second, three runs alike: `1 1 1 2 2` while the finger moves, then a pause, then `6 6 6 6 6` for the animations that follow. So **while the finger drags the task switcher open it is redrawn 10-20 times a second; once it animates by itself it runs at 60.** The drag phase is the slow part; cause not looked for (Plasma Mobile's own effect).
- On-screen keyboard: a tap on the drawer's search field did not bring the keyboard up when injected, so nothing could be measured. Open.
- `system/audio-autoload` (installed): its "pending" stamp had the same flaw as the GPU one - once left behind it silently kept sound, the video decoder and the other local modules unloaded on every later boot. Now it costs one boot.

## A.3 / D.4: typing on the on-screen keyboard (2026-10-10, one measurement)

- A password dialog could not be produced from an SSH login (`pkexec` started there is not part of the desktop session and no dialog came up), so the owner's exact case is still unmeasured.
- The keyboard did come up over the application search field. Six letters tapped at 0.45 s intervals: the keyboard process used 0.2 s of processor time, the compositor 0.5 s, **plasmashell 2.8 s** - about half a second of work per letter, because every letter starts a new search across the applications and other search sources. Frames during typing arrive irregularly, 1-5 per tenth of a second. So in this field the lag is the search behind it, not the keyboard.
- The keyboard process holds about 160-185 MiB of GPU buffers (roadmap 3.4, unchanged).
- Whether the password dialog suffers from something similar is not known; its text field belongs to a different program (the polkit agent).

## F.3: the recovery remembers its language; image `rec8` installed, not booted yet (2026-10-10)

- The recovery has no writable filesystem and never writes to the installed system, so `recovery/scripts/settings.sh` keeps its few settings in one 512-byte block of the RECOVERY slot itself, 1 MiB before the end (block 75776 of 77824): a marker line and `key=value` lines. The image occupies the first 16 of the 38 MiB and `tools/install-recovery.sh` writes only the image's length, so a new image leaves the settings alone. Five host tests (`tests/test_recovery_settings.py`): unset, set/replace, only that one block changes, unsafe values refused, a too-small device refused.
- The UI reads the language from there when nothing was chosen in the session, and writes it when the button is tapped.
- On the phone: UI rebuilt, `rec8` installed in RECOVERY from the running system; on the real partition `get` (empty), `set lang tr`, `get`, `set lang en`, `get` all correct and the first 16 MiB of the slot identical before and after. **The recovery itself was not rebooted into for this** (the phone was left in the native-display session for the owner), so the UI side is proven on the computer build only.
- Consequence: the whole-slot hash in `build/kernel/recovery-slot.json` no longer identifies the slot once a setting has been written; the image hash still does.

`rec8` first boot (same evening): with `lang=tr` stored from the installed system, the recovery came up in Turkish; a tap on the language button switched it to English and `settings.sh get lang` then returned `en` (`build/screenshots/rbt-lang.png`). So the UI reads and writes the settings block on the phone. Returned to the system, native display armed for one more boot, stamps cleared before the unclean reboot.

## Owner confirms the native display; it is now the daily path (2026-10-10)

- Asked whether the picture, the brightness slider, screen off/on and the earlier line/tearing were right on the native driver, the owner answered "Doğru" (correct). First time anybody has seen the panel on this driver.
- `/etc/j701f-display-native` now holds `always`: every boot switches to DECON + DSIM + panel before the desktop starts. Ways back unchanged (Volume Down held at boot, the stamp after a failed switch, removing the file); the Volume-Down path and the failure path have not been exercised on a real boot.
- Still RAM-only in one sense: the display nodes come from an overlay loaded by a module that is pinned to the kernel in BOOT. A new kernel image needs the two modules rebuilt and the fingerprint file renewed, otherwise the switch declines and the phone boots on the firmware framebuffer.
- His other answers: the store is **not** to be kept running in the background; the store currently shows only installed applications (so he could not try an installation); all five trial applications stay; "we have concentrated on the store too much - let us pause it". Store work is parked: the "installed only" view and the unconfirmed password fix are recorded, not pursued.

First reboot under `always` (same evening): the phone came up on the **firmware framebuffer** - my own stamp was still there, because I had rebooted less than 150 s after the previous native boot, and the first version of the switch kept a found stamp for good. The flaw I had just removed from the GPU guard. Fixed the same way: a found stamp is deleted and costs that one boot; `system/stamps-stop` (clean shutdown) removes it too. Installed, stamp cleared, rebooted after the guards had settled: "NATIVE display active (mode always)", `exynos-drm`.

## B.4: suspend and resume on the native display; a suspend warning from my charger driver fixed (2026-10-10)

- Suspend-to-idle with an RTC alarm 25 s ahead (`wakealarm`, `echo freeze > /sys/power/state`), native display active: suspended at 238.9 s, resumed at 264.3 s; on resume the DSIM PLL locked at once, the CRTC is active, compositor and shell alive, top-panel gesture at 57 frames per second. So the panel path survives a suspend in software terms; **what the screen showed across it was not seen by anybody.** (A first attempt used `rtcwake`, which is not installed: nothing had happened, and I had not noticed until the log showed no suspend.)
- During that suspend the kernel warned "i2c i2c-4: Transfer while suspended" from `j701f_charger_poll`: the status poll of my own charger driver ran on the ordinary workqueue while devices were suspended. Now on `system_freezable_wq` (patch `linux-power-j701f-s2mu005-charger.patch` and the tree; the module built out of tree in `build/kernel/chg-mod` and installed in `~/j701f/modules/misc/`). A second suspend/resume: no warning.
- Also seen once in the log, not pursued: `exynos_drm_gem_prime_import_sg_table: buffer chunks must be mapped contiguously` - something tried to hand a GPU buffer to the display directly and was refused (the fallback path works; this is what the optional display IOMMU, B.5, would allow).

## F.2: rotation matrix in the device tree; BOOT = `accel1`, first real kernel-image update through the recovery (2026-10-10)

- `kernel/dts/exynos7870-j7velte-extra.dts`: `mount-matrix` of the accelerometer corrected to the one the owner confirmed (`0, -1, 0; 1, 0, 0; 0, 0, -1`).
- Image `accel1` built from the same tree: kernel payload byte-identical to `dsimpll2` (GNU build ID `1950147e...`), device tree differs in that one property only (decompiled and compared), initramfs is the current one (it has the recovery hook of `/init`, inactive without the UI binary; `dsimpll2` had Codex's older one).
- Written with `tools/run-recovery-update.sh accel1`: staged, into the recovery, written and read back by `flash-boot.sh`, clean reboot; BOOT partition `50f2e397...`. The tool removes the start-up stamps before its unclean reboot now.
- After the reboot: native display switch worked as before (same kernel, so the pinned modules still match); `in_accel_mount_matrix` reads the new matrix; the override was removed from `system/accel-udev.rules` and from the phone (the rule only selects polling now).
- Not checked by turning the phone: the kernel reports the same matrix the udev rule supplied before, so the behaviour should be unchanged; the owner's confirmation refers to the override.
- For Codex: BOOT is no longer `dsimpll2`; his trial controller pins that baseline and will refuse until its records are renewed.

## F.3: the recovery's buttons exercised by taps (2026-10-10, `rec8` in RECOVERY)

Taps injected into the touchscreen over SSH, each step checked on a dump of the framebuffer (`build/screenshots/rbt-t*.png`):

- **Files:** home -> Files -> `mnt` -> the image file selected; "Copy to SD card" -> confirmation -> "storage: COPIED to /mnt/sd/j701f-files/accel1.img" (the copy removed again afterwards).
- **Kernel:** "Flash the selected image" -> confirmation -> "flash-boot: WRITTEN AND VERIFIED: accel1.img"; "Roll back to the previous image" -> confirmation -> "flash-boot: ROLLED BACK AND VERIFIED". The image was the one already in BOOT, so the slot is unchanged before, between and after: `50f2e397...`.
- **Power:** the page and the confirmation for "Reboot into the system" came up; the owner stopped the session there, and the phone was back in the installed system when I next looked (he tapped, or it was rebooted another way - I did not send that tap).
- Cosmetic, not fixed: the selected path is shown with a doubled slash (`//mnt/accel1.img`); confirmation boxes are light on a dark interface.
- Still not exercised: power off and download mode, the recovery with an unreadable installed system.
- The owner then cleared the goal and judged the project "largely complete". Next asked for: flashlight (front and rear), then the cameras.

## Flashlight: rear and front LED (2026-10-10; electrically confirmed by the chip, light not yet seen)

- Owner: "do the flashlight, then we start on the camera."
- Hardware, from the factory device tree and the vendor driver: both LEDs hang on the S2MU005's two flash-LED current sinks (channel 1 rear, channel 2 front); two GPIOs (gpd3-2/3) are alternative enable inputs. Reference fetched: `drivers/leds/leds-s2mu005.c` and its header from the pinned vendor tree (`build/kernel/vendor-fled-reference/`, GPL-2.0).
- Implementation: in my existing charger driver (`linux-power-j701f-s2mu005-charger.patch`, same I2C device and regmap): two LED class devices, torch mode only, enable bits over I2C. `white:flash` = rear, 6 steps of 25 mA (25-150 mA; vendor default 75, vendor limit 400); `white:front-flash` = front, 2 steps (25-50 mA; vendor 50). Vendor order of writes kept, including the bit it sets for torch while a charger is attached. Off across suspend. Photo-flash mode not implemented. The chip is revision 4, so the enable register is 0x3c.
- Built out of tree (`build/kernel/chg-mod`), installed as `~/j701f/modules/misc/j701f-s2mu005-charger.ko`; `system/flashlight-udev.rules` (-> `/etc/udev/rules.d/82-j701f-flashlight.rules`) makes the two brightness files writable for the desktop user (takes effect when the module loads at boot).
- Test, each LED 2 s at the lowest step: the chip's status register read `0x40` with the rear channel on and `0x10` with the front one, `0x00` before and after; no fault flag (open/short) in the LED interrupt register. **Nobody was looking at the phone: whether light came out, and from which LED, is for the owner to say.**
- Use: `echo 3 > /sys/class/leds/white:flash/brightness` (0 = off). Plasma Mobile's flashlight button looks for an LED whose name contains `:flash` or `:torch`; whether it picks this one up has not been checked.

Owner, right after the test: the **front** flash lit up (he saw it); the rear one faces the table, so he could not see it. Front LED confirmed on channel 2; rear still unseen.

Owner, later: **both the front and the rear flash work; the rear one gets brighter step by step up to 6.** Flashlight confirmed. Plasma's flashlight button not reported on.

## Camera: reconnaissance only (2026-10-10; nothing built, nothing touched on the phone)

- **What is fitted** (factory device tree, `build/kernel/j701f-live.dtb`): rear Samsung S5K3L2 (13 MP) at I2C address 0x2d with a DW9807 autofocus actuator at 0x18; front Samsung S5K5E3 (5 MP) at 0x10. Two MIPI CSI-2 receivers at 0x14420000 (rear) and 0x14460000 (front), both feeding one capture block at 0x14410000 (vendor names "flite"/BNS), one D-PHY provider, the ISP power domain, three sensor clocks.
- **What mainline has:** the clock controller for this block (`samsung,exynos7870-cmu-isp`) and the CAM0 system-register node are already in the 7870 device tree. No driver for either sensor (`drivers/media/i2c` has S5K3M5, S5K5BAF, S5K6A3, S5KJN1 only). A CSI-2 receiver driver and a FIMC-LITE capture driver exist for the Exynos 4 / 5250 generation; whether the 7870's blocks are close enough to extend them has not been compared register by register.
- **Community:** the postmarketOS wiki lists the camera as broken for the Exynos 7870 and for its J7 devices; the upstream 7870 series of 2025 does not mention cameras. Nothing ready to take over was found. (Sources: wiki.postmarketos.org pages "Samsung Exynos 7870 Octa", "Samsung Galaxy J7 Prime", "Samsung Galaxy J7 Pro"; lkml "Add support for the Exynos7870 SoC".)
- **Why a raw path looks possible:** in the vendor design each sensor has its own capture device (CSI receiver -> "flite" -> memory) in front of the image processor, so Bayer frames reach memory before the closed ISP firmware is involved. That is an inference from the device tree and driver structure, not something tried.
- **Proposed first milestone (cheap, reversible):** power one sensor with its regulators, clock and reset as the vendor does and read its chip ID over I2C. No image, but it proves power, clock and bus - the base of everything else.

## Camera milestone 1: the rear sensor answers (2026-10-10; BOOT = `cam1`)

- Owner's goal: "a working camera".
- Reference fetched from the pinned vendor tree into `build/kernel/vendor-camera-reference/` (GPL-2.0): the S5K3L2 and S5K5E3 sensor files and their module (power-sequence) files.
- Connections of the rear sensor, from the factory device tree: I2C 0x2d on `hsi2c@138a0000`; AVDD 2.8 V = PMIC LDO35; DVDD 1.2 V enable = gpd4-4; IO 1.8 V enable = gpf3-2; AF 2.8 V enable = gpd1-1; reset = gpf3-3 (low = reset); MCLK 26 MHz on gpe0-0 from the MIF "sensor 0" clock. All of bus, clock, pin group and regulator already exist in the mainline 7870 device tree and our PMIC include.
- `kernel/dts/exynos7870-j7velte-camera.dts` (new top of the chain): enables that I2C bus and adds a `camera@2d` node. Image `cam1`: kernel byte-identical to the one in BOOT, device tree differs by that node (phandle numbers shift; the display overlay refers to the base tree by symbol, so it is unaffected - and the native display did come up after the update). Written with `tools/run-recovery-update.sh cam1` (BOOT `3cafec04...`). `tools/prepare-boot-update.py` now has a branch for the recovery flow (image only; the 3.18 scripts need a previous partition image that is no longer recorded).
- `tools/kmod/j701f_cam_probe.c` (built in `build/kernel/cam-mod`): powers the sensor in the vendor's order, reads the identity registers, powers it down. Result on the phone: **`rear sensor answers: model 0x30c2 revision 0xb1 (MCLK 26000000 Hz)`** - 0x30C2 is the S5K3L2. Power, clock, reset and I2C to the rear sensor work on the mainline kernel.
- Not yet: any pixel. Next: the CSI-2 receiver and the capture block, compared against the vendor code.

## Camera milestone 2 groundwork: the capture path is simpler than feared (2026-10-10)

- Vendor configuration of this phone (`build/kernel/baseline/config`): `CONFIG_CSIS_V4_1`, `CONFIG_FIMC_BNS_V4_10_0`, `CONFIG_FIMC_IS_V3_11_0` and **`CONFIG_USE_CSI_DMAOUT_FEATURE=y`**: the CSI-2 receiver has its own DMA output and writes frames straight to memory. A raw capture therefore needs the receiver and the sensor only - not the "flite"/BNS block and not the image processor with its closed firmware.
- More reference fetched (same pinned tree, `build/kernel/vendor-camera-reference/`): `sensor/csi2/fimc-is-hw-csi-v4_0.[ch]` (register map with fields, the hardware functions: reset, lanes, settle, channel config, DMA config and address, enable, interrupt sources), `fimc-is-device-csi_v2.c`, the v3.11.0 chain and power files.
- Read on the phone, read-only, with the CAM0 power domain switched on for the moment (my `j701f_cam0_off` module unloaded and loaded again): both receivers answer - `0x14420000` and `0x14460000`: VERSION `0x04010000` (v4.1), CMN_CTRL `0x4000`, CLK_CTRL `0xf0`, DMA control registers present and zero. So the block is clocked and reachable on the mainline kernel as the boot loader left it. (First attempt used a `devmem` applet that this BusyBox does not have; nothing was read then.)
- Plan from here: (1) a test module that powers the rear sensor, writes one of the vendor's mode tables, points the receiver's DMA at one contiguous buffer, takes a single frame and lets user space read the raw Bayer data - the first picture, without any V4L2 plumbing; (2) the same as a proper V4L2 sensor driver plus receiver/capture driver; (3) libcamera with its software image processing; (4) front sensor; (5) autofocus.
- Risks known now: the mode tables are large and vendor-specific (machine-converted, not understood line by line); D-PHY timing ("settle") per mode; the display SysMMU-style question (does the receiver's DMA need its IOMMU switched to bypass as the video decoder did); clocks are only "as the boot loader left them" while `cmu_isp` is disabled in our tree.

## Camera milestone 2: raw frames arrive from the rear sensor (2026-10-10; BOOT = `cam3`)

- `tools/kmod/j701f_cam_frame.c` (test module, no V4L2): powers the S5K3L2, writes the vendor's initial tables and the 2072x1552 30 fps mode (machine-converted by `tools/kmod/gen-s5k3l2-tables.py` into `s5k3l2-tables.h`), configures the CSI-2 receiver (CSIS v4.1) with its DMA output pointing at one 8 MB contiguous buffer, starts the sensor for half a second, stops and powers everything down. Buffer and a status text in debugfs (`/sys/kernel/debug/j701f_cam/`). The receiver is only started after the sensor has confirmed the mode's output size, so its DMA cannot run past the buffer.
- Device tree (`exynos7870-j7velte-camera.dts`): the camera node also names the receiver's D-PHY (`<&mipi_phy 0>`) and the two MIF clocks that feed the camera block (`cam3` image; two BOOT updates through the recovery on the way, `cam2` and `cam3`).
- Three things had to be found:
  1. An I2C client has no DMA mask (allocation failed with -EIO); and a buffer for the sensor's largest mode (26 MB) could not be had, hence the size check above.
  2. **The SysMMU of the camera block comes out of reset enabled with no page table** (CTRL 0x3, STATUS 0x1), exactly as the video decoder's did: switched to bypass for the test, restored afterwards.
  3. **Clocks.** First capture: frames arrived but with CRC, ECC, ID and lost-frame-start errors (`INT_SRC0 = 0xf1101107`) and only 62 kB of data. The block's clock controller (`cmu_isp`) has no driver bound in our tree and the boot loader leaves all its "user" multiplexers on the 26 MHz oscillator (five registers read `0x00200000`). With bit 12 set on three of them (camera clock, ISP clock, receiver byte clock) and the two MIF clocks enabled (399.75 MHz each): **`INT_SRC0 = 0x01100000` - frame start and frame end only, no error - 24 frames counted, 4,842,240 bytes per frame.**
- Format, worked out on the computer: 3120 bytes per line, two 10-bit samples in three bytes, little-endian 12-bit packing (`tools/raw12-to-png.py` converts a frame to a picture: unpack, half-resolution Bayer to RGB, black level 64, grey-world balance, gamma).
- The frames so far are black: every sample 59..74 around the sensor's black level of 64 - the phone lies on its back with the lens against the table, also with the flash LED on. So: a genuine dark frame, coherent data, but **no picture of anything yet**. Needs the owner to hold the phone up.
- Not done: Bayer order unverified (needs a real scene), exposure and gain are whatever the mode table sets, no V4L2 driver, no libcamera, front sensor, autofocus. The test leaves the CAM0 power domain on (my power-saving module is unloaded for it).

## Camera milestone 3: the first real picture; the front sensor delivers frames too (2026-10-10; BOOT = `cam4`)

- **Rear camera, first picture of a scene:** `build/screenshots/camera-rear-3.png` - a ceiling with a beam, a flag-like object with blue and red stripes and a framed picture on the wall, recognisable and with plausible colours. Taken with `exposure_lines=2000 analog_gain=256` (8x), new module parameters written to the standard registers 0x0202 / 0x0204 after the mode table; with the table's own values the room was too dark (all samples near the black level of 64). The colours come out sensibly with the Bayer order GRBG; not checked against a known colour chart.
- The earlier frames were black because the lens was against the table; the phone has since been turned over (the owner tried the flash), so now the rear lens looks at the ceiling and the front one at the table.
- **Front camera (S5K5E3):** `j701f_cam_frame.c` generalised to a per-sensor configuration (receiver base, lanes, settle, clock multiplexer, tables, buffer size); device tree node on `hsi2c@138c0000` (image `cam4`, written through the recovery). Sensor identity `0x5e30`, mode 1280x960 accepted. First attempts: the sensor streamed (its frame counter ran) but the second receiver saw no lane activity. Cause, from the vendor PHY driver fetched for this (`phy-exynos-mipi.c`): its device tree's "option" is a **bit number in the CAM0 system register (0x144f1040)**, bit 3 for this receiver, set by `phy_set()` from the vendor CSI code; the mainline PHY driver sets the reset bits in that register but not this one. With bit 3 set: frame start/end only, no errors, 1,843,200 bytes per frame (1280 x 960 x 1.5). The front picture is black because that lens now faces the table.
- Buffers: 6 MB (rear) and 3 MB (front); a second 8 MB buffer could not be allocated. The receiver's byte-count register does not always equal the frame size (it read 894,720 for a full front frame); the data in memory was complete.
- State of the "camera": **a test module that takes one burst of frames per load and a script on the computer that turns the raw data into a picture.** No V4L2 device, no application can use it, no automatic exposure, no white balance beyond a grey-world guess, no autofocus (the rear lens sits wherever its actuator rests), no full resolution.

## Camera milestone 4: the phone takes photographs by itself (2026-10-10)

- `system/camera/j701f-photo` (-> `/usr/local/bin`, needs `py3-numpy` and `py3-pillow`, both installed): loads the capture module two or three times to find an exposure (aims the bright parts of the scene at mid-scale; exposure up to the frame length, gain up to 16x), then unpacks, demosaics (bilinear), balances (grey world), applies gamma and saves a JPEG in `~/Pictures/Camera`. `system/camera/j701f-camera` plus two menu entries ("Camera (rear)", "Camera (front)") take one photograph and open it in Koko.
- On the phone: `sudo j701f-photo rear` -> `IMG_20261010_171357_rear.jpg` in 9.5 s (700 kB, 2072x1552; exposure 3160 lines, gain 16x in the dim room): the ceiling again, a Turkish flag and a light-blue one recognisable (`build/screenshots/phone-photo-rear.jpg`). `front` -> a file in about 6 s, nearly black because that lens faces the table. The menu entries were installed but not tapped.
- **A kernel oops on the way, caused by me:** the two sensor nodes share the 1.8 V enable GPIO and I had requested it "non-exclusively" from both devices. After a module reload the request failed ("a GPIO is missing"), and the next load oopsed in the driver core (`pm_runtime_get_suppliers`, then a second fault). `reboot -f` did not return on that kernel; magic SysRq sync / remount read-only / reboot did. No filesystem error afterwards. Now the module binds one sensor per load (`only=rear` by default, `only=front`) and requests the line normally.
- Module parameters: `only`, `exposure_lines`, `analog_gain`. Module on the phone: `~/j701f/modules/camera/` (not loaded at boot).
- Wiki: new page `reference/camera(.tr).md`.

Camera, same evening: the launcher's script was run inside the desktop session (not tapped): the photograph was taken and saved, but **Koko did not open** - given a file to show, Koko on this Alpine exits with "QQmlComponent: Cannot create a component in an invalid context" (19 times); started without an argument it works. The launcher now sends a notification with the file name and starts Koko plainly; a screenshot shows Koko's Pictures view with the Camera folder and its thumbnails (`build/screenshots/camera-check.png`). `j701f-photo` also raises the colour saturation by 1.6 (no colour matrix for these sensors is known here): the flag in the test scene is now clearly red.

## Camera milestone 5: real camera devices; Plasma Camera shows a live preview (2026-10-10; BOOT = `cam5`)

- Owner: the snapshot launchers gave "FileNotFoundError" (my fault: I had left a streaming test module loaded, which held the sensors; fixed) and Plasma Camera, which he installed, listed no camera (it uses libcamera, which needs real camera devices). Asked which way to go, he chose "the proper way".
- **The receiver has a second DMA layout.** With its 12-bit packing off it writes plain 16-bit little-endian samples: exactly V4L2's `SGRBG10`, 6,431,488 bytes for 2072x1552. Found with a test parameter - and that test **overran its 6 MB buffer by 140 kB** (my size guard checked the mode, not the layout). Phone rebooted at once with sync / remount / reboot; no filesystem error. Buffers in the new driver are sized from the layout.
- **`tools/kmod/j701f_camera.c`**: for each sensor node a media device, a sensor sub-device (one fixed mode; exposure, analogue gain, read-only blanking and pixel rate, orientation and rotation from the device tree) and a capture video node (`SGRBG10`, vb2). The receiver's DMA alternates between two driver buffers (ordinary cached pages) and a polling thread copies each finished frame into the application's buffer. Device tree (`cam5`): new compatibles, `orientation`/`rotation` (90 and 270, assumed), and the shared 1.8 V switch as a fixed regulator.
- **libcamera 0.7.1** (Alpine): its generic "simple" pipeline accepts a fixed list of platform drivers, so the media device calls itself `qcom-camss`, an entry with software image processing enabled. That is a local trick, stated in the driver; the alternative is a patched libcamera. `cam -l`: "Internal back camera", "Internal front camera".
- Its software image processing needs a dma-buf provider and the kernel in BOOT has neither `UDMABUF` nor dma-buf heaps: `drivers/dma-buf/udmabuf.c` built **out of tree as a module** (`tools/kmod/udmabuf-out-of-tree.patch`: one check dropped because `memfd_fcntl()` is not exported, licence/namespace lines added). No kernel image change, so the display modules still match.
- GPU or CPU processing: on the GPU path libcamera's buffers are offered to the display driver, which refuses them ("buffer chunks must be mapped contiguously"), and `cam` aborted in about one start in three. With `LIBCAMERA_SOFTISP_MODE=cpu` (set for the desktop session in `~/.config/plasma-workspace/env/j701f-camera.sh`): three runs of 40 frames without a failure; libcamera's own benchmark 50 ms per frame in Plasma Camera.
- Exposure: libcamera's automatic exposure works with the two controls but climbs 10 % per frame, so in a dim room the picture takes a few seconds to come up; with the rear flash LED on, a frame from `cam` shows the ceiling and the flags in colour (`build/screenshots/libcamera-rear.jpg`).
- Boot: `~/j701f/modules/camera/load.sh` (five modules) is run by the guarded `/etc/local.d/j701f-audio.start`; udev rule `83-j701f-camera.rules` gives media, video, sub-device nodes and `/dev/udmabuf` to group `video`; my power-saving module that switched the camera block off at boot is moved aside (the block stays powered now). After a reboot both cameras were there without my doing anything.
- **Plasma Camera, started inside the session: live preview of the rear camera** (`build/screenshots/plasma-camera.png`), shutter button and Photo/Video switch visible. Not done by anybody yet: pressing the shutter, switching to the front camera, recording video; whether the assumed rotation is right when the phone is held normally.
- Also: v4l2loopback 0.15.1 was fetched and built for this kernel on the way (`tools/kmod/v4l2loopback-linux-7.1.patch`) for the route not taken; it is not installed. The snapshot launchers are removed; `j701f-photo` and the test modules remain as tools (they need the real driver unloaded).

Camera, same evening - Plasma Camera exercised by injected taps (audio output muted for the duration and restored; screen kept awake - a first attempt screenshotted a blanked screen and showed nothing):

- **Shutter:** `~/Pictures/image_0001.jpg` written, 1552x2068 portrait JPEG (`build/screenshots/plasma-camera-photo.jpg`): the lit ceiling and the flags; its thumbnail appears in the application.
- **Camera switch:** the preview changes to the front camera and keeps running (dark and noisy: that lens faces the table).
- **Video: does not work.** The application logs "Started recording" / "Stopped recording" with the MP4 muxer, but the file is 48 bytes with no video in it. Not investigated; FFmpeg on the phone offers `libx264` as well as the hardware `h264_v4l2m2m` encoder wrapper, and which one Qt picked is not known.
- Unchanged open points: orientation with the phone held normally, colours, the front camera on a real scene, the owner's own use.

Camera, owner's first report from Plasma Camera: **"the photographs are upside down"**. So he took photographs with it himself, and the assumed rotation of the rear sensor was wrong by 180 degrees. The driver now reports 270 for the rear sensor and 90 for the front one (the front value is the mirrored assumption, not checked); the device tree source carries the same values for the next image, the image in BOOT (`cam5`) still has the old ones and the driver overrides them. The module could not be reloaded while the desktop held the camera devices, so the phone was rebooted; the controls read 270 and 90 afterwards.

Video recording, looked at further and still not working: the encoder is fed frames (the debug log shows them being sent) but the MP4 file stays at 48 bytes and never gets its index, also a minute after stopping. Qt found no hardware encoding context (VDPAU, VA-API, Vulkan all refused) and skipped the V4L2 wrapper encoders. Whether it is the software encoder being far too slow for 1552x2068 frames or something else is not known.

## Free-work session: battery gauge, charging speed, SD card, clean trip to the recovery (2026-10-13; BOOT unchanged = `cam5`)

The owner paused the camera and gave two hours to raise the port's quality on a route of my choosing. A health survey came first; what it found and what was done:

- **The computer's reboot had wiped the kernel build tree** (`/tmp` is a tmpfs). Rebuilt with `tools/build-kernel.py panfrost`: **same GNU build ID `1950147e…`**, so the modules on the phone still match; then `make modules` once for `Module.symvers` (out-of-tree module builds need it; `build-kernel.py` does not produce it).
- **Battery percentage was wrong: 43 % on a full battery.** Evidence: 4.35 V at the cell, charger state "top-off/done", current tapering. The fuel gauge chip holds the right battery model (its table registers match the factory device tree's `battery_table3/4`, the aged variant of the capacity), but its raw value really was 43 %: it counts charge ("current mode", register 0x4A = 0x10) and nothing ever corrected the drift. The vendor driver (fetched for reference, `build/kernel/vendor-fuelgauge-reference/`) switches the chip to voltage mode (0x4A = 0xFF) when charging above 99.6 % of the float voltage with less than 500 mA, or at 98 %, and near empty; back to current mode otherwise. Tried by hand: with 0xFF written the value rose 43 → 47 % in two minutes and 80 % twenty-five minutes later, still rising toward full.
- **`system/fuelgauge/j701f-fuelgauge`** (renamed `system/battery/j701f-battery` later the same evening, see below): the vendor's switch as a 30-second loop in user space (reads sysfs, writes that one register with `i2cset -f`; `i2c-tools` installed on the phone). Running on the phone from `~/j701f/fuelgauge/` for this boot. **Not installed as a boot service**: the attempt was stopped by the permission check, so it waits for the owner's yes (`j701f-fuelgauge.initd` is ready). The chip kept 0xFF across a reboot.
- **Charging was limited to 500 mA in / 450 mA into the battery from any source** - the bootloader's computer-port values; a wall charger was no faster. Charger driver (`kernel/patches/linux-power-j701f-s2mu005-charger.patch`, a module): the two limits are now set by cable type on every type change (DCP `dcp_input_ma`/`dcp_charge_ma` = 1200/1000 mA, CDP 1000/1000 as the vendor, otherwise 500/450) and are writable through sysfs, capped at 1550/1500 mA. Deliberately below the vendor's 1550/2150 mA for a wall charger because the battery temperature is not read here. Verified on the phone on a computer port: module reloaded, flash LEDs still there, writes read back, 9 A request capped to 1.5 A, values restored, policy line in the log after a boot. **The wall-charger branch has not been exercised** - it needs a wall charger plugged in.
- **SD card**: was never mounted in the system. `/etc/fstab` line (`/dev/mmcblk2p1 /media/sdcard vfat nofail,uid=1000,…`), mounted and writable as the user; `system/usb-mtp/start.sh` adds it to the running MTP server (`umtprd -cmd:addstorage`) when it is mounted. The computer lists two storages, "J701F" and "SD-card" (`mtp-detect`), also after a reboot.
- **Trips to the recovery were unclean shutdowns** (`reboot-recovery` only syncs). `system/reboot-recovery.sh` (phone: `~/j701f/boot-swap/reboot-recovery.sh`): clears the stamps, stops SDDM, SysRq-u, then the helper. Tried: in the recovery the system partition's superblock read state 1 (clean) with no needs-recovery flag; the system came back with native display, SD card, MTP and the new charger module. `tools/run-recovery-update.sh` uses it now.
- Looked at and left: `regulatory.db` is asked for at 3 s, before the root filesystem exists, so installing `wireless-regdb` does not help (it would have to be in the initramfs; the Wi-Fi chip is 2.4 GHz FullMAC, little to gain); the two CMA allocation failures at boot are retried and harmless, and "CmaFree" being low is normal (movable pages borrow the area); the phone has a proximity sensor but **no ambient light sensor**, so no automatic brightness; boot takes 28 s from kernel start to the shell (display switch at 11 s, SDDM 14 s, KWin 18 s).
- A tool mistake worth a line: the host's shell is now fish, where `$O` with several options is one word - a first attempt at the recovery trip did nothing at all. Multi-step host commands go through a `bash` script file.

Free-work session, second half (2026-10-13):

- **Time zone and clock.** `/etc/localtime` did not exist: the phone showed UTC, two hours behind the wall clock. Linked to the zone of the owner's computer (an assumption about where the phone lives; trivially changed). The hardware clock stood in January 2000: the kernel reads it at boot (`RTC_HCTOSYS`) but the one-shot `ntpd -q` never marks the clock as synchronised, so the kernel never writes it back. `system/wifi` (`/sbin/j701f-wifi`, previous copy kept as `.prev`) now runs `hwclock -w -u` after each successful fetch; after a reboot the system came up with the right time before Wi-Fi.
- **Battery temperature.** The factory device tree has the SoC's ADC at 0x10550000 with the battery thermistor on channel 1 and a board ("AP") thermistor on channel 0; mainline's `exynos7870.dtsi` has no ADC. Tried first: a run-time overlay with `samsung,exynos7-adc` - the built-in driver bound and every conversion timed out. With the vendor's "v3" sequence written by hand through `/dev/mem` all eight channels converted (vendor source fetched for reference, `build/kernel/vendor-adc-reference/`). So: **`tools/kmod/j701f_adc.c`**, a module that applies its own small overlay (`j701f-adc-overlay.dtso`, compatible `j701f,exynos7870-adc`) and drives the ADC itself, polled, as a hwmon device with `temp1` battery and `temp2` board, converted with the factory tables (`j701f-adc-tables.h`). On the phone: battery 24.4 °C, board 32.5 °C - believable for a phone lying on a desk on a slow charge. Installed in `~/j701f/modules/misc/`, which the guarded boot loader inserts. A lesson on the way: an overlay blob handed to `of_overlay_fdt_apply()` must be 8-byte aligned ("Invalid overlay_fdt header" otherwise), and a module without an exit function cannot be replaced without a reboot.
- **Battery helper** `system/battery/j701f-battery` (was `fuelgauge/j701f-fuelgauge`): besides the gauge mode it now sets the charge current by battery temperature - with a wall charger between 15 and 41 °C up to the driver's caps (1550/1500 mA), 700 mA below 15 °C, 450 mA below 5 or above 41 °C, 100 mA above 50 or below 0 °C, with hysteresis; nothing without a temperature reading. `tests/test_battery_daemon.py` runs the script against a simulated sysfs tree (11 cases; one of my expectations was wrong, the script was right: the vendor's "empty" test corrects the voltage for the load). Still **not a boot service**; running by hand on the phone. Gauge: 91 % a little over half an hour after the mode change.
- **Wiki**: status tables on the front page and the hardware page were badly out of date (display "no real panel driver", camera "not working", `RECOVERY` "vendor kernel", accelerometer "to be confirmed", no flashlight row); brought up to date in both languages, with a new "what comes next" list.
- Repository tests: 243 passed. `mkdocs build --strict` clean.
- Not tried, needs the owner: a wall charger (cable type DCP → 1200/1000 mA by the driver, 1550/1500 by the helper), and the yes for installing the helper as a boot service.

Free-work session, last part (2026-10-13):

- **Charging can be switched off.** Charger driver: the standard `charge_behaviour` property (`auto` / `inhibit-charge`), which moves the chip's mode field (CTRL0 bits 2:0) between 2 "buck and charger" and 1 "buck only", as the vendor's `s2mu005_enable_charger_switch()` does on this chip revision (4). On the phone: inhibited, the battery current fell from 116 mA to 1 mA, status "Not charging", register 0x11, and the resting cell voltage read 4.277 V; `auto` brought 129 mA and "Full" back, register 0x12. That resting voltage is an independent check of the gauge correction: it belongs to a battery well above 90 %, and the gauge now says 93-96 %.
- Battery helper: above 50 °C or below 0 °C it now inhibits charging instead of setting the minimum current, and gives charging back below 45 / above 5 °C, when the cable is pulled, or when the temperature can no longer be read; an inhibit it did not set itself is left alone. Tests: 17 cases, three of them two-round runs for the "charging comes back" paths.
- A 20-second suspend-to-idle with a clock alarm passed with the new modules loaded (temperature readable and charger answering afterwards; the known one-off touch-key I2C message on resume is unchanged).
- State of the phone at the end: BOOT `cam5` and RECOVERY `rec8` untouched; new or changed on the root filesystem: `/etc/fstab` line for the SD card, `/etc/localtime`, `/sbin/j701f-wifi`, `/usr/local/sbin/j701f-usb-mtp`, packages `i2c-tools` and `wireless-regdb`; in `~/j701f/`: `modules/misc/j701f-s2mu005-charger.ko` (new), `modules/misc/j701f_adc.ko` (new), `battery/`, `boot-swap/reboot-recovery.sh`.

- **`tools/phone-health.sh`**: the session's opening survey as a read-only tool - one `ok`/`WARN`/`FAIL` line each for the running system, kernel build ID, display driver in use, desktop, guard stamps, frequency limits, modules, battery (with a plausibility check of percentage against voltage, which would have caught the drifted gauge), battery helper, temperature, clock and hardware clock, SD card, MTP, Wi-Fi, kernel oopses, memory, disk. All `ok` at the end of the session.
- Also: the SD card is in the file manager's "Places" (`~/.local/share/user-places.xbel`, previous file kept beside it); `system/battery/install.sh` is the one command that makes the helper a boot service (not run). Checked that a missing SD card cannot hold the boot: OpenRC's `localmount` returns success regardless of a failed non-critical mount.

- **`tools/build-kernel.py` had a trap of its own**, found by running the whole flow with the edited charger patch: a patch edited after it had been applied was applied again on top of its older version and failed (earlier edits of that patch had been carried into the tree by hand). `apply_patches()` now keeps a copy of every applied patch beside its marker, reverses the older version first, and refuses with a plain message when a tree was prepared before copies were kept (`tests/test_kernel_patches.py`, 4 cases). New option `--modules` also builds the in-tree modules, which leaves the `Module.symvers` that separately built modules need. Run end to end: PASS, **build ID still `1950147e…`, Image hash unchanged** - the charger changes are module-only, as intended. (The charger `.ko` built inside the tree and the one built with `M=` differ in hash; the one on the phone is the `M=` build.)
- Wiki corrections found on the way: the "everyday loop" still named `fbmem.dts` as the device tree to build from (an image from it would have had no camera nodes) and described the update as going through the vendor system; both pages and the device-tree chain table now say `camera.dts` and the recovery.

Free-work session, second hour (2026-10-13, after the owner set the goal "two hours of free work"):

- **Roadmap 3.7, backup and a rehearsed restore.** `tools/phone-backup.sh`: runs the recovery's own `backup.sh` on the live system with a fuller list (`/etc`, `/sbin`, `/usr/local`, `.config`, `.local/share`, `~/j701f/modules`, the battery helper, the reboot-recovery helpers), archive on the SD card (35 MB, 1693 entries, hash recorded and verified), then unpacks it into an empty directory on the phone and compares every file with the live one: 1369 identical, 0 changed, 0 gone, 0 with a different type, owner or mode; directory removed. First run reported four differences that were the tool's, not the backup's: BusyBox tar leaves symbolic links owned by root, so links are now compared by type and target only. The archive holds secrets and stays on the card. Steps for rebuilding an erased phone are in the wiki; not rehearsed, by the owner's rule.

- **Roadmap 3.1, application start: the loader's share measured.** The loader alone (`ld-musl --list`, warm cache, median of six): Calculator 94 libraries 0.54 s, Settings 97 / 0.57 s, Koko 134 / 1.09 s, Angelfish 170 / 1.12 s, GNOME Software 126 / 0.81 s. That is before the program's first own instruction, and the plug-ins loaded later are resolved the same way. Nothing in this port can change that share. A `perf` profile of a warm calculator start (8 s, 499 Hz, flat): loader 26.9 %, libQt6Qml 17.0 %, kernel 15.9 %, libQt6Core 15.4 %, Gui 3.8 %, libxml2 3.4 %, Quick 3.4 %, Mesa 3.1 %, libqalculate 2.5 %, fontconfig 1.0 %; by thread: main 76 %, render thread 13 %, QML thread 10 %; apart from the loader no symbol above 1.3 %. No hot spot; item closed as "at the floor". Tables in the wiki.

- Tried and without effect: transparent huge pages `always` → `madvise` (the profile's kernel share is mostly page clearing): calculator 7.3 s / 6.2 s CPU, Settings 5.0 / 4.5-4.6, Koko 4.8 / 4.6 warm in both settings, memory the same. Left at `always`.
- **Roadmap 3.6, package updates:** `tools/phone-update.sh` - shows pending upgrades; `--apply` upgrades the ordinary ones and holds back a "sensitive" list (Mesa, KWin, Plasma, Qt, SDDM, PipeWire, libcamera, musl, BusyBox, OpenRC, udev, D-Bus, NetworkManager, OpenSSH, firmware) unless `--include-sensitive`; installed versions are recorded on the phone first, the health check runs after. Used once: `ca-certificates-bundle`, `alpine-release` 3.24.0 → 3.24.2, `libapk`, `apk-tools` 3.0.6 → 3.0.8; health check clean. No package rollback exists and none is claimed.

- GPU memory by process (panfrost fdinfo): 158 MiB resident in total - plasmashell 66, the on-screen keyboard 45 (roadmap 3.4 spoke of 240 MB at start; that was address space, the keyboard's "total" still reads 534 MiB), Xwayland 24, KWin 24. Nothing to trim. The session's side processes (Xwayland, tray and menu proxies, online-accounts daemons) hold 1-10 MiB each of real memory; left alone.
- Final check after a normal reboot with everything of today installed: `tools/phone-health.sh` all `ok`, **battery 100 %**, clock right before Wi-Fi came up. `ui-frame-bench.sh`, second run (the first, five minutes after boot, was lower): top panel 55 per second (90 % at 50-60), application drawer 34, home pages 43 - the same as on 2026-10-10 (52-54, 33, 42). No regression from the new modules or the helper.

- **Optional charge limit** in the battery helper (roadmap 2.3's last point): `charge_limit=NN` (50-99) in `/etc/j701f-battery.conf` stops charging at NN % and resumes at NN-5; no file, no limit (none is installed). The two reasons for switching charging off (temperature, limit) now go through one place, and charging comes back when neither holds. Tests: 22 cases. On the phone with a temporary file and limit 80 at 100 %: "inhibit-charge", "Not charging", -1.5 mA; set back to `auto` and the normal helper started again. My own slip on the way: a `pkill -f` whose pattern also matched the command line it was sent in ended the SSH session before anything ran - the known trap; the test went through a script file after that.

- Wiki: the journey part ended at chapter 8 (sound). New **chapter 9, "A battery number you can believe"** (EN/TR, in the navigation): today's battery work told as a story - the number that did not add up, why the gauge drifts, the second opinion from the resting voltage, temperature through an overlay instead of a new image, the charging table, and what to take from it. The lessons page has three new sections (a number nobody questions; a fix that does not survive a second edit; small traps met again). **Chapter 10, "A recovery of our own"** followed (EN/TR): why the vendor fallback had to go, what the recovery is made of, the owner's rule that shaped it, the trials, the order in which the safety net was replaced; written from the verified reference page. **Chapter 11, "A first camera"** as well (the question that made it possible - skip the image processor -, the five milestones, the two mistakes, the owner's verdict, where it stands; camera work itself stays paused). The camera reference page's status line said the owner had not used it yet; corrected. **Chapter 12, "The real display driver"** closes the gap (what the firmware framebuffer could not do, the chain, the RAM-only method with the watchdog and its rehearsal, the three faults, from trial to daily path, the sticky stamp). The display reference page still opened with "the phone currently uses simpledrm"; it now opens with a status box, in both languages. The chapters are out of chronological order (9 battery, 10 recovery, 11 camera, 12 display) and say so.

- More stale statements found while writing the chapters and corrected in both languages: the userspace page said KWin presents through `simpledrm` (checked on the phone: KWin holds `card0` = `exynos-drm` and both render nodes) and that video in Angelfish does not work (the owner watched YouTube in it on 2026-10-10; his two notes, short sound drop-outs and an occasional flicker, are now on the page as open); the "vendor kernel in RECOVERY" rough edge.

- New wiki page **"Using the phone"** (EN/TR, second in the navigation): what the person holding the phone needs - key combinations for the recovery and for the display fallback, files over USB and the SD card, battery helper, charge limit and stopping the charge, flashlight, camera, browser, backup / health check / updates / kernel image, and what the phone cannot do. Every statement taken from the reference pages; the wall-charger current is marked as not yet tried. Kernel page: the "which kernel is where" table still had the vendor kernel in `RECOVERY`; corrected.

- **Plasma's flashlight tile works** - an open point since the flashlight was written ("has not been checked"). Its plug-in enumerates LEDs named `*:torch` or `*:flash` (strings in `libflashlightplugin.so`), so it finds `white:flash` and not `white:front-flash`; it writes through the KAuth helper `org.kde.plasma.mobileshell.flashlighthelper`, whose polkit action allows active and inactive sessions without a password. Tried with injected taps on the tile (fourth in the quick settings; screenshot `build/screenshots/drawer-flash.png`): brightness 0 → 6 with the chip's enable register at 0x30, second tap → 0 and 0x00. Light only, no sound.

- **The desktop could not vibrate: feedbackd was not installed.** Found in the session log (`feedbackd vibration failed`, raised by my own injected taps on the quick-settings tile). Plasma Mobile sends haptic requests to feedbackd over D-Bus; the motor driver (`regulator-haptic`, event2) had been loaded for days with nothing using it. `apk add feedbackd feedbackd-device-themes`; its udev rule lists `regulator-haptic` (uaccess, `FEEDBACKD_TYPE=vibra`; one `udevadm trigger` for the device); the session user can open the device. Test: `fbcli -E message-new-instant` with the profile on `quiet` - the regulator summary showed `VDD_MOTOR_3.3` going from 0 to 1 users during the event. Then Plasma's own path: two injected taps on a quick-settings tile, motor supply seen at 1 again, no new failure lines in the session log. `tools/phone-health.sh` now also checks that the service is installed and on the `quiet` profile.
- **A sound-rule near miss, recorded plainly.** My first test event was `button-pressed` while feedbackd was still on its default profile `full`, in which that event also asks for a sound sample of the same name. No such sample exists in the installed sound themes (`/usr/share/sounds`: only `freedesktop`, which has none by that name), so nothing can have been played - but I had not checked that before sending the event. The profile was set to `quiet` (vibration and LED feedback only, no sounds) immediately afterwards and stays there; later tests check for it first. Lesson: a "haptic" daemon is also a sound daemon; read its theme before the first event.

## Modem, first look (2026-10-13 evening; owner: "start coding the modem, then a test application with an interface"; no SIM card in the phone)

- What the hardware is, from the factory device tree: an integrated Samsung Shannon 315 modem (`mif,name = "ss315ap"`), talked to over **shared memory** (`shmem@F0000000`, a 4 MiB IPC area at offset 0x07400000 of the modem's memory, which lies above the phone's own RAM) and a **mailbox** for interrupts in both directions (`mcu_ipc@10500000`, SPI 369). Power, reset and start are bits of a PMU register that only the secure monitor may touch. Nineteen logical channels (boot, ramdump, IPC "FMT", RFS, eight network interfaces, ...). Mainline Linux has no driver for any of it.
- Vendor sources fetched for reference (`build/kernel/vendor-modem-reference/`, same tree and commit as the others, GPL-2.0, not in the repository): `drivers/misc/modem_v1/` (link device over shared memory, I/O devices, SS310AP control, SIPC5 framing), `drivers/misc/mcu_ipc/` (mailbox, shared-memory layout), `drivers/soc/samsung/pmu-cp.c` (power and reset through SMC 0x82000700).
- **`tools/kmod/j701f_modem_probe.c`**, a look-only module. Through the secure monitor's read call: `CP_CTRL` = **0xb in both views: PWRON and START are set** - the boot loader leaves the modem powered and started. Whether it is alive and waiting, or sitting in its boot ROM, is the next question (the shared memory will say).
- **My mistake:** the same module then read the PMU's CP registers directly. They are secure-only - which is exactly why the vendor goes through the monitor - and the first read raised a synchronous external abort: an oops in `insmod`, module stuck half-loaded. The kernel carried on; the phone was restarted normally straight away and `tools/phone-health.sh` is clean (no oops in the new boot). The direct reads have been removed from the module.
- Partition sizes only (nothing read from them): `RADIO` 88 MiB (the modem's firmware), `CP_DEBUG` 5 MiB, `CPEFS` 8 MiB, `EFS` 20 MiB.
- **A decision that is the owner's.** On Android the modem gets its calibration and identity (the NV data) from files in `EFS`, and writes them back, through the "RFS" channel. The standing rules of this project are: never read EFS, never write EFS or the modem partitions. Without NV data the modem can probably be started and questioned, but will not behave as a calibrated radio; with it, the project would be reading EFS. Nothing of that kind is done until the owner says which way.

- Owner, in between: "why does this phone keep showing up on the computer as a wired connection, is that still needed?" No: it is the gadget's USB network function (`ncm.usb0`, 172.16.42.1) from the stages before Wi-Fi; no tool uses it. `system/usb-mtp/start.sh` now removes it from the gadget configuration while the gadget is off the bus for adding MTP (kept if `/etc/j701f-usb-net` exists). Applied live as well: the computer now sees two functions, the serial port (`/dev/ttyACM0`) and MTP (claimed by the desktop's file manager at once). After a live re-bind uMTP-Responder had to be restarted; at boot everything happens in one step.
- **EFS decision and backup.** The owner asked whether a stock ROM would repair a damaged EFS (no: EFS is this phone's identity and calibration, not part of any firmware) and then said: take a backup image and work with it, it can be written back from the computer. Raw copies of `EFS`, `CPEFS`, `m9kefs1-3` are in `build/backups/efs-20261013/` (outside the repository, mode 600), each hashed on the phone before and after the copy and on the computer: identical. Stance recorded in memory: serve the modem from a copy and keep its writes in RAM; write the real EFS only if unavoidable and after saying so.
- Modem, continued: the shared IPC area (0xB7400000, read through `/dev/mem`) holds uninitialised memory - no magic value, noise in every page - so the modem is not running a link: it has to be booted from scratch. The modem's memory is 0xB0000000 + 120 MiB, already reserved by the mainline device tree (`modem-if@b0000000`, and `gnss-if`). The mailbox registers read as zeros without a fault. `RADIO` starts with a table of contents: `BOOT` 5.8 KiB for modem address 0x40000000, `MAIN` 37 MiB for 0x40010000, `NV` 1 MiB for 0x44900000 (not in the partition: it comes from EFS), `OFFSET`. No open replacement for Samsung's boot daemon (`cbd`) was found; the vendor's `cbd` and `libsec-ril.so` were copied from the untouched Android `SYSTEM` partition (mounted read-only, no journal replay) to `build/kernel/vendor-modem-reference/android-bin/` for interoperability analysis - proprietary, never in the repository.

## Phone started in the recovery after a restart (2026-10-26)

Owner: "when I restart the phone it comes up in recovery mode, not normal mode". A restart through `loginctl reboot` (the path Plasma takes) came straight back to the installed system in 31 seconds, so the restart path is fine. The cause is the remote-safety net `/sbin/j701f-netguard` from 2026-10-09: when the installed system has no Wi-Fi address 300 s after boot it restarts into the recovery - meant for untried kernels with nobody near the phone; the recovery then boots the system again after 240 s, and away from the known Wi-Fi this repeats. Its log shows it firing, the last time on 2026-10-14 10:05. Turned off with its own switch, `/etc/j701f-netguard-off` (nothing removed; deleting the file re-arms it). Repository script, boot-chain and userspace pages (EN/TR) say so. The other way into the recovery from the initramfs - root filesystem not mountable after 90 s - stays: that one is a real fault.

## Clean-up and first public repository (2026-10-26)

Owner: "clean up, make the project professional, and share it on GitHub once you think it is ready". His choices: account Burak-GGM, public, GPL-2.0-only, the assistants' coordination files and home-network details stay out.

- The project folder had an empty `.git`: there was no version history at all. A repository was created with one first commit; before that every file that git would take was checked for firmware, binaries, keys, passwords, IMEI/serial numbers and personal paths. No binary file is tracked (416 files, 2.7 MB).
- Kept out by `.gitignore` in addition to the earlier list: `docs/coordination/` (locks, board and messages of the two assistants), `tools/reference/` (vendor source snapshots, fetchable from the URLs in `docs/third-party.md`), `.phone-ip`, tool caches and the assistants' empty settings folders. A stray 9.6 MB camera frame named `info:` in the root was moved to `build/stray/`.
- The phone's address is no longer written into the tools: shell and Python tools read `J701F_PHONE_IP`, else the one-line file `.phone-ip` in the repository root (ignored by git), else `j701f.local`. `run-boot-update.sh` takes its subnet from the same file. The SSH key path in five Python tools is `~/.ssh/id_ed25519` instead of an absolute home path. IP addresses in the notes and tests now use `192.168.1.0/24`; the router's model name was removed from `docs/wifi.md`.
- New `README.md` (status, layout, building, what is not in the repository, licence); the old one, which described stage 1, is `docs/stage1-recovery.md`. New `docs/README.md` sorts the notes into current and historical. `LICENSE` is the GPL-2.0 text.
- `tests/test_dsim7870_porches.py` failed on the host's clang 23 (a new warning, "set but not used" global, on the mock's board variables in the unpatched build, turned into an error by `-Werror`); the test now switches that warning off. The whole suite passes again.
- In a fresh clone (no `build/`, `extracted/` or user-supplied images) seven tests failed on missing files; `test_sboot_stub`, `test_recovery` and four tests in `test_diagnostics` now skip themselves when those inputs are absent. Fresh clone: 259 tests, 82 skipped, all others pass, also under Python 3.12. `.github/workflows/ci.yml` runs the tests and a strict wiki build on every push.
- The first CI run failed two real-terminal tests: on Ubuntu `/bin/sh` is dash, which takes the carriage return that wakes getty as part of the command (reproduced in an `ubuntu:24.04` container). They now run under bash, which edits lines like the phone's BusyBox ash; the second run passed.
- Repository: https://github.com/Burak-GGM/j701f-linux (public). Commits use the account's GitHub no-reply address.
- Owner: publish the wiki on GitHub Pages, deployed from CI. The `checks` workflow now uploads the strict wiki build and a `pages` job publishes it from `main` once the tests and the wiki build pass; Pages is set to the workflow source. Site: https://burak-ggm.github.io/j701f-linux/ (`site_url` set in `mkdocs.yml`).

## Two fixes prepared for mainline, not sent (2026-10-26)

Owner: prepare the `btbcm` and `s5p-mfc` patches in kernel form locally (checkpatch, get_maintainer, cover letter draft); send nothing.

- Base: a shallow clone of mainline at `d135ab453a74` (7.4 merge window) in `build/upstream/linux`, branch `j701f-upstream`. Both bugs are still there; the files are identical in `bluetooth-next` and in `media-committers` `next`. Web searches found no earlier patch for either.
- `btbcm`: the address list in mainline has grown (BCM4384B0) and has a comment per address; the patch adds `BDADDR_BCM43430A1_PATCHED` with its own comment line. Re-checked on the phone: the `brcm/BCM43430A1.hcd` it loads is byte-identical to linux-firmware's file ("BCM43438A1 37.4MHz Raspberry Pi 3-0141").
- `s5p-mfc`: the J701F comment was replaced by a neutral one. The H.264-only check came with `f96f3cfa0bb8` ("[media] s5p-mfc: Update MFC v4l2 driver to support MFC6.x", 2012; confirmed through the GitHub API, the original 2011 driver had no such check): `Fixes:` tag and `Cc: stable`, as the media maintainer profile asks for fixes. `head_processed` is read in one place only (`s5p_mfc_handle_init_buffers`), and the block is on the decoder path only.
- The kernel's rules for AI-assisted patches (`Documentation/process/coding-assistants.rst`): an AI agent must not add `Signed-off-by`. The patches therefore carry the owner as author but no sign-off; the commit messages state that the fix was found and written with Claude, and a `Notes:` section below `---` (instead of a cover letter, which a single patch does not take) says what was and was not tested.
- Checks: `W=1` arm64 build of both files without warnings; `checkpatch.pl --strict` with the sign-off added: btbcm clean, s5p-mfc one warning ("Unknown commit id") caused by the shallow clone. Recipients and send commands are in `kernel/upstream/README.md`.

## Release installer ZIP for TWRP and OrangeFox (2026-10-27)

Asked for by Codex (owner: "Codex's decision is my decision"); Codex owns the release builder, the host installer and the installer in the project's own recovery, Claude the flashable ZIP.

- `recovery/installer/update-binary` unpacks `installer.sh` and the project's pinned static AArch64 BusyBox 1.36.1 into `/tmp` and hands over; `tools/build-recovery-zip.py` builds the ZIP, with the release beside it (`j701f-release/`) or inside it (`--embed`, below 4 GiB only: no ZIP64).
- Why its own BusyBox: the two recoveries looked at are OrangeFox R11.1 (`tools/OrangeFox-R11.1-Beta-j7velte.img.tar`, 64-bit BusyBox 1.22.1, `getevent` from toolbox) and TWRP 3.x for the J7 Nxt (`tools/TWRP RECOVERY For J7 Nxt.tar`, 32-bit BusyBox 1.22.1, no `getevent`). Both mount `/data` from `by-name/USERDATA` with `length=-20480` and bind `/sdcard` onto it; the SD card is `/sdcard1` (OrangeFox) or `/external_sd` (TWRP).
- Checks, all before writing: `androidboot.bootloader=J701F*`; `ro.product.device=j7velte` when the recovery sets it; `by-name/USERDATA` is `mmcblk0p24` with 23314432 sectors / 11936989184 bytes (re-read on the phone today, UUID `4ce26b55-...` matches); BOOT contains `bootcmd=j701f_ramboot` (present once in each of the 86 built BOOT images and in the phone's BOOT, `mmcblk0p10`), otherwise it refuses because erasing Android's data would leave nothing that starts; ZIP and release not on a mount of USERDATA; `release.json` matches sectors, bytes, UUID and `j7velte`; compressed SHA-256 and `gunzip -t`; Volume Up within 60 s, read from `/dev/input/event*` as 24-byte events.
- Then: unmount every mount of USERDATA (deepest first; refuses if MTP holds it), `gunzip | dd conv=fsync`, SHA-256 of the whole partition, UUID; `install.status` with PASS/FAIL and the log next to the release.
- `tests/test_recovery_zip.py`: 12 cases against a simulated phone with the shipped BusyBox under `qemu-aarch64`; all pass. Not run on the phone yet; Codex coordinates the first real installation.
- Codex's review of the ZIP (same day): the internal-storage check looked only at the literal ZIP path and at mount sources in `/proc/mounts`; a `/sdcard` symlink or an emulated/FUSE view of internal storage would have slipped through, and the ZIP's own source could have been overwritten while writing. Now an allowlist: the ZIP and each release file are resolved with `readlink -f`, their filesystem's device number (`stat %d`) is looked up in `/sys/dev/block`, and the disk's `device/type` must be `SD`; USERDATA's mounts are found by major:minor (`/sys/class/block/mmcblk0p24/dev`) in `/proc/self/mountinfo`. Four new host tests (link from SD into internal storage for the ZIP and for the payload, non-SD storage, a USERDATA mount found only by major:minor); "SD" and "internal storage" are two real filesystems (`/tmp` and `/dev/shm`) so their device numbers really differ. 16 tests pass.
- Read-back after writing: the SHA-256 of USERDATA was taken straight after `dd`, so it could come from the page cache the write had just filled rather than from the eMMC. The ZIP now runs `blockdev --flushbufs` and drops the caches before reading back (found while reviewing Codex's installer, which has the same pattern).

## Codex's and Argon's installer work taken over and finished (2026-10-27)

Owner: "Codex's and agy's quotas are used up; carry on yourself and finish their half-done work". Codex had stopped at 04:13 holding the `phone` lock (taken for BOOT/RECOVERY backups before the DATA installer trial; USERDATA untouched); Argon had stopped while starting `scripts/first-install.py`.

- **Argon's `tools/prepare-first-install.py`:** the atomicity gap Codex had sent back twice was still there: `clear_published_outputs` deleted the targets in order with `manifest.json` last, so a directory in place of `recovery.img` stopped the run with the old manifest still marking the bundle prepared. The manifest is now removed first, then every target's type is checked before anything else is removed. New negative test with that exact case; it fails on Argon's version and passes now.
- **`scripts/first-install.py`** (Argon's unwritten piece): checks the Odin archives against their manifest, the release (hashes, `release.json`) and, with `--sd`, the microSD card mounted on the computer (its own removable vfat disk with room); prints Route A with the Odin commands written out; `--stage` copies release, recovery scripts and BOOT image to the card and reads each back. It contains no subprocess call at all (a test checks that). Ran against the real `build/first-install` and `build/release`: both pass.
- **Argon's plan** (`docs/installer-first-install-plan.md`): sections 3.2 and 7 brought up to date with Codex's last builder (native display only with pinned modules, uMTP-Responder only with `--umtprd-binary`, SD/MTP layer, empty password and lock settings, publickey-only SSH, per-step first-boot retries), the new script described, and "not run on hardware" stated.
- **Codex's installer:** the host tool sent `tr` and `rm` to the RAM recovery, which has neither (rec8's initramfs `bin/` was listed); without `tr` the wait for the recovery's Wi-Fi/MTP helpers saw no helper and went straight on, the case it was written to prevent. Both now go through `/bin/busybox`. `install-release-on-recovery.sh` called `uname` and `basename` without BusyBox (`basename` is missing in rec8); both through `$BB`. `scripts/install-release.sh` was Python: renamed `install-release.py`, references updated. The restore script read back without flushing the cache and had no after-write mount check, like the installer before Codex's fix: both added.
- **Tests for Codex's code** (it had none): `tests/test_install_release_on_recovery.py` runs the installer under `qemu-aarch64` with the recovery's BusyBox against a simulated phone (test-only path prefix, `J701F_INSTALLER_TEST`): dry run writes nothing; execute writes, reads back, checks the UUID, `install.status` PASS; a wrong UUID after writing gives FAIL; seven refusals before any write; a source linked off the SD card is refused. With the old `blkid -s UUID -o value` line the success test fails, so it guards that bug.
- Full suite passes; strict wiki build passes; tools page lists the new tools (EN/TR).

## First hardware run of the release installer: backup, reinstall, verified boot (2026-10-27)

Owner's yes: "first a full USERDATA backup to the SD card, then install the new release and verify it"; later "every kind of authority is yours, do not ask".

- Before: BOOT and RECOVERY on the phone equal Codex's host backups (`build/phone-slot-backups/`, BOOT `19215c50...`, RECOVERY `16774008...`; RECOVERY differs from the 10-10 record only by rec8's settings block). SD card 29 GB free.
- `scripts/install-release.py --execute --erase-userdata --backup-userdata --reboot` staged and verified the release on the SD card over SSH and rebooted into rec8. Then three faults that only the hardware could show, each fixed and resumed with the new `--from-recovery` (no second staging):
  1. The host never found the recovery's serial port: `find_ports()` accepted only the stage-1 console's USB serial number, the mainline initramfs/recovery gadget is `j701f-diagnostic`. The recovery had actually received the first command (its stay marker was set at 05:57) but the host gave up after 180 s.
  2. My own SD re-check in `--from-recovery` split each `sha256sum` line in two; the serial prompt stuck to the first line, so the payload looked different. Now a regular-expression search; the payload hash read by the recovery was `c9b37322...`, the release's.
  3. `mtp.sh down` run from the serial shell unbinds the USB gadget, which hangs up that same shell: the script died between "unbind" and "bind again", leaving the phone with no USB (06:12). Recovered over the recovery's Wi-Fi SSH as root in `/proc/1/root`: finished the teardown (unmount `/dev/ffs-mtp`, unlink and remove `ffs.mtp`) and bound `13600000.usb` again; USB was back at 06:16. The installer now runs `mtp.sh down` detached after 2 s, waits, and checks that the MTP function is gone and the UDC bound.
- Then everything ran as designed: in-recovery dry run (compressed and full decompressed SHA-256); backup job `preinstall-userdata-20261027-052652` on the SD card, 12 chunks, re-read and verified by the restore script's dry run (partition SHA-256 `316f9082...`); install job: 11936989184 bytes in 297 s (38.3 MB/s), cache flushed, full read-back `a29d50a5...` = release, UUID, `install.status` PASS; reboot; the host saw `BOOTED_RELEASE` (root on USERDATA, version `BURAK_ALPINE_0_1`, kernel 7.1).
- First boot of the new system, over USB: first-boot cache steps all `.ok`, 22 modules, native display "active (mode always)", uMTP-Responder running, SD card at `/media/sdcard`, `/etc/shadow` 640 root:shadow, kscreenlockerrc as designed, 1.2 GB free RAM.
- **Fault 4: no desktop.** SDDM showed its greeter: "Autologin failed!", PAM "You are required to change your password immediately (administrator enforced)". `provision.sh` writes `0` as the shadow last-change day, which pam_unix reads as "must change now". On the phone: the field set to today (20753), SDDM restarted, Plasma Mobile came up; a cold reboot then logged in by itself (desktop at 84 s uptime, native display). In the builder: empty last-change field (no ageing) in `add_user`, the same migration for reused roots, and `validate_root` refuses a `0` there. The release was rebuilt from the reused root with the fix.
- Not done: SSH key and Wi-Fi for the new system. Adding this computer's key and copying the home network's Wi-Fi profile over the serial shell was refused by the session's permission check as unauthorised persistence, so the phone is offline and reachable over USB only until the owner joins Wi-Fi in the settings and adds a key (or allows it). The previous system is in the SD backup above and can be restored with `restore-userdata-on-recovery.sh`.
- Afterwards: `tools/usb-run.py` runs a local script on the phone over the serial shell (sent base64 in short lines, framed output and exit status; host tests), and `tools/phone-health.sh --usb` uses it, for a phone without network or SSH key. It could not be tried on the phone: its USB connection dropped at 07:36:19 and did not come back, and with no Wi-Fi configured the phone was then unreachable. The README gained an installation section.

## Plasma Camera's empty videos, investigated off the phone (2026-10-27)

The phone was unreachable (USB gone since 07:36, no Wi-Fi on the fresh system), so Codex's request from 2026-10-26 was taken up on the computer. `tools/camera/qt-recorder-probe.cpp` mirrors Plasma Camera 2.1.1's recording code (read from its v2.1.1 source): `QImage` frames into `QVideoFrameInput`, `QMediaRecorder` MP4/H.264/MP3, timestamps per frame, frame rate 0, optional default microphone. It was cross-compiled with clang against the release root (`build/release/work/rootfs`) plus the headers of Alpine's `qt6-qtmultimedia-dev` 6.11.1 (fetched from the official v3.24 mirror into `build/third-party/qtmm-dev/`) and run under `qemu-aarch64` through the root's own musl loader.

- First guess wrong: QtMultimedia 6.11.1 never uses `*_v4l2m2m` encoders for recording (`qffmpegcodecstorage.cpp` disables them), so the untried MFC encoder is not involved; `libx264` is used with its default preset, Qt setting only `crf` (`qffmpegencoderoptions.cpp`). Second guess wrong too: the recorder reports `RecordingState` straight after initialisation (`qffmpegmediarecorder.cpp`), so there is no wait between it and Plasma Camera, which only starts sending frames in that state.
- The path works on the computer, with the host's PulseAudio microphone as well: valid MP4 with H.264 and MP3.
- From RGB frames Qt picks YUV 4:4:4: H.264 High 4:4:4 Predictive, unplayable on hardware decoders. YUV 4:2:0 frames give High profile and let 56 of 60 frames through at camera size instead of 18.
- Peak memory (VmHWM under qemu, 60 frames): 195 MB at 320x240, 485 MB at 960x540, 622 MB at 1280x720, 1.07 GB at 2072x1552, the rear camera's frame size and what the default "Auto" resolution records at; 4:2:0 frames do not lower it (x264 threads and lookahead dominate). With about 1.2 GB free on the phone before the camera's own buffers, swapping and an earlyoom kill of the camera application are the likely end: an empty or truncated file. Not yet confirmed on the phone; the test to do is on the camera wiki page.
- Camera-size frames recorded at the 540p preset: peak 403 MB instead of 1.07 GB, but 960x540 with square pixels, so the 4:3 picture is squeezed; not made the default.

## Roadmap 4.5: Linux 7.1 has reached end of life; the patch stack on 7.2.13 (2026-10-27)

kernel.org's `releases.json` lists mainline 7.3, stable 7.2.13 and the longterm series; 7.1 is gone, so `7.1.13` gets no more fixes. Trial on the computer only: `linux-7.2.13.tar.xz` from `cdn.kernel.org`, SHA-256 `08e7b0c4...` checked against `sha256sums.asc` (signature not verified, as for 7.1.13), unpacked in `build/kernel-7.2-trial/`, then the 31 patches in the build's order (`exynos7870-7.1/*.patch`, then `linux-*.patch`), each dry-run first; results in `build/kernel-7.2-trial/result.txt`:

- Community: 01-04 apply cleanly; **05 and 06 (`dw_mmc` DMA threshold option and the Exynos value) are already in 7.2.13** (they reverse-apply) and can leave the stack.
- Local: all 25 apply. With offsets or fuzz: `audio-exynos7870-lpass`, `dsim-j701f-timing-trial`, `dsim-pll-wait-fix`, `g3d-exynos7870-scaling`, `mip4-vdd-supply`, `zz-simpledrm-j701f-software-backlight`; the rest cleanly.
- Fuzzed hunks read back in the patched 7.2.13 tree: `dsim-pll-wait-fix` lands where it should (the PLL wait in `samsung_dsim_set_pll` reads `if (!ready)` together with the diagnostics patch; the IRQ handler services `PLL_STABLE` after the reset branch, about 35 lines further down than in 7.1); `g3d-exynos7870-scaling` adds `clk-exynos7870-g3d-park.o` once, next to `clk-exynos7870.o` (7.2 added `clk-artpec9` and `clk-acpm` to that Makefile); `mip4-vdd-supply` enables the supply and waits 300 ms in `mip4_probe` before `mip4_power_on`, as on 7.1; `audio-exynos7870-lpass` puts `exynos7870-lpass.o` (and the codec card's objects after it) right after `snd-soc-i2s.o`.
- **Built**: `defconfig` + `exynos7870.config` + `kernel/configs/mainline-bringup.config`, `olddefconfig` (2141 built-in, 745 modules), `make ARCH=arm64 LLVM=1 Image modules dtbs` in 1060 s, `Image` 27.5 MB. Every local driver compiled: GPU clock parking, CPU frequency, read-only TMU, LPASS, COD3026X codec and card, S2MU005 charger (module), DSIM, MFC, btbcm, MIP4, Panfrost shrinker. Two warnings, both from our `drm_sysfb_j701f_neon.c`: `<arm_neon.h>` brings the compiler's `stdint.h`, whose `UINTPTR_MAX`/`SIZE_MAX` clash with the kernel's `limits.h`.
- Not done yet: the project's own device tree and FIT/U-Boot packaging on 7.2, the out-of-tree modules (`tools/kmod`, display), `kernel/inputs.json` pins and the resolved-config hash (given to Codex), and any phone test.

## The fresh release "switches itself off" after 15 minutes: it suspends (2026-10-27)

Both times the new system had been up 15-17 minutes, USB went away and did not come back (07:20:54 boot, 07:36:19 gone; 10:15:13 boot, 10:32:25 gone, during Codex's camera check); the owner later "switched the phone on" again. A crash would have rebooted the phone (`panic=10`, watchdog), so it was asleep. The release's `provision.sh` installs `system/elogind-nosleep.conf` as `/etc/elogind/logind.conf.d/j701f-nosleep.conf`; its `[Sleep]` section is only read from `sleep.conf.d`, where the old system had it (`/etc/elogind/sleep.conf.d/10-j701f-nosleep.conf`, this log, 2026-10-08). So logind allowed suspend, PowerDevil's default suspends after 15 idle minutes, and on this phone only the clock alarm wakes it (the key wake-up was removed again), so it looked switched off. Fixed in `provision.sh`, in the reused-root migration and in `validate_root`; the wiki's userspace table had the wrong place too. The installed phone needs the same move (`usb-run.py` while it is awake) and the release a rebuild.
- Done on the phone at 168 s uptime over USB: the file moved to `sleep.conf.d`, logind's `CanSuspend` now answers `"no"`.
- Owner, the same morning: "the phone has switched itself off twice, USB contact or something you do, I don't know; you need not stop, I am at home and give you full authority — record this". Recorded. Plasma Mobile's first-start "Welcome" wizard appears on the fresh system; the owner goes through it on the phone (it also sets up Wi-Fi).

## The fresh release had no working Wi-Fi: root-owned D-Bus helper (2026-10-27)

While the owner went through Plasma Mobile's Welcome wizard, NetworkManager showed `wlan0` as "unavailable" and no `wpa_supplicant` ran; starting it through D-Bus gave `Spawn.ExecFailed ... Permission denied`. `/usr/libexec/dbus-daemon-launch-helper` was `4750 root:root`: with `apk --no-scripts` the `messagebus` group did not exist when the file was extracted, apk fell back to group root (its database even records `a:0:0:4750`), and the system bus, running as `messagebus`, could not execute it. Same cause: `/etc/polkit-1/rules.d` was `750 root:root`, unreadable for `polkitd`, so the project's `49-j701f.rules` and the default rules were ignored.

- On the phone over USB: both re-grouped (`messagebus`, `polkitd`), NetworkManager restarted: `wlan0` "disconnected", 12 networks in the scan; polkit restarted.
- In the builder: `provision.sh` and `refresh_release_scripts` set both, using the group numbers from the target's own `/etc/group` (the build container's names may differ); `validate_root` checks mode and group. Rebuilt from the reused root: PASS, helper `4750 0:101`, rules `750 0:107`, no-sleep file in `sleep.conf.d`.
- Systematic check for more of the same: the packages whose scripts create users or groups (dbus, its launch helper, polkit, rtkit, sddm, seatd, avahi, feedbackd, NetworkManager, PipeWire, libftdi1, shadow, wpa_supplicant, BlueZ, utmps; 188 packages with dependencies) installed natively, scripts included, in an x86_64 Alpine 3.24 container, and every path not owned by root:root listed. Only five: the launch helper and `polkit-1/rules.d` (fixed above), `/etc/shadow` (fixed earlier), `unix_chkpwd` (already right) and `/var/lib/sddm` (`2755 sddm:video`; the release had 755, now 2755 in `provision.sh`). Nothing else is hiding behind `--no-scripts` in these packages.

## The owner's first test of the fresh release: recents key, back key, battery icon, clock (2026-10-27)

The owner, testing on the phone: Home works, the recents and back touch keys do not, and the battery percentage shows in Settings but not at the top right. Checked over USB (`tools/usb-run.py`, screenshots through `~/.local/bin/kwin-screenshot`, keys and taps written to the evdev nodes with `tools/inject-key.py` and `tools/inject-swipe.py`).

- **Recents.** The hwdb mapping is applied (`KEYBOARD_KEY_00=prog1` on `tm2-touchkey`, which reports codes 148 and 158), but the release's `kglobalshortcutsrc` had `Mobile Task Switcher=Meta+C,none,...`: the old system's binding to `Launch (1)` lived only in that user's own file. Written on the phone with `kwriteconfig6` as the user, phone rebooted: `KEY_PROG1` now opens the task switcher, a second press closes it. In the release: `system/release/kglobalshortcutsrc`, installed by `provision.sh` and `refresh_release_scripts`, checked by `validate_root`.
- **Back.** `KEY_BACK` reaches the session and works: it closes the app drawer, and in Settings it goes from the Bluetooth page back to the list. Kirigami apps (`StandardKey.Back`) and the Folio app drawer and folders handle it; on the home screen and on an app's first page there is nothing to go back to, so it does nothing there. Whether the physical key produces events is still open: a 15-minute logger on `event1`/`event3` (`/tmp/keylog.txt`) recorded three quick press/release pairs of code 148 (recents) at 11:21:40 while the owner was testing, and no 158 at all. Either back was not pressed then, or the chip reports the back key in the recents bit; to settle with the owner pressing back alone while the logger runs.
- **Battery icon.** UPower and the fuel gauge were fine; the icon is present after the reboot (99-100 %). `upowerd` has no OpenRC service and is started through D-Bus activation, which needs the launch helper broken on this system's first boot (see the Wi-Fi entry): Plasma's battery model started with no batteries and does not notice UPower appearing later, when Settings started it after the helper was fixed. After the reboot `upowerd` starts at 25 s, just before `plasmashell`; nothing more to fix.
- **Clock one hour behind.** `/etc/localtime` was missing in the release too, so the phone showed UTC. Linked on the phone to the computer's zone and `plasmashell --replace` run so the status bar re-reads it (11:20 shown). **Do not do that again:** a `plasmashell` started from the USB root shell through `su` is outside the logind session, and polkit then refused its KAuth requests (flashlight: `kauth returned an error code: 4`, authorisation denied); a reboot put things right. `tools/build-release.py` gained `--timezone`, defaulting to the build computer's zone; it sets `/etc/localtime` and `/etc/timezone` and records the zone in `release.json`.
- **Flashlight.** After the reboot the quick-settings flashlight works (tile tapped by injected touches: `white:flash` brightness 6, then 0). Plasma Mobile 6.6 writes the LED through a KAuth helper (`org.kde.plasma.mobileshell.flashlighthelper`, polkit `allow_active`), so it depends on the D-Bus launch helper and polkit rules fixed this morning; it only looks for `*:flash` and `*:torch` and so only drives the rear LED. The flash inside the camera application is part of the camera task given to Codex (crash on camera switch, lag, blur).
- **Front flash app** (the owner's request: the old systems could switch the front flash from a terminal, Plasma has no button for it): `system/flashlight/j701f-front-flash` toggles `white:front-flash` (or `on`/`off`), with a launcher "Front flash" / "Ön flaş"; the brightness file is already user-writable through `system/flashlight-udev.rules`. Installed in `provision.sh` and `refresh_release_scripts`; on the phone, run as the user: brightness 2 (max), then 0.
- **Flashlight app instead of the launcher.** The owner: the toggle works but feels very sluggish (Plasma Mobile shows its opening animation for a launcher that never opens a window). Replaced by a small app, `system/flashlight/j701f-flashlight` (Python and GTK 4, both already on the phone; launcher `org.j701f.flashlight.desktop`, "Flashlight" / "Fener", matching the Wayland app id): two large round buttons, rear and front, showing on/off; it follows changes from the quick-settings tile once a second and switches both LEDs off when the window closes. Tried first in QML through `qmlscene`: reading the brightness files works, but `XMLHttpRequest` PUT never reaches sysfs. GTK's GL renderer shows no window here (Panfrost: "Failed to choose spill node"), so the app uses the Cairo renderer. On the phone, tapped by injected touches: front 2, rear 6, both 0 again. `j701f-front-flash` stays for the terminal; its launcher is removed.
- **Camera: crash on switching, lag.** Given to Codex at 11:28; its quota ended before it reported a finding. Cause found afterwards: the release never installed `system/camera/camera-env.sh` (`~/.config/plasma-workspace/env/j701f-camera.sh`, `LIBCAMERA_SOFTISP_MODE=cpu`), so libcamera's software image processing ran on the GPU, the path that aborted in about one start in three on this phone (2026-10-10). Installed on the phone, rebooted: the session has the variable, the debayer runs on the CPU at 50 ms per frame as before, and three camera switches in a row in Plasma Camera left the same process running with a picture from the front camera. In the release: `provision.sh`, `refresh_release_scripts`, checked by `validate_root`. Not changed: the picture stays soft (no autofocus, a quarter of the sensor's resolution, no sensor tuning; wiki camera page), and Plasma Camera's own flash control does nothing, since the pipeline drives no flash while taking a picture; the flash the owner had working before is the flashlight, which works.
- **Why the rear picture is soft: the focus motor is on a bus we never enabled.** The camera device tree says "DW9807 actuator at 0x18, not used yet" and assumed the sensor's bus. Checked on the phone while the rear camera streamed (`cam -c 1`, `afvdd` gpd1-1 high): nothing answers on `hsi2c@138a0000` but the sensor (`i2cdetect -r 7`: only 0x2d). The factory device tree (`build/kernel/j701f-live.dtb`) has the actuator on a different controller, **`hsi2c@138B0000`, 7-bit address 0x0c** (`samsung,exynos5-fimc-is-actuator-dw9807`; the node name's "@18" is the 8-bit form), together with the **rear EEPROM at 0x58** (`samsung,rear-eeprom-i2c`, which holds the module's calibration, autofocus range included). That controller is not enabled in the project's device tree, so the lens stays wherever its spring holds it. Next step: enable `hsi2c@138b0000` with its pins, let `j701f_camera` (which already switches `afvdd`) write a fixed lens position through a second I2C client after power-up (a value found by a sweep; DW9807: register 0x02 = 0 to wake, 0x03/0x04 = 10-bit position), and later read the EEPROM for the calibrated range; this needs a new BOOT image. Plasma Camera's flash button does nothing because libcamera's simple pipeline drives no flash; not attempted.

## The rear focus motor driven, without a new BOOT image (2026-10-28)

- **Bus.** `tools/kmod/j701f_camaf.c` applies `j701f-camaf-overlay.dtso` at load time: it only sets `status = "okay"` (and 400 kHz) on `/soc@0/i2c@138b0000`, which mainline describes complete with its pins (gpf1-0/1, the same as the factory tree) but leaves disabled. On the phone: `overlay result=0`, a new bus `i2c-9`. Loaded by `~/j701f/modules/camera/load.sh` before the camera driver, optionally. Modules built against the 7.1.13 tree configured with the phone's own `/proc/config.gz` (the tree had been wiped from `/tmp`; the host compiler is now clang 23, the phone's kernel was built with 22, and `MODVERSIONS` is off; the configuration otherwise identical, including the options added to the fragment after `cam5`).
- **Motor and EEPROM.** While the rear camera streams (`afvdd` high), the DW9807 at 0x0c answers and takes positions (read back: 0x03/0x04 hold what was written; register 0 reads 0xf9). The rear EEPROM at 0x58 starts with a section table (0x100, 0x200, 0x300), holds the module name `T13LLIA00PM`, `J7`, and at 0x100 and 0x108 two little-endian lens codes, **506 and 727**, taken here as the infinity and macro calibration.
- **Driver.** `j701f_camera.c` gained the parameter `focus` (`/sys/module/j701f_camera/parameters/focus`): `-2` (default) = a fixed position a tenth of the way from the infinity code towards macro (528 on this phone, about 1-2 m), read once from the EEPROM; `0..1023` by hand, applied at once while streaming; `-1` = lens not driven. The lens is moved in steps of 16 with a millisecond between them and lowered the same way before the motor's power is cut.
- **Clicks.** The first sweep jumped the lens between positions and its power was cut with the lens up: the owner heard a ticking from the phone ("pıt pıt"). That was the voice-coil motor; the steps and the lowering are the answer to it.
- **Which code is infinity: from the vendor source.** The test scenes on the phone were dark (rear camera covered: mean level 36 of 255 with or without the rear LED), so sharpness could not decide it. The vendor kernel (`samsungexynos7870/android_kernel_samsung_exynos7870`, `fimc-is2/vendor/mcd/fimc-is-eeprom-rear-3l2_v00*.h`) names 0x0100 `EEPROM_AF_CAL_PAN_ADDR` (infinity) and 0x0108 `EEPROM_AF_CAL_MACRO_ADDR`; this module's EEPROM matches the v001 layout (header `T13LLIA00PM` at 0x20 and 0x1E0, map version `V001` at 0x30). Its DW9807 driver writes these 10-bit codes unscaled (`fimc-is-device-dw9807.c`, first 100 then 170 at start). So 506 is infinity and the default 528 sits just in front of it, as intended. Still to see on a real, lit picture.
- **Flash in the camera application.** Plasma Camera (current `master` at invent.kde.org) has no flash code at all, only unused flash icons in its resources, and the phone's camera screen shows no flash button (timer, shutter, switch, settings). So there is nothing there to fix; the flash that worked before is the flashlight (quick-settings tile, "Flashlight" app), which works.
- **Focus on a real picture: not yet seen.** Every sweep so far, with `cam` frames and with Plasma Camera's own preview (the screenshot's green-channel gradient over the preview, positions 400-760), was flat, and both showed the same dark, plain picture (mean 36-37 of 255, one thin diagonal edge): with the phone lying on its back on the desk the rear camera looks at the desk surface from a few millimetres, and the rear LED does not change that. The one time the preview showed a scene (the owner's desk, mouse and cables at about 0.3-1 m, looking acceptably sharp at the default 528) the owner was holding the phone and closed the application during the sweep. A sweep needs the phone held or propped up facing a scene.

## The back key: works, but not the way Android's does (2026-10-28)

- A key logger on `event1`/`event3` while the owner tested: Home (125), recents (148) and **more than 25 presses of back (158)** at 13:49-13:50, each with press and release. The key and its driver work.
- The owner still found it "not working": in Plasma, Back only goes back a page inside an application (Settings sub-page to list, app drawer closed); on an application's first page (Plasma Camera) and on the home screen there is nothing to go back to, and unlike Android it never leaves the application. Plasma Mobile's own navigation bar has no back button at all (task switcher, home, close).
- `system/session/backkey/j701f-backkey`: listens on the touch key device (the user is in `input`, nothing is grabbed); a short press stays the application's Back, **holding it half a second closes the active application** through KWin's `Window Close` shortcut. Tested on the phone with injected presses: Settings stayed open after a 0.1 s press and closed after a 0.8 s press. Running on the phone from `/tmp` for this session only; installing its autostart entry (`j701f-backkey.desktop`) on the phone was refused by the permission check as persistence, and a new session service needs the owner's yes anyway, so it is not in `provision.sh` yet.

<!-- CLAUDE-END 2026-10-09 -->

<!-- CODEX-BEGIN 2026-10-28 -->
## Camera video recording checked on the phone (2026-10-28)

With `LIBCAMERA_SOFTISP_MODE=cpu` active, the Plasma Camera 2.1.1 process was tested over USB serial. The output sink was verified muted before every test. No audio was played. Three short captures were made through injected touchscreen taps; `ffprobe` read the files without decoding or playback:

| Camera / setting | Result | Memory observation |
| --- | --- | --- |
| Front, Auto | Valid 9.33 s MP4, 1276 × 960 H.264 + MP3, 3.6 MB | During recording camera RSS reached about 710 MB; it survived and finalized the file. |
| Rear, Auto | Invalid 48-byte MP4 (`moov atom not found`); camera process later disappeared | In six seconds `MemAvailable` fell from 643 to 95 MB and `SwapFree` from 889 to 647 MB. RSS reached at least 788 MB before the process exited. No earlyoom or kernel OOM line was found, so the precise terminating signal is unproven. |
| Rear, 540p | Valid 6.92 s MP4, 960 × 540 H.264 + MP3, 1.47 MB | Camera remained alive; peak RSS (`VmHWM`) 491 MB. |

This confirms that lower encoder resolution avoids the observed rear-camera failure, although the 540p preset distorts the 4:3 preview to 16:9. It is not made the default. A proper recorder fix needs aspect-preserving downscaling and YUV 4:2:0 input; both are future work. The temporary `plasmacamerarc` edit was restored, the trial files removed, and the phone lock released. The CPU ISP release fix, autofocus-bus finding, and separate flashlight app are in Claude's entries above.
<!-- CODEX-END 2026-10-28 -->

<!-- CODEX-BEGIN 2026-10-28 INSTALLER -->
## Host graphical installer (2026-10-28)

Added `tools/installer-gui.py` as a Tk front end to the existing guarded scripts. Its three pages wrap `scripts/install-release.py` (including `--backup-userdata` and `--from-recovery`), `scripts/first-install.py`, and `tools/build-recovery-zip.py`. The default button executes only the first two scripts' dry-run mode; the ZIP builder lacks a dry-run switch, so the GUI checks its local BusyBox/scripts and optional embedded release instead of creating a file. A one-step write switch resets after each operation. USERDATA erase, optional reboot, backup omission, SD staging, and replacement of an existing ZIP each have operation-specific confirmation; phone erase and SD/ZIP replacement require exact typed phrases. Release execution requires exactly one `/dev/ttyACM*` whose USB parent serial is `j701f-diagnostic` (found via sysfs). All subprocesses use argv arrays, no shell, and stream output in a worker thread so the window stays responsive. The window refuses to close while a release job is in progress because a detached recovery write may continue after host disconnect.

The GUI itself has made no phone or SD writes. Eight host unit tests cover command boundaries, serial filtering, dry-run flags and confirmation behavior; a Tk window initialization smoke test passed on the host. It deliberately does not automate Odin, BOOT/RECOVERY flashing, or running the TWRP ZIP. Public usage and caveats are in `wiki/reference/installation.md` and `.tr.md`.
<!-- CODEX-END 2026-10-28 INSTALLER -->
