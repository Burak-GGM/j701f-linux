# Tools and workflow

Everything in `tools/` runs on the development PC unless noted. The tools are deliberately strict: they pin inputs by hash, check results, and stop rather than guess.

## The everyday loop

```sh
# 0. Only when kernel sources, patches or configuration changed: compile the kernel
python3 tools/build-kernel.py panfrost --jobs 11

# 1. Build and verify an image (nothing touches the phone)
tools/build-mainline-image.sh NAME kernel/dts/exynos7870-j7velte-camera.dts "--allow-audio --allow-sd --allow-mfc"

# 2. Make sure it really produced an image
ls build/kernel/boot-update-NAME/boot-mainline.img

# 3. Install it and reboot the phone into it
tools/run-recovery-update.sh NAME
```

`NAME` is a short label for the stage (`gpufreq`, `audio4`, …). Each stage keeps its own directories under `build/kernel/`, so any earlier image can be installed again.

!!! warning "Check step 2"
    If the output of step 1 is piped through `tail` or `grep`, the shell reports the exit status of that last command, not of the build. Twice a failed build went unnoticed this way and the phone was sent off to restart for an update that did not exist.

!!! warning "Step 1 does not compile the kernel"
    `build-mainline-image.sh` packages whatever kernel was compiled last. After a patch change, skipping step 0 produces a perfectly valid image with the old kernel in it. That happened once: the image was installed and the "fix" was simply not there.

!!! note "After the computer restarts"
    The kernel work tree lives in `/tmp`, which is emptied by a restart of the computer. Step 0 rebuilds it and, because the build is reproducible, gives the same kernel build ID, so the modules already on the phone keep matching. Separately built modules (`tools/kmod/`, the charger, the display modules) additionally need `Module.symvers`, which step 0 produces only when asked: run it as `python3 tools/build-kernel.py panfrost --jobs 11 --modules` before building any of them (otherwise every kernel symbol is reported as undefined).

The device tree named in step 1 is the top of the chain (`camera.dts` includes all the others); an image built from an older file in the chain boots, but without what the later files add. Step 3 restarts the phone into the project's recovery (with `system/reboot-recovery.sh`, which shuts the filesystems down cleanly), has the recovery write and read back `BOOT`, and restarts into the new image; the recovery uses the same Wi-Fi address and host key as the system. `J701F_PHONE_IP=192.168.x.y` names another address. The older `run-boot-update.sh`, which went through the vendor system, refuses to run now that the vendor image is no longer in `RECOVERY`.

If the image currently in `BOOT` is not the one a prepared update expects (for example after going back to an older image), prepare the update again:

```sh
python3 tools/prepare-boot-update.py --handoff-dir build/kernel/handoff-NAME \
    --output-dir build/kernel/boot-update-NAME \
    --phone-dir /home/burak-alpine/j701f-boot-update-NAME
```

## Build tools

For modem development, `tools/modem-radio-toc.py` reads a local RADIO image's
512-byte table and checks section bounds. It does not extract firmware or
interact with the phone. `tools/modem/sipc5.py` checks bounded link frames;
`tools/modem/rfs.py` checks NV requests against a caller-supplied RAM image.
Neither opens a device or private file, and neither is a running modem service
([modem status](modem.md)).

| Tool | Purpose |
| --- | --- |
| `build-kernel.py` | Fetch, patch, configure and compile the kernel; pins source, patches and configuration by hash |
| `build-j701f-dtb.py` | Compile and verify the board device tree; `--allow-emmc`, `--allow-gpu`, `--allow-wifi`, `--allow-audio`, `--allow-sd` |
| `build-mainline-initramfs.py` | Build the initramfs with helpers and Wi-Fi firmware |
| `build-mainline-fit.py` | Bundle kernel, device tree and initramfs into a FIT image |
| `build-j701f-uboot.py` | Build the patched U-Boot with the FIT image embedded |
| `package-embedded-mainline-diagnostic.py` | Wrap U-Boot in the Android image S-BOOT accepts |
| `validate-embedded-ramboot-guards.py` | Check that the loader accepts good images and refuses 15 kinds of broken ones |
| `trace-j701f-uboot.py` | Run the loader in QEMU up to the jump into Linux |
| `build-mainline-image.sh` | All of the above in order, plus the unit tests and update preparation |
| `prepare-boot-update.py`, `run-boot-update.sh` | Prepare and carry out a guarded write to `BOOT` |
| `run-recovery-update.sh` | The same update through the project's own recovery instead of the vendor system: stage the image, reboot into the recovery, let its `flash-boot.sh` write and verify BOOT over SSH, reboot. The way to update BOOT since the recovery was installed (2026-10-10); `restore-vendor-recovery.sh` puts the vendor system back into RECOVERY (not run so far) |

