# Third-party inputs and provenance

The repository is licensed GPL-2.0-only (see `LICENSE`). Kernel patches and files derived from other
projects keep their own notices. Apart from the generated tables noted below
(camera sensor and thermistor tables in `tools/kmod/`), none of the inputs is stored in the repository:
each is fetched from the pinned URL and checked against the recorded hash. The read-only reference snapshots listed as
`tools/reference/...` are kept locally only; fetch them from the URLs given here.

The user supplied OrangeFox and Odin4 binaries. The project copies the known-good recovery locally, verifies it, and reuses its kernel and DTB payload. It does not establish upstream authenticity or redistribute rights for those supplied files. Existing stock firmware bundles are never build inputs.

BusyBox input:

- Official package page: https://pkgs.alpinelinux.org/package/v3.20/main/aarch64/busybox-static
- Package URL: https://dl-cdn.alpinelinux.org/alpine/v3.20/main/aarch64/busybox-static-1.36.1-r31.apk
- Package SHA-256: `1d8e7a7fc2ed69bdb8eb7be9d962489c21a0f75b72d8a325437c8a09d4cfac70`
- Extracted `bin/busybox.static` SHA-256: `ebd2865edcab0b590c7d0edb70d3e782cbfb541e518a390ced3a3e186509bc7f`
- License reported by Alpine: GPL-2.0-only.
- Source/build recipe: follow the package page's source and commit links for the exact Alpine revision, including Alpine patches and configuration. BusyBox upstream source: https://busybox.net/downloads/

The cached APK and provenance report support repeatable local builds. The pinned digest detects changed downloads; it was recorded from the HTTPS fetch, not independently authenticated with Alpine's signing key. Package extraction selects a single regular payload and never installs Alpine packages on the host.

If publishing images, provide corresponding source and applicable notices for the reused GPL components, including the exact BusyBox package sources/patches and the supplied recovery kernel. A binary hash or generic upstream URL alone is not corresponding source. No publication is performed here.

Format references used while checking the independently written parser:

- Legacy Android boot header and DT hashing: https://github.com/osm0sis/mkbootimg
- Linux early userspace and initramfs: https://docs.kernel.org/filesystems/ramfs-rootfs-initramfs.html
- Local Odin4 `-h` output (version `1.2.1-dc05e3ea`) for the actual installed command syntax. No options from unrelated Odin implementations are assumed.

USB/display diagnostic reference snapshots (read for understanding, not compiled):

- `tools/reference/android-usb.c`: https://raw.githubusercontent.com/samsungexynos7870/android_kernel_samsung_exynos7870/SIMPLE-V1.0-PERMISSIVE/drivers/usb/gadget/android.c — SHA-256 `e04ff3f3c26a91b26ea09567239fe1a9e7ae7c4374e95f20a6c52837f4f739c3`. Related kernel source, not a verified exact match to the supplied binary. The file retains its upstream GPL notice.
- `tools/reference/fbsplash.c`: https://raw.githubusercontent.com/mirror/busybox/1_36_1/miscutils/fbsplash.c — SHA-256 `5cdcf9be5dccc0cb5eeb5246fa6716218908ddf3d5b61e942c4ef67704e17803`. Inspected for framebuffer handling. The new independently written helper also sets alpha and requests pan/scanout, which are relevant to this display experiment. The snapshot retains its upstream notice.
- The related display source snapshots use the same [SIMPLE-V1.0-PERMISSIVE decon_7870 directory](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/tree/SIMPLE-V1.0-PERMISSIVE/drivers/video/fbdev/exynos/decon_7870): `decon-Makefile` SHA-256 `77da390a745e11116bc6f078eac676059945fcfc5b412adb833dd11e38efe582`, `decon_core.c` SHA-256 `d171b1d0d03790f48927326b52146cb3504d51830e50d59fdc08686791176158`, and `decon-int_drv.c` SHA-256 `695ebba1ff11ceb3562d5cbffdfb21c0f1e1ef92c5f35f16be47e518a663a321`. These describe mode preparation and pan submission; they do not prove an exact source match to the shipped kernel. They retain upstream notices and are not compiled into the helper.

`tools/fb-heartbeat.c` uses the installed Linux framebuffer UAPI and the standard AArch64 Linux syscall ABI. It contains no extracted kernel code, physical framebuffer address, or device-specific display resolution. Its font glyphs are defined directly in that source.

