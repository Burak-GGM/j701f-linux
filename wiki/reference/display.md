# Real display driver

!!! success "Status: the native driver is the daily path (since 2026-10-10)"
    Every boot switches from the bootloader's framebuffer (`simpledrm`) to the real **DECON → MIPI DSI → EA8061S** path before the desktop starts: page flips at the panel's 59.6 Hz without a copy per frame, real panel brightness, screen off and on, resume from suspend. The bootloader framebuffer remains the fallback. The sections below are the record of how it got there, newest first; the story is in [journey chapter 12](../journey/12-display.md).

Suspend: with the native driver active the phone was put into suspend-to-idle and woken by a clock alarm 25 seconds later. The display link came back at once and the desktop drew at 57 frames per second afterwards. Nobody watched the screen during it.

## Plasma on the native driver (2026-10-10)

Claude took the display work over while Codex is away. Three more RAM-only trials with the same watchdog return:

| Trial | Result |
| --- | --- |
| `plasma-dsimpll2-02` | Plasma started on the native driver: KWin on `exynos-drm`, Panfrost rendering into a buffer allocated on the display device, no copy. The test that gives 54–56 frames per second on the copied framebuffer gives **59.5–59.8** here, i.e. the panel's refresh rate. KWin's screenshot is a normal home screen |
| `plasma-bl-01` | The panel driver now has a backlight device (`j701f-panel`): levels are mapped onto the panel's AOR register, the range taken from the vendor's table. Five levels written and read back, no complaint from the DSI link |
| `plasma-dpms-01` | Screen off and on through the compositor: output inactive while off, back afterwards, 59 frames per second again |

Nobody saw the panel during these trials; the numbers come from the kernel's display state and from the compositor. The owner looked afterwards (below).

**Daily path since 2026-10-10.** The owner looked at the panel on the native driver and found picture, brightness and screen off/on correct. A boot service (`system/display-native/`, installed as `/etc/init.d/j701f-display`) now switches to it before the desktop starts on every boot. Ways back to the firmware framebuffer: hold Volume Down while the phone boots; a failed or hung switch reboots and leaves a stamp that makes the next boots skip it; or remove `/etc/j701f-display-native`. The display nodes still come from an overlay that a module loads, pinned to the exact kernel in BOOT: after a kernel update the modules must be rebuilt, otherwise the switch declines and the phone uses the firmware framebuffer.

## First hardware trial passed

Roadmap 1.1 passed in the RAM-only `native-bl9-05` trial. DECON and DSIM bound,
the EA8061S panel answered DCS GET_POWER_MODE with `0x9c`, and 120 page flips
completed at 59.641 Hz. DECON read a new physical buffer at `0xbe200000`;
DSIM reported 720×1280 and the measured horizontal/vertical porches; display
SysMMU translation stayed off. The watchdog automatically returned the phone
to unchanged `bl9` BOOT, simpledrm and Plasma. Evidence and all seven checks:
`build/kernel/display-runtime/runs/native-bl9-05/result.json`.

The final fix was `panel.prepare_prev_first = true`, so the DSI host is prepared
before panel commands. **Physical appearance is unseen** pending owner feedback.
This is not daily native display or a desktop benchmark. One initial PLL timeout
still appears before later successful link setup; investigate it before daily
use. The successful capture uses P=3/M=110/S=1, so it does not justify changing
the PLL ratios blindly. Normal boots still use simpledrm. Native calibrated
brightness and blank/suspend remain future stages.
After startup settled, no safety stamps remained, GPU/CPU ceilings were back
at1001/1586MHz, and the RAM overlay was absent. The exact executed phone files
are archived locally beside the result, with a SHA recorded in it.

## Preparing the daily display path

