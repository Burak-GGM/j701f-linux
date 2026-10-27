# Linux 7.2.13 host migration

This is a separate, host-only candidate. The phone's installed BOOT and its
running kernel are unchanged. The established `panfrost` profile remains the
7.1.13 build; `panfrost-7.2` uses a separate source tree, output directory,
and artifact directory.

The source archive and SHA-256 are pinned in `kernel/inputs.json`. The four
community Exynos 7870 patches in `kernel/patches/exynos7870-7.2/` are followed
by the project's `linux-*.patch` files. Community patches 05 and 06 from the
7.1 set are already in Linux 7.2.13 and must not be applied again. The
resolved configuration digest is pinned separately from the 7.1 profile.

Build and inspect the candidate on the host:

```sh
tools/coord.sh wait kbuild codex 'Linux 7.2.13 host build' 90 1
python3 tools/build-kernel.py panfrost-7.2 --jobs 11 --modules
python3 tools/build-display-prototype.py --worker codex --kernel-profile panfrost-7.2
J701F_KERNEL_PROFILE=panfrost-7.2 tools/build-mainline-image.sh cam5-72 kernel/dts/exynos7870-j7velte-camera.dts '--allow-audio --allow-sd --allow-mfc'
tools/coord.sh unlock kbuild codex
```

The kernel report is `build/kernel/panfrost-7.2/report.json`. The final FIT
report is `build/kernel/handoff-cam5-72/report.json`; its `kernel_profile` and
`inputs.kernel.path` must name `panfrost-7.2` before review. The host pipeline
checks the device tree, FIT payloads and RAM layout, U-Boot guard behavior,
QEMU Linux entry, and unit tests. A host pass does not establish that this
kernel boots or that its drivers work on the phone.

For the initial compile check, all nine `tools/kmod/j701f_*.c` modules and all
four `tools/kmod/ea8061s/*.c` modules built against the successful 7.2.13
trial's `Module.symvers`, with no compiler warnings. The resulting `.ko` files
were not installed on the phone. Logs are in the ignored directories
`build/kernel/kmod-7.2/` and `build/kernel/ea8061s-7.2/`.

The separate, pinned build also passed with zero compiler warnings. Its
`Image` is 27,531,776 bytes (SHA-256
`8341d50ea26046156e7e8d73d01507547aaf6e29d442b44763f16e9c2b83465f`),
and its resolved config matches the pinned digest
`94b533e02182e1c4221d06c0a574de79cc0d4a864a077dc492462e11135688d3`.
The NEON framebuffer object compiled without the two former macro warnings.
The nine local modules and four display modules were rebuilt successfully
against this final output. `build-display-prototype.py` also produced its
isolated 7.2 panel/info report.

The `cam5-72` host pipeline passed DT validation, initramfs checks, FIT
payload/hash/layout checks, the embedded loader guards (2 valid and 15
rejected cases), the QEMU `LINUX_ENTRY_BOUNDARY_REACHED` trace, and the unit
suite (`OK`, one skipped). The FIT report points to
`build/kernel/panfrost-7.2/Image` with the exact SHA-256 above. It prepared a
13,750,288-byte BOOT candidate under `build/kernel/boot-update-cam5-72/`.
Nothing was sent to the phone; hardware boot and driver behavior remain
unverified pending review.