`tools/reference/sec_reboot.c` is an uncompiled, related kernel-family source snapshot used to check reboot destination strings and charging power-off behavior: [Samsung reboot handler](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/SIMPLE-V1.0-PERMISSIVE/drivers/staging/samsung/sec_reboot.c), SHA-256 `b0715dec0df6b0df5541e1e5aada46fe8a6c921bc94290555a0b91eaa277def2`. It retains its upstream notice and is not claimed to match the binary exactly.

## Source kernel builds

The 2026-10-08 build milestone adds independently built research artifacts from the related SIMPLE 3.18.140 source and the Exynos7870 close-to-mainline 6.15 port. Immutable commits, archive URLs and SHA-256 values are in `kernel/inputs.json`; cached source archives retain their upstream COPYING/license notices. Compiler, configurations, build commands and output hashes are recorded in the corresponding `build/kernel/*/report.json`. See [kernel build instructions and source limits](kernel-build.md).

The vendor build uses official Android GCC 4.9 at a pinned compiler repository revision; the mainline build uses the installed host LLVM. The source trees are extracted without driver patches in this milestone. Configuration fragments and the host-tool compatibility flags are part of the build recipe. These compile targets do not replace the supplied kernel in recovery or the normal phone boot image, and compilation alone is not evidence of a working phone port. Any later publication must accompany the compiled GPL components with their corresponding source and build/configuration changes.

The later J701F diagnostic board source is kept in `kernel/dts/`; measured properties and transformation limits are documented separately. The diagnostic U-Boot second stage uses official v2026.01 commit `127a42c7257a6ffbbd1575ed1cbaa8f5408a44b3`, with its input pin in `kernel/uboot-input.json`, local source patch in `kernel/patches/uboot-j701f-diagnostic.patch`, configuration fragment and environment source in this project. The independently written GPL-2.0 handoff command is `kernel/diagnostic/j701f-ramboot.c`; its object is added to the board Makefile by the builder. The paired payload header is generated from the FIT and its hash is recorded in the loader report. The checked archive retains upstream licenses; the modified board file retains its GPL-2.0 notice. None of these artifacts is installed or published. See [diagnostic preparation](j701f-mainline.md) for the complete build recipe and verification limits.

The GPU audit reads the r28p0 platform files selected by the running IKCONFIG from the same checked SIMPLE archive. Snapshots remain in ignored `build/kernel/vendor-gpu-reference-r28p0/` with a provenance manifest and upstream notices. They are references, not code linked into Panfrost or the independently written headless GLES probe. The probe uses installed EGL/GLES/GBM/libdrm APIs; [Panfrost integration](panfrost-bringup.md) links the primary Mesa/Khronos references and distinguishes software pipeline validation from hardware rendering.


## Alpine 3.24.0 minirootfs