**Current BOOT:** isolated `dsimpll2` is installed with full-partition read-back
`a2b11f5a…`; running GNU build ID `1950147e…` and Plasma/simpledrm match. Its
DTB/initramfs are exact diagnostic bytes. Modules/overlay have been rebuilt;
fresh watchdog and native fix verification now passed. Daily display is still
simpledrm. Evidence: `build/kernel/dsim-pll-observe/installed-fix3.json` and
`build/kernel/display-runtime/runs/native-dsimpll2-01/result.json`.
First PLL initialization completed on one attempt without timeout; all seven
native checks and120 flips at59.641Hz passed, followed by automatic return to
the exact same BOOT/build ID/Plasma. DCS reply is0x1c this time (core bits same
as prior0x9c; bit7 difference recorded without interpretation). Settled startup
stamps are clear, CPU/GPU ceilings1586/1001MHz and the RAM overlay absent.
The following diagnostic results preceded this installation.

`dsimdiag2` was installed with full BOOT read-back; running GNU build ID and
Plasma/simpledrm matched. Its own watchdog rehearsal and `native-dsimdiag2-01`
passed: panel reply,120 flips/59.641Hz and automatic unchanged BOOT return.
After startup settled, stamps were clear, CPU/GPU ceilings1586/1001MHz and the
RAM overlay absent. Daily display remains simpledrm; physical appearance unseen.

Before first PLL programming, the PLL was already enabled/locked, but no fresh
completion arrived. Initialization immediately completed after error cleanup
turned it off. A small J701F-trial-only fix stops inherited clocks before reset.
Five new actual-init tests, all29 DSIM tests, package tests (one skipped), W=1
and QEMU checks passed before installation. Isolated `dsimpll2` uses
the previous exact DTB/initramfs. Earlier `dsimpll1` also contained the newly
guarded recovery hook and is excluded from this A/B; Claude's source is intact.

`--prime-probe` measured two paths: Exynos rejected render-node GBM import with
EINVAL; display-backed GBM exported/imported a buffer and created an FB object.
The latter also logged a ZINK initialization error; its eventual renderer is
unknown. Neither buffer was presented, nor GPU rendering verified. This proves
neither that IOMMU is mandatory nor a zero-copy accelerated desktop. The next
measurement must establish EGL/GL renderer, drawing into the imported buffer
and actual compositor timing.

Two additional probes **passed on the phone** in `native-dsimpll2-01`.
`native-display-egl.c` identifies the actual renderer on each GBM path.
`native-display-dmabuf.c` uses Panfrost to draw into a display-allocated linear
buffer, checks 4096 pixels through GPU readback and synchronized CPU mapping,
then tests Exynos FB creation. It never presents that buffer. A passing result
establishes shared-buffer rendering, not native GPU scanout or desktop FPS.
The optional trial now allows 150 seconds and keeps the watchdog return.
All27 native-display host tests pass. Both EGL paths reported Panfrost/T830;
GPU and CPU verified4096 pixels, and Exynos FB creation passed. Actual phone
files/hashes are archived beside the result. The separate
`pll_initialization` result checks the first completion and register evidence;
the real diagnostic baseline correctly fails it despite its successful retry.
The fixed kernel passes on its first attempt. The next gate is bounded native
Plasma and the same compositor benchmark; roadmap1.2 remains open.
The old diagnostic phone staging folder was removed only after successor
verification; host images/rescue backup remain. Phone handed healthy to Claude
for the next recovery trial, with exact full-BOOT restore requested.

Read-only inspection confirms the required development headers and Mesa26.1.6.
That version's official kmsro/Panfrost source supports display-side buffer
allocation with 64-byte stride alignment (2880 bytes meets it). This supports
testing that route; it does not prove the installed native EGL path uses it.
Source URLs/checksums are in `build/kernel/mesa-native-reference/provenance.json`.

Trial files moved without deletion into `~/j701f/display-runtime/`. New image
staging is `~/j701f/boot-update/dsimpll2`; modules must be pinned again and a fresh
watchdog rehearsal run. Phone handed to Claude for the remaining folder migration.

## Trial method and earlier attempts

