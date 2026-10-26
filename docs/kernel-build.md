# Kernel build milestone — 2026-10-08

The user selected Mesa Panfrost as the graphics target. This milestone builds kernels on the laptop and saves compile evidence. It does not install a kernel, package an Odin image, modify phone partitions, or establish working GPU acceleration.

## Two build profiles

| Profile | Source | Purpose |
| --- | --- | --- |
| `baseline` | Related SIMPLE Linux 3.18.140 source | Establish a source build close to the working vendor kernel, with the recovered configuration and J7velte hardware selection. |
| `panfrost` | Existing Exynos7870 close-to-mainline Linux 6.15 source | Compile the standard DRM/Panfrost stack and available related-board device trees as a foundation for a J701F port. |

The running phone keeps its original verified 3.18.140 kernel. The related SIMPLE branch is not an attested exact source match for that binary. Building it is not a claim of reproducing the original bytes or proving that it boots. Its vendor Mali driver remains enabled in the baseline; this is not the Panfrost build.

Panfrost is the [Mesa graphics driver for Mali-T830](https://docs.mesa3d.org/drivers/panfrost.html). The kernel side also needs standard DRM support, GPU clocks/power/buffers, and integration with the display controller. These are not supplied by adding Mesa packages to the current `/dev/mali0` stack.

## Pinned source inputs

`kernel/inputs.json` records immutable revisions, archive URLs and SHA-256 values:

- SIMPLE: `29223d295a58ebe82e95347c8eb8468ea2b1c336`, from [SIMPLE-V1.0-PERMISSIVE](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/tree/29223d295a58ebe82e95347c8eb8468ea2b1c336).
- Exynos7870 mainline: `9186b039cf245886b25e4395b1bb20f0d3c03948`, from [exynos7870/6.15](https://gitlab.com/exynos7870-mainline/linux/-/tree/9186b039cf245886b25e4395b1bb20f0d3c03948).

Archive hashes were recorded from HTTPS downloads and are checked on reuse. They detect changed input; they are not independently verified release signatures. The 6.15 branch is an existing experimental SoC port selected for this build milestone, not a promise of a maintained production kernel.

The user-provided Quantum repository remains a device/driver reference. Its resolved HEAD during this milestone was `ef4326c93656866b482fa2efd062904fd88e579a`; it is not substituted for the closer SIMPLE baseline or the mainline Panfrost target.

## Build commands

On the laptop, from this project directory:

```sh
python3 tools/build-kernel.py baseline --jobs 3 --save-vmlinux
python3 tools/build-kernel.py panfrost --jobs 2
```

`--prepare-only` verifies/downloads source and checks the compiler without compiling. There is no execute/flash option. First preparation needs HTTPS access; subsequent builds use the checked archive cache.

The workspace is on NTFS. Thousands of source/object files are therefore extracted and built under `/tmp/j701f-kernel-build` on a Linux tmpfs; source archives, compilers, config snapshots and final artifacts persist in the workspace. `/tmp` caches are expendable and disappear on laptop reboot. The two profiles together consume several GiB there; jobs are deliberately limited because the laptop is also running other applications. Do not launch two builds of the same profile against its shared output directory simultaneously.

Output is saved in `build/kernel/baseline/` and `build/kernel/panfrost/`: `Image`, `config`, `System.map`, `build.log` and `report.json`. The baseline additionally saves its DTBH image and a config diff. `--save-vmlinux` retains a compressed ELF for later symbol/debug inspection. Panfrost saves compiled related-board DTBs in `dtbs/`.

The report records source, compiler, command, config/artifact hashes, AArch64 Image header fields and kernel release. It explicitly records `phone_modified=false`, `hardware_boot_tested=false` and `flash_ready=false`. A failed invocation changes the report to `failed`; leftover files from an earlier invocation do not override that status.

The resolved mainline configuration hash is also pinned in `kernel/inputs.json`. An unchanged cached configuration can be reused for incremental builds. A changed compiler or fragment that resolves to a different configuration stops for review, rather than silently producing another target with the same profile name.

## Baseline compiler and configuration

The binary on the phone reports GCC 4.9.x 20150123. The first profile uses official Android aarch64 GCC 4.9, pinned to commit `84fb09fafc92a3d9b4d160f049d46c3c784cc941` from [Android's compiler repository](https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9/+/84fb09fafc92a3d9b4d160f049d46c3c784cc941). The tool validates its origin, commit and clean checkout. This matches the compiler family, not an assertion that the shipped toolchain was identical.

`kernel/configs/vendor-running.config` is the unmodified recovered IKCONFIG, SHA-256 `669d32f426befcb9706b83097a7c92020479caca6c4eaed5bb99764011c0598f`. The pinned resolved seed is `kernel/configs/vendor-baseline.config`. Its differences are:

- An identifying local version, `-BURAK-BASELINE-01`.
- The selected source's Android-10 Kconfig rules enable stack-protector/strong symbols. That source also retains the original `CC_STACKPROTECTOR_NONE` symbol, which reflects its unusual Kconfig choice definitions; the compiler build is not claimed to match the old binary.
- A newly visible USB NDOP gadget option is disabled.

The source's own build script specifies Android `q`/10; those environment values are recorded here and used explicitly. The builder passes `CCACHE=` because this source otherwise assumes ccache. Modern host GCC compiles the build utilities with `-std=gnu89 -fcommon`; this preserves the older host-tool assumptions without applying a runtime driver patch. Kernel code uses the GCC 4.9 cross compiler. The official wrapper prints deprecation notices; these are expected log output.

Build user/host/version/timestamp are fixed. Host compiler/linker and environment still matter; the milestone pins inputs and records outputs, rather than guaranteeing identical bytes on every host. No zswap/hotplug fix is included in this baseline.

## Mainline configuration and missing board port

The mainline profile uses the laptop's Clang/LLVM 22.1.8, arm64 `defconfig`, upstream `exynos7870.config` and `kernel/configs/mainline-bringup.config`. The local fragment identifies the build, keeps initramfs LZMA/ext4/devtmpfs and USB ACM configuration support, and disables large debug-info/BTF objects for the bounded build workspace.

Required built-in options are checked after compilation: `DRM`, `DRM_PANFROST`, `DRM_EXYNOS`, `DRM_EXYNOS7_DECON`, ext4 and devtmpfs. This establishes that the target includes those code paths, not that they probe correctly on the phone.

The pinned source contains Exynos7870 board trees for A2 Core, A6, J5 2017, J6 and On7 variants. It contains **no J701F/j7velte board tree**. Their compiled DTBs are references and cannot be used as drop-in J701F DTBs. The old Samsung DTBH and vendor DT bindings also cannot simply be attached to the modern Image and assumed compatible.

Before a phone boot trial, a J701F tree must describe its memory/reservations, eMMC, PMIC/regulators, clocks, pin control, USB PHY/controller and CPU startup. Display integration needs its actual EA8061S panel and wiring; touch needs its actual Melfas MMS438 controller support. Those device selections come from the recovered vendor config, not from a related phone's model name.

Mainline also changes userspace integration: the working USB setup uses the old Android gadget interface, whereas this target uses configfs. Wi-Fi would use a different kernel driver path, so the current DHD-specific startup cannot be assumed to work unchanged. An appropriate diagnostic initramfs and loader/device-discovery check belong to the boot-trial milestone.

The next staged task is to map those J701F board details against the existing Exynos7870 port and produce a minimal diagnostic boot target. Physical boot/storage/debug evidence comes before GPU rendering, and a small accelerated rendering test comes before Plasma Mobile.

That mapping produced a compiled diagnostic J701F tree, RAM-only initramfs and a source-built U-Boot second stage. Two RECOVERY-only candidates have now been flashed and tried; neither produced verified mainline execution. Both trials required manual recovery. Working rescue and normal Alpine have now been restored again; full BOOT/RECOVERY hashes are verified and SSH is reachable at 192.168.1.142. See [diagnostic preparation, measured properties and remaining limits](j701f-mainline.md). The original `panfrost` profile remains a compile reference; the local board port has separate artifacts and reports.

## Recorded baseline and live board evidence

The baseline completed compilation and artifact checks as `3.18.140-BURAK-BASELINE-01`. Its uncompressed Image is 18,598,264 bytes, SHA-256 `c911446e61af66af2fe26e6ab800e5a02978efe4f0e010714a8e69b2109ac57b`. Its header reports `text_offset=0x80000` and a 22,249,472-byte runtime memory reservation. The memory size includes uninitialized storage/BSS and can exceed the file length; this distinction is covered by three Image-header regression tests and the [AArch64 boot ABI](https://docs.kernel.org/arch/arm64/booting.html).

The source-built DTBH is byte-for-byte identical to `extracted/dtb`, SHA-256 `afbf297a9ea000c596d68471852b16678251b61e21eb088040510a11714e8191`. This is strong evidence for matching board-tree inputs, but it does not attest that all kernel source/code matches the shipped binary. The baseline is not flashed or hardware-tested. Its temporary object cache was removed after checksumming the persisted Image/config/map/DTBH and compressed ELF, releasing about 3 GiB of laptop RAM-backed storage.

A read-only copy of `/sys/firmware/devicetree/base` was saved from the running phone: 5,324 file/directory entries and 46,145 property bytes. The first attempt exceeded the small 16 MiB `/tmp` filesystem because each small property occupies filesystem allocation space; it was cleaned up, then retried successfully in a temporary 64 MiB tmpfs. That mount and capture directory were removed, with `/tmp` returning to 88 KiB used and no capture mount left. No physical partition was mounted or reflashed by the capture.

The host reconstructed a DTB/DTS using `dtc -I fs`. Files are `build/kernel/j701f-live-device-tree.tar.gz`, `j701f-live.dtb`, `j701f-live.dts` and `phone-device-tree-cleanup.txt`. The model is `Samsung J7VE LTE SEA rev02A board based on Exynos7870`. The reconstructed DTB SHA-256 is `6cf7de1d089d8583218a18c1c90df943f74be8106aef470e1b46c2442e5b005e`. It is a vendor-binding reference, not a modern board DT ready to boot. Its chosen properties may contain device-specific identifiers, so the capture stays in ignored local build output.

## Recorded mainline compile evidence

The mainline target completed as `6.15.0-BURAK-PANFROST-01`. Its Image is 17,986,048 bytes, SHA-256 `58a9059e5b76b7ad58ea527f6c4346fecff09511a9d97ff1c7748f82539eac65`. The header reports an 18,677,760-byte memory reservation, `text_offset=0x0` and flags `0xa`. The different load offset is another input that must be checked against Samsung's boot handoff before building a phone boot image; the compile milestone does not patch it or assume that the old image layout is sufficient.

The five related-board DTBs compiled. Required DRM/Panfrost/Exynos configuration entries were verified, and `System.map` contains linked `panfrost_device_init`, `panfrost_gpu_init` and `panfrost_job_init` symbols. Every saved artifact hash in both build reports was rechecked. The first full mainline compilation log is retained as `first-compile.log`; an incremental build reran with the corrected Image-memory-size validation and completed successfully. That correction concerned the host validator, not a kernel compilation failure.

Three focused Image-header tests passed, including the runtime-memory-versus-file-size case. The builder also passed Python syntax checking. No device boot, GPU rendering, clock/power validation or Plasma test was performed. The working phone still reported the original `3.18.140-SIMPLE-KERNEL_V1.0` during the read-only board capture.

After the final artifact checksum checks, all generated `/tmp/j701f-kernel-build` caches and the abandoned partial NTFS extraction were removed to release laptop memory. Checked download archives, the compiler checkout and final artifacts remain in the workspace. The next build will recreate its temporary source/output directories.


## Later hardware trial status

Three Linux 6.15 diagnostic candidates have now been tried through RECOVERY, with complete read-back and unchanged normal BOOT. None supplied boot/USB proof. The third corrected a confirmed LLD BSS layout defect and changed the Samsung container to embedded FIT plus empty Android ramdisk and stub DTBH; it stayed at the Samsung logo. The working new UI rescue was restored and completely read-back verified; normal Alpine/Wi-Fi/pinned SSH returned at **192.168.1.145** on the original kernel. [Detailed trial records and limits](j701f-mainline.md#third-candidate-embedded-fit-and-corrected-loader-layout).