## Release and installation tools

| Tool | Purpose |
| --- | --- |
| `build-release.py` | Build the USERDATA release: signed Alpine minirootfs, AArch64 packages, provisioning from `system/release/`, ext4 image with the fixed UUID, `userdata.ext4.gz`, two SHA-256 files and `release.json`. Docker required ([building a release](release-build.md)) |
| `scripts/install-release.py` | Reinstall a release on a phone already running this system: stage it on the SD card, reboot into the recovery, optional full USERDATA backup, write and read back ([installing a release](installation.md)) |
| `scripts/install-release-on-recovery.sh`, `recovery-install-job.sh`, `restore-userdata-on-recovery.sh` | The recovery side: guarded USERDATA write and full read-back, a detached job that survives a USB disconnect, restore of a backup |
| `build-recovery-zip.py` | The flashable ZIP for TWRP/OrangeFox ([graphical recovery](recovery.md)) |
| `prepare-first-install.py` | Single-member Odin archives of the BOOT and RECOVERY images for a phone still on stock Android, with every check the images must pass |
| `scripts/first-install.py` | Host side of the first installation: checks the archives, the release and the microSD card, prints the steps, `--stage` copies everything to the card. Never runs Odin or touches the phone |

Tests for all of them run against simulated phones under `qemu-aarch64` with the BusyBox the recovery uses; none of them has been run on the phone yet (2026-10-27).

## Talking to the phone

| Tool | Purpose |
| --- | --- |
| `usb-console.py` | Serial shell over USB (`/dev/ttyACM0`); works on both kernels and inside the initramfs |
| `usb-run.py` | Run a local shell script on the phone over the USB serial shell, as root, with its output and exit status; for a phone without network or SSH key (a fresh release, the recovery). `phone-health.sh --usb` runs the health check this way |
| SSH | `ssh burak-alpine@<phone address>`; the address is fixed on mainline because the MAC address is fixed. The host tools read it from `.phone-ip` in the repository root (one line, ignored by git) or from `J701F_PHONE_IP` |
| `i2c-peek.c` | Tiny static program to read or write one I²C register on the phone |
| `reboot-recovery-static.c` | Reboot into the `RECOVERY` slot |
| `kmod/j701f_pdinfo.c` | A tiny kernel module that prints the state of the four power domains — the safe alternative to dumping registers. With `off=NAME` / `on=NAME` it switches one domain |
| `kmod/j701f_cam0_off.c` | Switches the unused camera power domain off while loaded |

### Health check

`tools/phone-health.sh` logs in to the running phone and prints one line per thing that has silently gone wrong at least once in this project: which system is running, the kernel build ID, the display driver actually in use, the desktop, start-up guard stamps left behind, the frequency limits, the modules, the battery (including whether the percentage is believable for the measured voltage), the battery helper, battery temperature, clock and hardware clock, SD card, MTP, Wi-Fi, oopses in the kernel log, memory and disk space. It changes nothing on the phone; lines start with `ok`, `WARN` or `FAIL`, and the exit status is 1 if anything failed. A good first command in any working session.

### Package updates

`tools/phone-update.sh` shows which Alpine packages have updates and changes nothing; with `--apply` it upgrades the ordinary ones and holds back the "sensitive" ones - the graphics stack and desktop (Mesa, KWin, Plasma, Qt, SDDM), sound and camera (PipeWire, libcamera), and what the phone needs to come up and be reachable (musl, BusyBox, OpenRC, udev, D-Bus, NetworkManager, OpenSSH, firmware) - until `--include-sensitive` is given, so that those are upgraded when somebody can look at the screen afterwards. Before changing anything it records the installed versions in `~/j701f/updates/` on the phone, and afterwards it runs the health check. There is no automatic way back: Alpine's stable repository does not keep old versions, so make a backup first when the sensitive ones are included.

### Application profile

`system/apps/setup.sh` runs **on the Alpine phone**. It previews the daily-use application packages by default; `--apply` installs them, `--prune` also removes the listed optional applications, and `--development` adds compilers and diagnostics. The owner's development tools remain installed. Applying requires the `samsung,j7velte` device-tree compatible string. The preview and repeat apply were exercised on the running phone on 2026-10-26 without additional package changes. The script does not build or flash BOOT/RECOVERY, migrate DATA, or configure Wi-Fi; a full public installer is still future work. See `system/apps/README.md` for usage.
It also installs a Koko-only wrapper in `/usr/local/bin/koko` to avoid the image-opening crash with Kirigami's mobile layout.