The approved `docs/roadmap.md` permits unattended trials, provided
they automatically return to a working image; panel appearance is recorded as
unseen unless the owner reports it. Codex ran a **RAM-only** first
trial on the existing working BOOT. `tools/build-display-overlay.py` builds
`kernel/dts/j701f-display-runtime.dtso` and a one-shot loader. The merged tree
passes 21 native software checks. Twelve host tests cover graph equivalence,
changes confined to display nodes, preserved RAM reservations and supervisor
deadline/failure behaviour. The module and standard DCS power-mode reader build
with `W=1`. The KMS program compiles with warnings treated as errors.
Five of those tests compile the actual loader initialisation under address/UB
sanitizers, covering wrong machine/configuration, active controllers, bound
firmware/MMU, failed IOMMU-property removal and partial overlay-apply failure.

The active prototype is now pinned to `dsimdiag2`; the first successful
hardware trial used the earlier `bl9` framebuffer-copy revision. `display-trial-supervisor.py` opens and feeds the watchdog,
starts a bounded child, then **stops feeding while keeping the fd open**. A
mandatory no-display-change rehearsal must prove that this really resets and
boots the same working image before native takeover. Neither BOOT nor RECOVERY
is written. The overlay is never removed in place: reboot discards it. It is
not installed at boot and cannot become the persistent display accidentally.

`native-display-trial.sh` stops SDDM without changing its runlevel, unbinds
simpledrm, opts into the DSIM timing profile, loads the panel/overlay and
reprobes the native DRM master. The intended hardware checks are 120 completed
page flips, a standard DCS GET_POWER_MODE answer and fixed read-only controller
registers. No sound, power-domain reset, arbitrary DCS command or factory-data
read is part of the trial. Physical appearance is separate from these checks.

The first real watchdog rehearsal is now verified on `bl9`:
`build/kernel/display-runtime/runs/wd-bl9-03/result.json`. Feeding stopped with
the fd open, the phone reset by itself and returned to unchanged BOOT/kernel,
simpledrm and Plasma. The final marker is synced before reset; the initial run
returned too but lost that last unsynced log line. The controller waits for
at least 240 seconds uptime and no startup stamps: the GPU job begins after
40 seconds and guards its raised limits for another 180. Two regression tests
check early empty stamps and persistent pending stamps. This proves automatic
return, not native scanout or physical panel appearance.

The first native attempt (`native-bl9-01`) refused before display takeover:
OpenRC said SDDM was stopped despite its supervisor and Plasma still running.
The trial now stops the actual SDDM supervisor and checks the processes again;
autoload/runlevels stay unchanged. Root-owned trial logs are read with sudo,
and live logs use `/dev/kmsg` because BusyBox dmesg has no `-w`. Automatic return
was verified after that refusal; no native panel activation occurred in it.

Stopping SDDM still left compositor children. The trial now verifies the local
SDDM Wayland cgroup and that SSH/watchdog are outside it before stopping its
remaining processes; four scratch-file tests reject unsafe scope selections.
Attempt 03 then reached firmware unbind and found an overlay-loader bug: the
valid embedded DTBO array was not 8-byte aligned, so libfdt rejected its header.
`__aligned(8)` fixes its actual module offset from `0x1e` to `0x20`; `.rodata`
alignment is also 8. Two tests check the real AArch64 module and host libfdt.
That attempt returned safely without native modesetting. Attempt 04 uses the
rebuilt module; the working kernel Image and BOOT remain unchanged.

A lightweight read-only phone preflight confirmed the running GNU build ID
matches the prepared `bl9` modules and `keep_on_shutdown=Y`.
`build/kernel/display-runtime/read-only-kernel-preflight.json` records that
check. It is not a watchdog reset rehearsal or native-display test.