The user-selected official AArch64 minirootfs is cached under `tools/downloads/` for RAM-only compatibility trials, not embedded in the recovery archive. `tools/alpine-ram-test.py` pins SHA-256 `4b8cd66a6688b2a87276c39843ed89c3a06d9534fc6a5823c586aff2696c1f2a` and verifies its detached release signature against Alpine's HTTPS-published release public key (fingerprint `0482D84022F52DF1C4E7CD43293ACD0907D9495A`). See `docs/alpine-ram-trial.md` for URLs and verification limits, and `build/alpine-provenance.json` for the archive inventory totals. Component licenses and source packaging are governed by Alpine's package metadata and corresponding [v3.24 aports sources](https://gitlab.alpinelinux.org/alpine/aports/-/tree/3.24-stable); the archive includes both GPL and other licensed components and is not a newly source-built distribution by this project.

LVGL (recovery UI, added by Claude 2026-10-10):

- Source: https://github.com/lvgl/lvgl, tag `v9.2.2`, commit `7f07a129e8d77f4984fff8e623fd5be18ff42e74`, shallow clone in `build/third-party/lvgl-src` (not committed to this repository).
- Licence: MIT (`LICENCE.txt` in the source); the notice has to accompany any distributed recovery image.
- Used by `recovery/ui/` (configuration in `recovery/ui/lv_conf.h`).

## uMTP-Responder (MTP over USB, added by Claude 2026-10-10)

- Source: https://github.com/viveris/uMTP-Responder, tag `umtprd-1.6.8`, commit `149efca9d5e236171e770938174a6064edbf44f7`. Licence: GPL-3.0-or-later.
- Use: built unmodified on the phone, installed as `/usr/local/bin/umtprd`; configuration and start script are the project's own (`system/usb-mtp/`).
- The source tree is kept under `build/third-party/` and is not part of the repository.

## Vendor flash-LED driver (reference only, added by Claude 2026-10-10)

- `drivers/leds/leds-s2mu005.c`, `include/linux/leds-s2mu005.h` from github.com/samsungexynos7870/android_kernel_samsung_exynos7870 @ `29223d295a58ebe82e95347c8eb8468ea2b1c336`, GPL-2.0. Kept in `build/kernel/vendor-fled-reference/`; register meanings and the order of writes were taken from it for the flashlight part of the charger driver.
- `drivers/battery_v2/s2mu005_fuelgauge.c` and its header (also the older `drivers/battery/` copy) from the same tree and commit, GPL-2.0. Kept in `build/kernel/vendor-fuelgauge-reference/`; the conditions for switching the fuel gauge between current and voltage mode in `system/battery/j701f-battery` were taken from `s2mu005_get_rawsoc()`. The charge-current encodings in the charger driver come from the already listed `s2mu005_charger.c`.
- `drivers/iio/adc/exynos_adc.c` from the same tree and commit, GPL-2.0. Kept in `build/kernel/vendor-adc-reference/`; the "exynos-adc-v3" conversion sequence and register offsets in `tools/kmod/j701f_adc.c` follow it. The thermistor tables in `tools/kmod/j701f-adc-tables.h` are values from the phone's factory device tree.
- `drivers/misc/modem_v1/` (shared-memory link, I/O devices, SS310AP control, SIPC5 framing), `drivers/misc/mcu_ipc/` (mailbox, shared-memory layout) and `drivers/soc/samsung/pmu-cp.c` with their headers, same tree and commit, GPL-2.0. Kept in `build/kernel/vendor-modem-reference/` as the reference for the modem work; so far only the secure-monitor read call and the register names in `tools/kmod/j701f_modem_probe.c` come from it.

## Camera work (added by Claude 2026-10-10)

- Vendor camera sources consulted as a reference (GPL-2.0, same pinned vendor tree `29223d295a58...`): `drivers/media/platform/exynos/fimc-is2/` sensor, module, CSI and chain files and `drivers/phy/phy-exynos-mipi.c`, kept in `build/kernel/vendor-camera-reference/`. The sensor register tables in `tools/kmod/s5k3l2-tables.h` and `s5k5e3-tables.h` are machine-converted from them.
- `udmabuf` module: `drivers/dma-buf/udmabuf.c` of Linux 7.1.13 (GPL-2.0), built out of tree with `tools/kmod/udmabuf-out-of-tree.patch`.
- v4l2loopback 0.15.1 (GPL-2.0, github.com/v4l2loopback/v4l2loopback, commit `7546a42a...`): fetched and built with `tools/kmod/v4l2loopback-linux-7.1.patch`, not installed.
- Alpine packages installed for it: `libcamera-tools`, `py3-numpy`, `py3-pillow`.

## OrangeFox recovery for the release ZIP test (added by Claude 2026-10-27)

- `OrangeFox-j7velte-beta@R11.1.zip` and `OrangeFox-j7velte-stable@R11.0_1.zip`, downloaded from the official OrangeFox API mirror (`dl.orangefox.download`, release ids `6103cb9ddfa9fd3c4edb5762` and `5fa2585c18a4f5027b916617`). Their MD5 values and those of the contained `recovery.img` match the API. R11.1's `recovery.img` (SHA-256 `5bbcb385...`) is byte-identical to the user-supplied `original/OrangeFox-recovery.img`, which gives that image the provenance it lacked. Licence: GPL-3.0-or-later (OrangeFox), components under their own licences. Kept in `build/third-party/recoveries/`, not in the repository. Details: [recovery-zip-device-test.md](recovery-zip-device-test.md).
- No official TWRP exists for j7velte; the 2018 TWRP tar in `tools/` has no known origin and is not used.