### Backup

`tools/phone-backup.sh` - see [Backup and rebuilding the phone](userspace.md#backup-and-rebuilding-the-phone).

## Seeing and touching the screen remotely

| Tool | Purpose |
| --- | --- |
| `phone-screenshot.sh OUT.png` | Wake the display, unlock the session, capture through KWin, convert to PNG |
| `kwin-screenshot.c`, `raw-to-png.py` | The two halves the script uses |
| `inject-swipe.py DEV X0 Y0 X1 Y1` | Write a one-finger swipe (or a tap, with equal start and end) into a touch device |
| `inject-key.py` | Write a key press into an input device |

Before a screenshot or a graphical test, wake the output — a blanked screen makes every graphics measurement meaningless. The screenshot has the desktop's logical size, which depends on the display scale (450 × 800 at 160 %).

## Evidence and tests

| Tool | Purpose |
| --- | --- |
| `panfrost-render-probe.c` | Render off-screen on the GPU and verify every pixel |
| `j701f-gpu-evidence.py`, `j701f-board-evidence.py` | Turn captures from the live phone into the JSON files the verifiers use |
| `scroll-benchmark.mjs`, `bench/scroll/` | Fixed local browser workload and bounded timing collection; [method and limits](scroll-benchmark.md) |
| `phone-perf-sample.py` | Bounded phone CPU/frequency/memory/thermal counters over pinned SSH; matching phone lock required |
| `tests/` | Unit tests: `python3 -m unittest discover -s tests -p "test_*.py"` |

## From the first stages

`recovery.py`, `flash-system.py`, `build-system.py`, `alpine-ram-test.py`, `ondevice-terminal.c` and the other early tools built the recovery environment and the first Alpine installation ([chapters 2 and 3](../journey/02-recovery-linux.md)). They are still the way to rebuild the phone from nothing.

## Recovery (in development)

A graphical recovery for the RECOVERY slot is being built; it has its own page: [Graphical recovery](recovery.md).

## Working in parallel

| Tool | Purpose |
| --- | --- |
| `coord.sh` | Locks (`phone`, `kbuild`), a work board and a message inbox for two assistants or people working at the same time; rules in `docs/coordination/README.md` |

## Where things live

| Path | Contents |
| --- | --- |
| `kernel/` | Device trees, patches, configuration, initramfs scripts, pinned inputs |
| `system/` | Files installed into the Alpine system |
| `tools/` | The tools above |
| `docs/` | Working notes and the detailed log (`j701f-mainline.md`) |
| `wiki/` | This wiki |
| `build/` | Everything generated: images, logs, measurements, screenshots. Not source |

## Native display GPU-sharing probe

`run-native-display-trial.py --prime-probe` adds `native-display-prime.c` under
the existing lock/BOOT/watchdog guards. GBM/libdrm headers are required. Render-node and display-backed GBM allocators
are tested separately; rejection of the first alone does not prove IOMMU is needed.
`prime.log` separately records GPU-buffer import into Exynos and FB-object
creation; it measures neither visible scanout nor desktop FPS. The actual phone trial rejected render-node import but accepted display-backed
FB creation; GPU rendering remains unverified. Staging is under
`~/j701f/display-runtime/LABEL`. See [display method](display.md).

The same option now adds `native-display-egl.c` (renderer identity on both
devices) and `native-display-dmabuf.c` (Panfrost shader into a display-allocated
DMA-BUF, GPU/CPU pixel checks, independent Exynos FB creation). EGL/GLES2 and
Linux DMA-BUF headers are also required; compilation happens before watchdog
arming. Logs are `egl-render.log`, `egl-display.log` and `shared-render.log`.
The child deadline is 150 seconds with these probes; each has a shorter timeout.
Neither additional helper presents a frame. Phone execution passed in
`native-dsimpll2-01`: both EGL contexts Panfrost/T830,4096 shared-buffer pixels
verified through GL and CPU, Exynos FB accepted. Context identity, shared-buffer drawing and FB creation are separate
result fields, and none alone establishes daily native desktop performance.
`pll_initialization` separately checks first-attempt completion and register
state; a later successful retry does not hide the first timeout.
`panel_power_mode` preserves the raw reply (0x1c in this trial); native checks
require core power-mode bits2..6=0x1c, not only transport success. Bit7 difference
from the earlier0x9c is left uninterpreted; physical appearance is separate.
