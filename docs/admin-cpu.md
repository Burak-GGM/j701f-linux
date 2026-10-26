# Administrator access and CPU diagnosis — 2026-10-07

The SSH user is UID 1000 and initially had no privilege elevation tool. This explains apk and sysfs permission errors. `/bin/su` is a link to the non-SUID BusyBox binary; adding a setuid bit to the entire BusyBox binary is not the fix.

The user explicitly approved unrestricted passwordless sudo after the initial automatic approval review rejected that broad grant without explicit authorization. The sudo package is installed, and the reviewed rule from `system/sudoers` is installed at `/etc/sudoers.d/j701f`, root-owned mode 0440. `visudo -cf /etc/sudoers` passed; `sudo -n id` through SSH returned UID 0. SSH is still key-only and the root account cannot log in directly over SSH.

Use:

```sh
sudo -i
sudo apk add neovim git gcc musl-dev make
```

The requested packages were already installed through the USB root console. Verified versions: Neovim 0.12.2, Git 2.54.0, GCC 15.2.0 and GNU Make 4.4.1; musl-dev is installed. Report: `build/phone-sudo-packages-test.txt`. The grant and packages are live DATA provisioning, not included in existing flash images.

## Four online CPUs are a separate kernel issue

The kernel recognizes eight possible/present CPUs (0–7), with four online (0–3). Its Exynos hotplug governor is enabled and the measured policy initially allows 4–8 cores. A six-second workload with eight runnable processes did not bring CPU4 online. Live kernel messages show:

```
zswap: can't allocate compressor transform
_cpu_up: attempt to bring up CPU 4 failed
cpu_hotplug_in: Failed to hotplug in CPU4 with error -1
```

A root write to CPU4's online attribute did not activate it. The root shell accepted the write, but the online mask remained 0–3 and the hotplug failures continued. This is not resolved by fixing user permissions.

Both lz4 and lzo compressors are built in and registered with passed self-tests. zswap is enabled, uses lz4/zsmalloc, and its enabled/compressor attributes are read-only. No swap device is configured. Over 1.6 GiB MemAvailable was observed; this does not prove why crypto_alloc_comp fails.

The [related SIMPLE source](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/SIMPLE-V1.0-PERMISSIVE/mm/zswap.c) shows its CPU_UP_PREPARE notifier allocating a compression transform and returning NOTIFY_BAD on failure, which can veto CPU startup. That matches the observed failure sequence, but the source is not an attested exact match for the running binary, and the underlying crypto allocation error is not printed. The same code skips zswap initialization when booted with `zswap.enabled=0`.

The short load test triggered repeated CPU4 retries every 100 ms. Cleanup sets `/sys/devices/system/cpu/cpuhotplug/max_online_cpu` to 4 for this boot only, to keep the four currently working cores and stop that retry loop. No startup setting pins four cores permanently. A reboot resets this user cap. Root commands that request the extra cores remain subject to the unresolved kernel failure.

Reports for the initial diagnosis: `build/phone-admin-cpu-test.txt` and `build/phone-admin-summary.txt`.

## BOOT header trial and verified rollback

`tools/boot-cpu-trial.py` prepared a separate candidate with `zswap.enabled=0` in the primary Android BOOT header command-line field. The kernel, ramdisk, DTBH and every byte outside that field remained identical. A full 32 MiB live BOOT backup was saved on both laptop and phone and checked against the phone's SHA-256. Three unit tests cover preservation and refusal of an unexpected baseline or existing command line.

The guarded USB trial wrote only the first 2048-byte header and verified the full partition checksum. Normal Alpine boot, automatic Wi-Fi association and SSH login returned successfully. However, `zswap.enabled=0` did not appear in `/proc/cmdline`, and zswap remained enabled. This boot route did not pass the primary header argument through; the test therefore did not establish whether disabling zswap would fix hotplug.

All eight cores were online briefly early in boot, before the governor reduced the mask to 0–3. That is not evidence that subsequent hotplug works. The temporary four-core cap was reapplied for the GUI trial to avoid repeated CPU4 failures.

The original working BOOT header was restored from the phone backup. Full-partition read-back matched the original SHA-256 `0575c65837f1f993b46884dfa69e9ae54ae5d83aae50bcc02c8b97e3f4f3995c`. Reports are under `build/boot-cpu-trial/`, including `phone-reboot.txt` and `phone-rollback.txt`. The latter records `ORIGINAL_WORKING_BOOT_RESTORED_AND_VERIFIED`. Recovery was unchanged.

The backup is `build/backups/boot-before-cpu-trial.img` on the laptop and `/var/lib/j701f/boot-cpu-trial/boot-before.img` on the phone. A separate Odin restore archive is `build/boot-cpu-trial/BOOT-working-restore.tar`. The trial candidate is historical diagnostic output, not a CPU fix to flash again. Changing kernel built-in arguments/configuration requires a separate kernel milestone; the first GUI proceeds with four cores.