The host controller `tools/run-native-display-trial.py` refuses a missing or
expiring phone lock, a stale BOOT/module build, or a running kernel with a
different GNU build ID. It waits out the existing module-startup safety guards.
Native mode requires a successful watchdog rehearsal on the same BOOT. After
reset it verifies unchanged BOOT/build ID, simpledrm and both KWin/plasmashell
processes. It saves trial, KMS and kernel/pstore logs under
`build/kernel/display-runtime/runs/`. Native success additionally requires a
new DECON buffer address (not firmware `0x67000000`), 720×1280 DSIM resolution,
the measured horizontal porches and disabled SysMMU translation. Six evidence/guard
tests include rejection of the actual old firmware capture, failed DCS reads,
missing flips and wrong timing. A safe reset alone is not reported as native
success. Logs are evidence, not proof of physical
panel appearance. Do not run either mode while Claude owns the phone.

```sh
python3 tools/run-native-display-trial.py --execute --rehearsal --label wd-01
python3 tools/run-native-display-trial.py --execute --label native-01 \
  --rehearsal-report build/kernel/display-runtime/runs/wd-01/result.json
```

### Historical flash candidate (before bl8)

Claude rebased the wiring onto the current suspend layer and prepared
`boot-update-displaytrial3`, without flashing it. Codex independently rechecked
its 24 native/FIT checks and actual Samsung container, embedded FIT/loader,
BOOT guard and predicted full-partition bytes. It uses exactly the same kernel
Image and initramfs as `bl7`; the native display DTB differs. Candidate SHA:
`d797482febef7e9b0bcc77672e21a2860841e02ce5baf74ee152ec26dce04106`.
The previous-BOOT guard expects `bl7` (`25ae86fb…`). Evidence:
`build/kernel/boot-update-displaytrial3/codex-package-audit.json`.

The trial disables the firmware framebuffer device, so its software backlight
does not apply. It still needs a stopped graphical session, explicit DSIM timing
opt-in, manual `allow_init=1` panel load and bounded modesetting. Watching is
helpful; the newer roadmap removed that prerequisite. It has no native brightness implementation yet. The older numbered
packages below are historical; do not use them as the current trial.

## First panel prototype

An experimental panel module is prepared in
`tools/kmod/ea8061s/panel-j701f-ea8061s.c`. It compiles for the installed Linux
7.1.13 kernel with no build warnings. Its initialisation routine matches all
19 static commands in the pinned Samsung J7VE source. Host tests check the
bytes, waits and handling of a failure at every transfer. A second host harness
checks power/reset ordering and cleanup after resource or transfer failures,
including repeated cycles. Nine test methods pass under address/UB sanitizers;
these software checks do not establish electrical behaviour.

It was temporarily loaded and tested in the trial above. It requires explicit
`allow_init=1`, has no node in the active device tree, and uses only the vendor's
fixed initial gamma. It does not yet implement calibrated brightness.

`tools/build-display-prototype.py` rebuilds the modules after checking the
shared `kbuild` lock and pinned configuration. A separate read-only
`j701f-display-info` module is prepared to capture known display registers;
it is not loaded at boot. `tools/capture-display-state.py` temporarily loaded
that diagnostic and confirmed its removal. The running display SysMMU had
CTRL=0 and STATUS=0: translation was disabled, and DECON was reading the physical
framebuffer at `0x67000000`. DSIM's PLL fields matched P=3, M=220, S=2. No display,
clock or MMU registers were written. The wiring candidate
`kernel/dts/exynos7870-j7velte-display-prepared.dts` compiles and resolves the
graph, supplies and reset, with all display controllers still disabled.

The measured timing is 720 × 1280 at nominally 60 Hz, with four RGB888 DSI lanes.
Horizontal back/front/sync are 48/56/4; vertical back/front/sync are 5/9/2.
Reset is gpd3-4, and the supplies are LDO30 (1.8 V) and LDO29 (3.0 V).

## What remains

The first isolated display trial can retain physical DMA and the disabled
display SysMMU measured above. Clock requests and takeover from simpledrm still
need integration; the snapshot does not establish state after a different
reset or boot image. The display shares its power
domain with audio, so restarting that whole domain is unsuitable. The first
hardware trial records its appearance as unseen unless the owner reports it;
successful compilation does not establish visible output.

Before activation, source-level tests found another difference: the common
DSI routine would write horizontal timing counts 46/39/0 instead of the live
firmware's 56/48/4. The compiled `linux-dsim-j701f-timing-trial.patch` adds a
default-off, J701F-only trial profile matching both horizontal and vertical
fields. Six host methods verify that profile and its limits. It requires an
explicit root parameter change before panel loading, with no native session
active. The existing PLL search, tested separately, selects the same 476.667 MHz
output using a lower VCO; its limits remain unchanged. Link stability needs
hardware testing.

A separate, definite software bug was fixed in
`kernel/patches/linux-dsim-pll-wait-fix.patch`: PLL completion was interpreted
backwards, its interrupt was masked, and combined interrupt events could be
discarded. Six actual-C host tests and a full AArch64 kernel rebuild pass.
Claude's later `pfshrink2` package includes this PLL correction. It affects the
future native display path; it does not explain black tiles with today's
simpledrm path. Real PLL lock and panel output still need hardware testing.

`linux-dsim-init-errors.patch` also stops clock/link failures or reset timeout
from being ignored; four host methods cover cleanup and retry. A separate
`display-trial.dts` enables native controllers and disables the simple-framebuffer
device while retaining its reserved RAM and ramoops. The strict
`tools/validate-display-trial.py` checks these resources and the compiled
kernel/module hashes. The recorded `pfshrink4` BOOT package contains all three
DSIM changes but keeps native display controllers disabled. A software-validated
trial is not a verified daily-use display.

The offline `displaytrial1` BOOT package is prepared: 132 project tests ran
(one skipped), QEMU reached Linux's entry, and 20 native-display software checks
passed. Four intentionally invalid DTBs were refused. No phone flash, visible
output or performance improvement is claimed. Details and hashes are in
`build/kernel/boot-update-displaytrial1/display-trial-summary.json`.
Claude subsequently updated the BOOT record to `pfshrink3`. The trial uses the
same kernel and initramfs as that package, with a separate display device tree.
Its update guard was regenerated against the recorded full partition image
(`fe691403…`). SSH was available after the reboot. Recheck the slot if another
image is installed before use; the native display trial itself remains unflashed.

The working notes and evidence paths are in `docs/j701f-display.md` in the
repository. The host command test is:

```sh
python3 -m unittest discover -s tests -p 'test_ea8061s_*.py' -v
```

Display performance and black browser tiles need separate measurements.
Panfrost buffer-purge warnings were captured while Angelfish started under
memory pressure; a display driver alone is not a demonstrated fix for them.

The subsequent DECON audit found a divider-field difference between the common
Exynos7 code and Samsung's 7870 header. A per-SoC correction is staged, with six
actual-C tests passing; it is not in the kernel build inputs or trial image.
The clock framework currently reports 64 MHz, selecting divide-one, so the
affected write is skipped. This is a latent integration issue rather than
evidence of today's slowdown. Triple-buffer bit 18 also needs review against
hardware: the vendor header does not name it, which alone proves no defect.
See the working notes for the exact scope.

The [local browser benchmark](scroll-benchmark.md) now provides a fixed silent
scene for later comparisons. Its desktop checks do not measure phone speed.

The latest GPU revision superseded the original trial package. `displaytrial1`
is retained as a historical checkpoint; its original BOOT guard rejects the
new slot. A new FIT (`handoff-displaytrial2`) uses the `pfshrink4`
Image. The module builder now pins its Image and symbol-version hashes.
Validation with `--handoff-dir` checks the actual compressed FIT payloads, not
only their report: 24 checks pass, and stale/corrupt payloads are refused in
three negative cases. The completed Samsung BOOT package is in
`boot-update-displaytrial2`: QEMU reaches Linux's first instruction and 146
tests pass (one skipped). It remains uninstalled and has no hardware-output or
performance verification. Its update guard expects the recorded `pfshrink4`
partition; recheck that identity before use.
