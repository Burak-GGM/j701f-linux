# J701F real display path — Codex working notes

<!-- CODEX-BEGIN 2026-10-10 -->

## Current result

**Latest installed checkpoint:** isolated `dsimpll2` is now in BOOT, with
full read-back `a2b11f5a…`, fixed Image `2eabbca3…` and actual running GNU build
ID `1950147e…`. Plasma/simpledrm returned; native hardware fix verification is
pending. Evidence: `dsim-pll-observe/installed-fix3.json`, `install3-audit.json`.
Claude restored the exact diagnostic payload but its retained rec1 tail made
full BOOT `76e89600…`, so the update was re-prepared against that actual hash.
The diagnostic DTB/initramfs remain byte-identical. Modules/overlay rebuilt,
21 merged-tree checks pass; a fresh watchdog rehearsal is in progress.
Historical uninstalled-package descriptions below refer to earlier checkpoints.

The fresh watchdog rehearsal and `native-dsimpll2-01` now **passed on hardware**.
First PLL initialization completed on its only attempt, with PLL_EN cleared
before programming, locked link and no PLL failure; diagnostic baseline had
first completion0 then retry1. All seven native checks pass,120 actual flips at
59.641Hz (16.767ms mean interval), native buffer0xbe200000 and automatic return
to exact BOOT/build-ID/Plasma. Actual DCS reply is0x1c, not the prior0x9c;
bits2..6 are0x1c in both. Kernel DCS power-mode definitions cover these core
bits; bit7 difference is recorded without an interpretation. The evaluator now
requires the requested core state, not just a successful read; two regressions
accept observed replies and reject disabled/idle/partial/garbage replies.
27 focused native-display tests and18 display module/guard tests pass.

Both render-node and display-backed EGL contexts actually report
`Mali-T830 MC1 (Panfrost)`, despite a ZINK fallback error. Display-allocated
linear XRGB8888 DMA-BUF drawing passed GPU readback and synchronized CPU mapping
for4096 shader pixels; Exynos import/FB creation passed. Render-node allocated
buffer import still rejects EINVAL. The shared GPU buffer is **not presented**;
this establishes the allocation/rendering route, not accelerated native desktop
or its FPS. Physical appearance remains unseen. Real files are archived beside
the result; all14 manifest entries and local probe-source matches verified.
Settled identity at241s: clear stamps, healthy Plasma/simpledrm; post-check
confirms CPU1586/GPU1001MHz and no RAM overlay. Next is bounded native Plasma
and the same compositor benchmark; Stage1.2 remains open.
After verified successor/settled checks, the old own
`~/j701f/boot-update/dsimdiag2` staging folder was removed by its candidate hash,
following the owner's cleanup rule. Host images and rescue backup remain.
Phone handed healthy to Claude for rec2; request exact full32MiB baseline restore
to preserve watchdog/module pins. No Codex trial process survives the reset.

**Roadmap 1.1 passed on hardware**, in
`build/kernel/display-runtime/runs/native-bl9-05/result.json`:

- Native Exynos DRM bound DECON and DSIM; panel attached on four lanes.
- DCS GET_POWER_MODE returned `0x9c` with result 0.
- 120 actual page flips completed at 59.641 Hz; native buffer `0xbe200000`.
- DSIM resolution `0x050002d0`, horizontal porch `0x00380030`, vertical porch
  `0x60010005`; display SysMMU CTRL/STATUS 0 (physical DMA).
- Watchdog reset returned to unchanged bl9 BOOT (`40e3fde6…`), GNU build ID
  `900acd1f…`, simpledrm and KWin/plasmashell. No BOOT/RECOVERY write.

Panel appearance remains **unseen** pending owner feedback. Daily use still
uses simpledrm; calibrated brightness and blank/suspend are not implemented.
There is one transient initial `PLL failed to stabilize` log before the later
successful link/DCS read. Investigate initialisation IRQ/mask/order before daily
use. Do not conclude the lower-VCO PMS cannot lock: the successful capture uses
that same P=3/M=110/S=1 and reports PLL stable. The measured flip rate equals
64 MHz / (828 × 1296), and is not a compositor benchmark.

The successful change from attempt 04 to 05 was
`ctx->panel.prepare_prev_first = true`: the panel bridge now prepares the DSI
host before panel DCS traffic. No kernel Image change was required. Nine
panel sequence/lifecycle tests and W=1 module rebuild pass. Host trial coverage
is now 24 tests (12 original, six evidence/startup, four scope, two FDT alignment).
After the reset and startup window, no pending stamps remained; GPU/CPU ceilings
were restored to 1001/1586MHz, Plasma/simpledrm were live and the RAM overlay was
absent. `native-bl9-05/settled-baseline.txt` records the read-only check. The
actually executed phone sources/modules/binary/logs are archived locally in
`actual-phone-files.tar.gz`; its SHA is recorded in the result JSON.

## Diagnostic retest and next isolated fix

Installed `dsimdiag2` passed its own watchdog rehearsal (`wd-dsimdiag2-01`)
and native retest (`native-dsimdiag2-01`): all seven hardware checks, DCS reply,
120 flips at59.641Hz and automatic unchanged BOOT/build-ID/Plasma return.
The real files are archived beside the result; flip timing is derived from the
actual 120 events. Appearance remains unseen. Settled uptime713s showed clear
startup stamps and a healthy session; subsequent read-only check confirmed CPU
1586MHz/GPU1001MHz and no overlay.

The diagnostic separates the initial failure from the successful retry:

| Observation | First initialization | Retry after cleanup |
| --- | --- | --- |
| completion | 0 | 1 |
| INTMSK before → after | `b77fffff` → `077b7fff` | same |
| LINK_STATUS before → after | `01110001` → `01110001` | `00100001` → `01100001` |
| PLLCTRL before | `008066e2` (enabled) | `00006371` (disabled) |
| reset completion | 1 | 1 |

This supports an inherited enabled/stable PLL failing to produce a fresh event,
rather than a PLL-ratio change. It is not yet an A/B proof of the fix.
`linux-dsim-zz-j701f-inherited-pll.patch` conditionally calls the existing
DSIM clock cleanup **before reset**, only for the privileged J701F trial and
only if PLL_EN is set. No shared DISPAUD reset, PLL search or IRQ-mask policy
change. Five ASan/UBSan host cases execute the actual init callback against the
baseline: inherited first-init success, profile-off equivalence, already-off
state/idempotence and every cleanup/retry failure. All29 DSIM tests, full package
suite (one skipped), W=1 and checkpatch pass. Fixed Image `2eabbca3…`, GNU build
ID `1950147e…` is **not installed**.

GPU sharing results are separate: render-node linear GBM import into Exynos is
rejected with EINVAL and the kernel's contiguous-buffer error. Display-backed
GBM creates a linear buffer, imports it and creates an FB object. Its Mesa log
also contains a ZINK initialization failure; the eventual renderer is unknown.
Neither probe presents its buffer or proves GPU rendering. This does not yet
establish an IOMMU requirement or a zero-copy desktop. The next GUI test needs
actual EGL/GL renderer, rendering into the imported buffer and compositor timing.

The first fixed package `dsimpll1` included Claude's newly guarded recovery-UI
hook in `/init`. Exact CPIO audit caught this unrelated difference before any
flash; it is historical/unflashed. Isolated `dsimpll2` reuses the exact recorded
`dsimdiag2` DTB and initramfs with the fixed kernel, preserving Claude's source.
Use its new `~/j701f/boot-update/dsimpll2` staging path, after Claude finishes the
project-folder migration. It still requires installation, module repinning,
a fresh watchdog rehearsal and an actual first-init native A/B test.

All nine completed Codex display folders were moved without deletion to
`~/j701f/display-runtime/LABEL`; the controller now stages there. Mapping is in
`build/kernel/dsim-pll-observe/display-folder-migration.json`. Phone released
healthy to Claude for the rest of his one-folder migration. No Codex background
watchdog/native process survives these resets; daily BOOT remains dsimdiag2.

## Additional GPU probes prepared (not yet run on the phone)

The optional `--prime-probe` now also compiles `native-display-egl.c` and
`native-display-dmabuf.c` before arming the watchdog. The first reports the
actual GLES renderer separately for Panfrost and Exynos GBM devices, without
drawing. The second allocates a linear XRGB8888 display buffer, imports its
DMA-BUF into an explicitly Panfrost/T830 EGL context, draws a 64×64 shader
pattern and checks all 4096 pixels both through GL readback and a synchronized
CPU mapping of the exported buffer. It then tests an independent Exynos FB
object. It never attaches that buffer to a plane; no native GPU scanout or
desktop FPS claim follows from it.

Logs are `egl-render.log`, `egl-display.log` and `shared-render.log`; their
stages are evaluated separately in the result JSON. Missing logs mean not run;
renderer identification alone is not a rendering pass. GPU/CPU checks can pass
while FB creation fails. With these optional probes the child deadline is
150 seconds, and each probe has its own timeout; the proven watchdog still
returns to the unchanged working BOOT.

Host verification: all three C helpers compile with `-Wall -Wextra -Werror`;
25 native-display tests pass, including actual CPU-byte validation under
ASan/UBSan and synthetic evidence checks that reject missing stages/software
renderers. These are software checks, not phone GPU results. Claude owns the
active rec1 recovery trial; wait for his exact dsimdiag2 restore/handoff before
installing the isolated PLL fix, re-pinning modules and rehearsing again.

`pll_initialization` separately records every diagnostic attempt and requires
the first completion, reset completion, locked link and a disabled prior PLL,
with no PLL failure messages. The archived real dsimdiag2 log correctly fails
this check despite its later successful retry. Four evidence tests cover that
capture, synthetic fresh success, incomplete/wrong register evidence and absent
diagnostics. This metric is independent of the seven native hardware checks;
it does not retroactively turn the existing native pass into a clean PLL start.

Read-only phone inspection confirms Mesa 26.1.6 and all EGL/GLES2/Linux DMA-BUF
headers. The official same-version source is pinned with URLs/checksums under
`build/kernel/mesa-native-reference/provenance.json`. Its DRM loader falls back
to kmsro for a display-only driver; kmsro can select Panfrost, whose scanout
allocator creates a display-side dumb buffer with 64-byte stride alignment.
720×4=2880 meets that requirement. ZINK is also a possible fallback when a
screen could not be created, so the old ZINK error is insufficient to identify
the final path. These are source findings, not installed-build-flag or native
renderer proof. Keep the two EGL and shared-pixel measurements as the next gate.

Panel/read-only modules were W=1 rebuilt for prepared fixed Image2eabbca3;
the overlay report is still pinned to dsimdiag2. The controller refuses this
pairing. Rebuild the overlay only after the installed BOOT identity changes.

## Next checkpoint: first PLL completion and GPU buffer import

Diagnostic baseline `dsimdiag2` was prepared against bl9, then **installed with
full BOOT read-back**. Running GNU build ID matches; Plasma/simpledrm returned.
Evidence: `build/kernel/dsim-pll-observe/phone-baseline2.json`.
Its DTB and initramfs payloads are byte-identical to bl9; native controllers
remain disabled at normal boot. Image `376b1d82…`, GNU build ID `7ffdee37…`,
candidate `e277a70b…`, predicted full BOOT `5c1e7163…`; guard expects current
full BOOT `40e3fde6…`. `build/kernel/dsim-pll-observe/candidate-audit.json`
records the full hashes. The old bl9 Image/vmlinux/config/symvers are archived
under that directory's `baseline/`. RECOVERY remained unchanged; only BOOT was written with the guarded updater.

`linux-dsim-z-j701f-pll-diagnostics.patch` adds observations only under the
existing root-only, J701F/Exynos7870-restricted timing opt-in. It captures the
interrupt mask, LINK_STATUS and previous PLL control before programming, then
logs completion, mask/link status after waiting and reset completion. It never reads FIFO/interrupt-source registers
or adds register writes; failed completion still rejects host initialization.
The present source only writes INTMSK from the reset-release handler, so a masked
initial completion is a hypothesis worth testing, **not an established cause**.
The later working LINK_STATUS cannot establish what it was at the first timeout.
The pinned vendor `dsim_reg_set_clocks()` explicitly recognises an already-stable
PLL inherited from U-Boot. An absent fresh PLL event in that state is a second
hypothesis, so pre-programming link/PLL observations are needed too.
Five host cases execute the real patched wait/diagnostic under ASan/UBSan,
including stable hardware without completion and disabled-profile no-extra-read
behaviour. All 24 DSIM tests pass. The full package suite passes (one skipped);
DSIM W=1 object compile and checkpatch (excluding sign-off) are clean. Samsung
container/FIT guards, predicted full BOOT and QEMU Linux-entry boundary pass.
The initial diagnostic package (dsimdiag1) needed local QEMU socket access;
the completed dsimdiag2 package passed the full wrapper with that access. The
older candidate and its audit/patch remain historical, uninstalled artifacts. No runtime fix is claimed.

Stage 1.2 also needs a real GPU/display buffer-sharing test. Exynos GEM import
requires the entire buffer to be contiguous in DMA address space; physical-DMA
mode may reject a scattered Panfrost allocation. Source constraint alone does
not prove failure on this phone. The optional `--prime-probe` controller flag
stages `native-display-prime.c`, compiled with libdrm/GBM and warnings as errors.
After KMS, it tries one 720×1280 linear XRGB8888 buffer on each allocation path:
Panfrost render-node GBM, then display-backed GBM (including SCANOUT usage). Each
exports a DMA-BUF, imports it into an independent Exynos file description and
creates an FB object. The independent file description avoids closing a handle
owned by the GBM allocator. Failure of the first path alone does not prove IOMMU
is mandatory: the display-backed/kmsro path may allocate contiguous memory. It never attaches that
FB to a plane or changes visible pixels. The watchdog and BOOT identity guards
are unchanged. `prime.log`, `prime-display.log` and separate result records distinguish import
rejection, FB creation rejection and inconclusive allocation/format failures.
Four parser tests deliberately do not equate FB creation with scanout or desktop
performance. Host compile and shell syntax pass; both GPU allocation probes now ran, with the distinct results above. Read-only preflight confirms GBM headers and the Panfrost render node.

The phone now runs dsimdiag2. Display modules/overlay were rebuilt and pinned
to its Image/BOOT (21 merged-tree checks). The new watchdog rehearsal and native/PRIME retest passed/returned; see the
actual observations above. The shared kernel build is now the uninstalled fix,
so its next installation requires fresh module pins and a new rehearsal. The controller refused any old bl9
report against the new Image rather than refreshing its hash. Claude finished
his recovery UI tests and explicitly handed off the phone. Before updating,
Codex verified bl9 full BOOT/build ID and clear startup stamps. Recovery appeared
at .79, then the existing updater wrote BOOT and verified the entire partition.
No sound test or RECOVERY write occurred.

## RAM trial route and earlier attempts

Roadmap Stage 1 is now claimed by Codex. The owner removed the watched-trial
prerequisite, but requires automatic return to a working image. To cover a
native-probe hang before userspace could restore BOOT, the first route is now
RAM-only DT overlay on unchanged BOOT, not flashing the native-only image.
Current prepared overlay baseline: `bl9` (BOOT `40e3fde6…`, Image `2f07df10…`).
`tools/build-display-overlay.py` builds the merged native tree and the loader
plus one-shot standard DCS power-mode reader. 21 native checks, twelve host
tests, W=1 module build and warnings-as-errors host KMS compile pass. The
merged graph has the same hardware properties as displaytrial3; only display
nodes/symbols differ from baseline and all RAM reservations are preserved.
Evidence: `build/kernel/display-runtime/report.json`.

`display-trial-supervisor.py` owns the watchdog fd, never gives it to the
child, and ceases feeding at child exit/deadline while keeping the fd open.
First rehearse a real watchdog reset without native display changes. Then
`native-display-trial.sh` stops SDDM (no persistent config change), unbinds
simpledrm, loads opt-in panel/overlay, reprobes exynos-drm, and runs bounded
colour/page-flip plus DCS read/controller capture. Teardown is always a reboot
into the unchanged working BOOT, not overlay removal.

Actual hardware checkpoint: `runs/wd-bl9-03/result.json` proves watchdog reset
and return to unchanged bl9 BOOT/build ID, simpledrm and KWin/plasmashell.
The watchdog was opened with a 15-second timeout, fed for ten seconds, then
left open without feeding. Before/after boot IDs differ, and the synced final
reset marker is present. BOOT and RECOVERY were not written. The first run
also returned, but its final log marker was not persisted; the supervisor now
syncs after that marker too. A second attempt correctly refused to arm while
the GPU startup guard was pending. This checkpoint established reset/return
before native activation; the successful native result is above.

`native-bl9-01` returned automatically but stopped before firmware unbind:
`rc-service sddm stop` reported the service already stopped while its supervisor,
KWin and Plasma were still running. The guard correctly refused takeover.
The installed `/etc/conf.d/sddm` uses `supervisor=supervise-daemon`; the trial
now explicitly stops that named supervisor when SDDM remains live, then again
refuses if any SDDM/KWin/Plasma process survives. No persistent runlevel edit.
BusyBox dmesg lacks `-w`, so live capture now reads `/dev/kmsg`. Root-owned 0600
trial logs are collected with `sudo -n cat`; the first logs were recovered
without repeating the trial. This first refusal did not load or activate the
native panel.

The second run also refused: stopping the SDDM supervisor removed the elogind
session but left compositor children. Attempt 03 validated the exact local
Wayland `sddm-autologin` `/c1` cgroup, verified the trial and watchdog were not in
it, and stopped remaining GUI children with that cgroup's `cgroup.kill`.
Four scratch-file tests of the actual shell guard reject root/other scopes,
non-Wayland/SSH sessions, and scopes containing the supervisor or trial.
It then reached firmware unbind and the opt-in overlay loader.

The first actual loader error was `OF: overlay: Invalid overlay_fdt header`,
`result=-22`. The DTBO bytes were valid but its embedded C array had no
8-byte alignment: actual AArch64 symbol offset was `0x1e`. libfdt rejects any
FDT pointer not aligned to eight bytes before it copies the blob. The generated
array now uses `__aligned(8)`; actual symbol offset `0x20`, `.rodata` alignment
8. Builder checks the module symbol. Two tests check actual module alignment
and real host libfdt acceptance of the generated array versus rejection of a
misaligned copy. W=1 module rebuild and 21 tree checks pass. Attempt 03 returned
to unchanged BOOT/Plasma; no native modeset occurred. Attempt 04 uses the fixed
module. No shared kernel Image rebuild or partition write was needed.

The host controller `tools/run-native-display-trial.py` additionally pins the
running GNU kernel build ID (not only its shared release string), checks the
entire BOOT partition hash, waits out the delayed startup guards, and requires
the successful reset rehearsal report before native mode. Return verification
includes the original simpledrm driver and both KWin/plasmashell processes.
The controller separately evaluates native hardware evidence: 120 flip events,
DCS answer, new DECON framebuffer address, DSIM resolution/porches and disabled
SysMMU. Six evidence/guard tests pass, including refusal to count the actual old
firmware register capture as native success. Safe reset alone cannot complete
the native trial. Current host coverage is 12 loader/tree/supervisor tests plus
six evidence/guard, four scope and two alignment tests. The GPU job starts after 40 seconds and holds
its stamp for another 180 seconds; the controller requires at least 240 seconds
uptime and no pending stamps before arming. An early empty stamp list is not
enough. Persistent stamps refuse the trial rather than being deleted.
Light read-only SSH preflight now confirms actual running build ID
`900acd1f4637fb3b9245bc0545cf74c09d2de703` equals the prepared bl9 modules and
`keep_on_shutdown=Y`. Evidence: `display-runtime/read-only-kernel-preflight.json`.
That earlier check did not prove watchdog reset or native output; the later
rehearsal above now proves reset and return. Logs and after-reset pstore are
retained per unique run label. The handoff wait completed and the bounded
trials returned to the working baseline. No partition mutation was performed.

The following flash candidate checkpoint is historical after bl8; its previous
BOOT guard correctly refuses the newer slot.

Latest offline checkpoint: Claude rebased the trial on the suspend layer as
`display-prepared2.dts` / `display-trial2.dts` and prepared `displaytrial3`.
Codex independently rechecked 24 native/FIT checks, actual Samsung container
and embedded loader/FIT pairing, full BOOT tail prediction, previous-slot guard
and exact kernel/initramfs equality with `bl7`. Candidate SHA
`d797482febef7e9b0bcc77672e21a2860841e02ce5baf74ee152ec26dce04106`;
previous BOOT SHA `25ae86fb1d8641c86b182a345d295d49f6ffb62380203123a43f1bb063fb7952`.
Evidence: `build/kernel/boot-update-displaytrial3/codex-package-audit.json`.
It remains uninstalled. Earlier trial1/2 checkpoints below are historical.
The current software-backlight framebuffer layer is deliberately absent from
the native tree; no native brightness control is implemented. Phone access
must still be coordinated before any bounded hardware trial.

The first standalone EA8061S J7VE DRM panel prototype is in
`tools/kmod/ea8061s/panel-j701f-ea8061s.c`. It builds against the installed
`7.1.13-BURAK-PANFROST-01` configuration with `W=1`. It was temporarily loaded
for the successful RAM trial above; it is **not a daily display driver**.
The normal running phone still uses simpledrm and the bootloader's scanout.
A separate read-only diagnostic
module was temporarily uploaded, loaded and removed on 2026-10-10; no display,
clock or MMU register was written. Its temporary file was removed as well.

The module requires `allow_init=1` before its probe acquires any panel resources.
There is no matching panel node in the active device tree and no autoload entry.
The first implementation reproduces the vendor's fixed initial gamma, not the
factory-MTP-calibrated final brightness sequence. It exposes no backlight yet.

## Evidence and sources

| Input | Location / result |
| --- | --- |
| Running vendor configuration | `kernel/configs/vendor-running.config`: `CONFIG_PANEL_EA8061S_J7VE=y` |
| Vendor implementation selected by that option | `build/kernel/vendor-panel-reference/drivers/video/fbdev/exynos/decon_7870/panels/Makefile`: `ea8061s_j7lite_lcd_ctrl.o` and dynamic dimming helpers |
| GPLv2 reference commit | SIMPLE `29223d295a58ebe82e95347c8eb8468ea2b1c336`, pinned archive in `kernel/inputs.json` |
| Vendor parameter / controller files | `ea8061s_j7lite_param.h`, `ea8061s_j7lite_lcd_ctrl.c` in that reference directory |
| Captured device tree | `build/kernel/j701f-live.dtb` and its decompiled `.dts` |
| Vendor timing parser and DSIM programming | Extracted from the pinned archive to `build/kernel/ea8061s-prototype/reference/` |
| Mainline clock snapshot | `build/kernel/ea8061s-prototype/mainline-clock-snapshot.txt` |
| Live display register snapshot | `build/kernel/ea8061s-prototype/phone-display-state.txt`, confirmed `DISPLAY_READONLY_PROBE_UNLOADED` |
| Build and module metadata | `build/kernel/ea8061s-prototype/build.log`, `report.json`, `panel-j701f-ea8061s.ko`, `j701f-display-info.ko` |
| Independent command fixture | `tests/fixtures/ea8061s-j7ve-init.json`, including hashes of both vendor source files |

The panel's `timing,h-porch` and `timing,v-porch` arrays are **back, front,
sync**, as verified in `dsim_parse_lcd_info()` in the vendor `dsim_drv.c`.
Copying them into DRM as front/back would silently reverse the porches.

| Parameter | Value |
| --- | --- |
| Resolution / nominal refresh | 720 × 1280, 60 Hz |
| Physical dimensions | 68 × 121 mm |
| Horizontal back / front / sync | 48 / 56 / 4 pixels |
| Vertical back / front / sync | 5 / 9 / 2 lines |
| Totals / calculated DRM pixel clock | 828 × 1296, 64,385 kHz |
| DSI | Four lanes, RGB888, video burst; vendor suppresses HFP packets |
| Requested HS / escape clocks | 477 MHz / 16 MHz |
| Vendor PLL P / M / S | 3 / 220 / 2 |
| Reset | `decon_board/gpio_lcd_rst` = gpd3-4; active low |
| Power | LCD_1P8 = LDO30; LCD_3P0 = LDO29 |

Do **not** use `ea8061s_hd/gpios` as the reset: that property points at gpd3-5.
The vendor's board action sequences explicitly use `gpio_lcd_rst` on gpd3-4,
with raw HIGH/LOW/HIGH and 5/5/10 ms delays. Power-up enables 1.8 V, then 3.0 V,
then waits 25 ms. The prototype uses ordered regulator calls and acquires reset
with `GPIOD_ASIS`, so acquisition itself does not pulse it.

The mainline snapshot reports DECON VCLK / DISPAUD PLL at 64 MHz, ECLK at
199.875 MHz, APB at 99.9375 MHz, and the audio PLL at 98,304,019 Hz. The
`frat_dispaud_mipiphy_*` roots report 188 MHz; these are fixed-rate clock
definitions, **not a measurement of the actual DSI lane rate**.

### Live register evidence (2026-10-10)

The guarded `tools/capture-display-state.py` helper requires the phone lock,
matching kernel/module hashes and the pinned SSH host key. It loads only the
read-only diagnostic, saves the register log and confirms module removal.

| Register | Captured value | Interpretation |
| --- | --- | --- |
| DISPAUD STATUS | `0x0003000f` | Domain on; low four status bits set |
| DECON buffer start | `0x67000000` | Firmware framebuffer physical address |
| DECON timing 0–4 | `00040008`, `00010000`, `002f0037`, `00030000`, `04ff02cf` | 720×1280; back/front/sync 48/56/4 and 5/9/2, using count-minus-one fields |
| DSIM resolution | `0x050002d0` | 720×1280 |
| DSIM PLLCTRL | `0x008066e2` | PLL enabled; P=3, M=220, S=2 |
| DSIM CONFIG | `0x2444747f` | Video burst, RGB888, four lanes, HFP disabled; **HSYNC_PRESERVE clear** |
| Display SysMMU CTRL / STATUS | `0x00000000` / `0x00000000` | Translation disabled at capture |
| Display SysMMU CONFIG / VERSION | `0x00100000` / `0x60020044` | Configuration retained; kernel decoder reports version 6.0 (`reg >> 21`, then major/minor split at bit 7) |

With a 26 MHz input, the PLL fields calculate to 476.667 MHz lane bit rate;
this is a calculation from register values, not an oscilloscope measurement.
The live HSYNC_PRESERVE bit differs from the vendor DT request of 1, so the
working firmware state takes precedence over blindly copying that request.
The first isolated display trial can retain the existing physical-DMA setup
and disabled SysMMU. Proper IOMMU support remains a later, separate change;
this one snapshot does not establish its state after other resets or images.

### DSIM programming discrepancies found before activation

#### PLL completion and coalesced interrupt fix

The imported `exynos7870-7.1/04-21b89c2f.patch` has a definite software bug:
`wait_for_completion_timeout()` returns nonzero on success, but the new PLL
code rejects that result and accepts zero (timeout). Its reset IRQ mask also
omits PLL_STABLE, and returning immediately after a PLL event discards any
simultaneous RX/FIFO event already acknowledged in INTSRC.

`kernel/patches/linux-dsim-pll-wait-fix.patch` corrects these three paths. It
is now an active **build input**, applied by the shared builder. Claude's later
`pfshrink2` package uses the same PLL-fixed Image SHA below; its full BOOT
readback is recorded, while runtime testing belongs to Claude. DSIM remains
disabled in that charger-stage image, so this bug does not explain the current
browser's black tiles.

Six host test methods compile the actual patched wait branch and IRQ handler,
covering success, timeout, reset unmasking, combined RX/FIFO/PLL/reset events
and a spurious interrupt. An isolated AArch64 `W=1` object build passed;
`checkpatch --no-signoff` reported zero warnings/errors. The full kernel
rebuild passed, with Image SHA256
`36226d2232605595b598c5db63f00b35d971c2e456dc163e7e2170239f34c5ca`.
This is compile/software evidence, not proof of real PLL lock or panel output.

```sh
python3 -m unittest discover -s tests -p test_dsim_pll_completion.py -v
```

The SHA above identifies the first PLL-only build. Its immutable evidence is
`build/kernel/ea8061s-prototype/dsim-pll-fix-report.json`; the shared
`build/kernel/panfrost/report.json` now describes later builds with the init and
opt-in timing changes too. The isolated log is
`build/kernel/ea8061s-prototype/dsim-pll-compile/build.log`.
The snapshot in `reference/mainline/samsung-dsim.c` intentionally remains the
pre-fix source, so regressions can apply the correction to it with zero fuzz.

#### Horizontal, vertical and VCO differences

The actual `samsung_dsim_set_display_mode()` routine was compiled in a host
register mock using the prepared source snapshot. At the panel's mode and
476.667 MHz HS clock, the common conversion writes HFP/HBP/HSA=46/39/0,
whereas both the captured firmware registers and Samsung's
`dsim_reg_set_porch()` use **56/48/4** directly.

`kernel/patches/linux-dsim-j701f-timing-trial.patch` now supplies an
**experimental, default-off J701F-only** profile. It is a build input and
has compiled into the kernel, but has not been hardware-tested or flashed.
Six host methods execute the actual current/patched mode and atomic-check
routines: horizontal and vertical register matches, other-hardware/default-off
behaviour, board restriction, valid boundaries and invalid VFP rejection.
An isolated AArch64 `W=1` build and `checkpatch --no-signoff` pass.

The profile writes the captured DSIM VPORCH=`0x60010005` (command-allow=6,
stable-VFP=1, VBP=5) rather than the common routine's `0xf0090005`. It restricts
VFP to 3–18 to keep the vendor command budget representable in four bits.

Enable it **only with no native graphical session active, before panel load**,
via the root-only parameter:
`/sys/module/samsung_dsim/parameters/j701f_vendor_timing` (0600).
The bootloader explicitly overrides DT bootargs, so changing a DT bootarg alone
would not enable this profile. Its default is false. The helper also requires
Exynos7870 and the `samsung,j7velte` machine compatible.

The PLL limits stay unchanged. A host harness executes the actual existing
PLL search with its source-defined limits and finds **P=3/M=110/S=1**, output
476,666,666 Hz for the 477 MHz request. Its VCO is 953.333 MHz, within the
existing 500–1500 MHz range; the firmware's P=3/M=220/S=2 has the same output
ratio but a different VCO. Three search tests pass. This proves arithmetic and
bounds only; analogue stability must be measured on the phone. No limit was
raised to reproduce the firmware's higher VCO.

```sh
python3 -m unittest discover -s tests -p test_dsim7870_porches.py -v
python3 -m unittest discover -s tests -p test_dsim_pll_search.py -v
```

#### Host initialisation error handling

`kernel/patches/linux-dsim-init-errors.patch` is also now a compiled build input,
included in the later recorded `pfshrink3` package with native DSIM disabled.
The previous init routine ignored clock/PLL and link failures,
and reset timeout was only logged; it then marked the host INITIALIZED and
allowed transfers. It now returns the original error and unwinds the IRQ and
DSIM clock state. Four actual-C host methods inject all three failures, test
retry/resource balance, normal idempotence and the functional-reset path.
The successful ordering is unchanged. The full AArch64 build passes.

```sh
python3 -m unittest discover -s tests -p test_dsim_init_errors.py -v
```

### First takeover route

For an isolated first boot image, explicitly disable the simple-framebuffer
**device node**, retaining its reserved RAM and ramoops. This avoids depending
on an aperture-removal call that the Exynos DRM source does not currently
make. Keep SysMMU disabled and the panel module manual/opt-in. Do not attempt
to keep a live simpledrm compositor writing while DECON binds: its bind path
already clears enabled channels, before panel initialisation succeeds.

Confirm SSH/USB rescue and stop automatic graphical-session startup for this
trial; then load the panel with `allow_init=1`, enumerate the native connector,
and run a bounded colour/page-flip test before starting Plasma on that device.
The initial image may have no working on-screen console until the panel is
loaded. `kernel/dts/exynos7870-j7velte-display-trial.dts` implements this
separate trial wiring. It is not the installed top. `tools/validate-display-trial.py`
checks native controller state, graph/supplies/reset, physical DMA, reserved RAM,
compiled opt-in parameter and panel/probe hashes in addition to the existing
board verifier. Visible output still needs a watched hardware trial.

## Checks completed

### Packaged trial checkpoint

`build/kernel/boot-update-displaytrial1/boot-mainline.img` is prepared, **not
flashed**. `display-trial-summary.json` beside it pins the candidate, kernel,
DTB and DSIM patch hashes and points to evidence. The candidate SHA256 is
`b3e7eab3251c29633f45d2c755d8dd30c27f7c62536672ff96225e0b1f75c079`.

- Full project suite: 132 tests run, OK with one skipped.
- QEMU reaches the first Linux instruction with the expected ARM64 header.
  This does not emulate Exynos display hardware or execute the kernel.
- The packaged DTB passes 20 native-display software checks plus the existing
  memory/PMIC/PSCI verifier. Four deliberately invalid DTBs (simpledrm still
  enabled, SysMMU enabled, wrong reset pin, wrong ramoops address) are refused.
- The initial combined packaging command stopped because the sandbox denied
  QEMU's local GDB socket, before emulation began. Re-running that trace with
  the socket permitted passed; tests and BOOT-update preparation then finished.
  The final summary records these completed checks, not the initial failed run.

No visible-output or performance claim follows from this checkpoint. Before
execution, revalidate the package and current BOOT rollback identity, take the
phone lock, arrange the bounded rescue path, and stop the graphical session.
The installed top remains charger. While this package was prepared, Claude
wrote `pfshrink2` with full BOOT readback. The trial's update manifest was then
regenerated against that verified partition image (SHA
`4c0943adca34f11a4101767db78c03b743db44f9316953d69356d9848deaabea`).
Codex has not independently verified that new image's running session;
coordinate with Claude before any phone trial.

Subsequent refresh: `pfshrink3` is now the recorded BOOT, with full partition
SHA `fe691403c93b56e1d1e7f6d1deb05ee8d0b96434b5b1471c773a926cb00aa41e` and
`MAINLINE_BOOT_UPDATE_FULL_READBACK_VERIFIED` in its phone-update log. Its kernel
(`60e883...`) and initramfs hashes exactly match `displaytrial1`; a second kernel
build is unnecessary. Rebuilt panel/probe modules and 20 native validation
checks pass. Refreshed the trial's update guard against this new partition;
candidate bytes/hash are unchanged. A cheap read-only SSH check saw the
expected kernel release, `shrinker_purge=1` and 126 seconds uptime; it does not
attest a running full Image hash. The native trial remains uninstalled.

### FIT provenance after the next GPU revision

Claude subsequently recorded `pfshrink4` (BOOT SHA `66fc1c71...`), with kernel
Image SHA `b710b5dd8c71db7838d1a03434f90fbab15c3cab35d4c981cd75fe79d2390976`.
The old `displaytrial1` Samsung container is now a historical checkpoint and
must not be refreshed blindly to the new BOOT hash: that would remove the newer
GPU change. Its old previous-BOOT guard remains in place to reject execution.

`tools/build-display-prototype.py` now records the actual Image and Module.symvers
hash used for its module build. `tools/validate-display-trial.py` requires that
Image/config provenance, and accepts `--handoff-dir` to check actual FIT contents
against the current Image, exact trial DTB and initramfs. With no FIT argument,
its report explicitly says it checks DTB/current build only, not a package.

New FIT: `build/kernel/handoff-displaytrial2/`.
It uses the new GPU Image and existing native trial DTB; 24 software checks pass.
Three negative cases are rejected: old kernel FIT, damaged FIT with the old
report, and damaged compressed kernel even after updating the outer FIT hash.
Evidence: `build/kernel/ea8061s-prototype/provenance-negative-tests.json`.
The subsequent Samsung BOOT package is now complete under
`build/kernel/boot-update-displaytrial2/`, candidate SHA
`d03917a8c93863c69754aa400ca78d127fd04cababd40d9299ed1bfb1e8a280f`.
QEMU reaches the first Linux instruction, and the full suite passes 146 tests
(one skipped). The update guard expects the recorded `pfshrink4` BOOT. This
package is **not installed and not hardware-validated**. Before a watched trial,
recheck the then-current GPU kernel and BOOT record and establish bounded rescue.

### Panel checks

- Out-of-tree AArch64 module compilation with `W=1`, using the existing resolved
  config hash `a916be80711b7aafae361ac872b36b92e7c41fa815422748128bea733faea853`.
- Kernel `checkpatch.pl`: zero errors and zero warnings.
- The actual C initialisation routine is compiled into a host mock transport
  under AddressSanitizer and UndefinedBehaviorSanitizer. Its 19 writes match
  the independently extracted vendor fixture byte for byte and in order.
- The four waits inside that routine match the vendor's 5 ms, 10 ms, 10 ms,
  150 ms sequence.
- A transfer error injected at each of the 19 writes stops subsequent init
  commands and independently attempts to lock both F0 and FC command keys.
- A second harness compiles the actual power/reset and display callbacks. It
  checks ordered rail enables, reset timing, balanced teardown, all initial
  transfer failures, four enable failures, three resource failures, sleep-in
  failure and repeated cycles. It caught a GPIO write after a failed direction
  change; the driver now guards that write. Rail-disable failure recovery is
  not modelled by the harness.

Repeat the host checks:

```sh
python3 -m unittest discover -s tests -p 'test_ea8061s_*.py' -v
```

These checks do not prove that the panel accepts the commands, that its
brightness is suitable, or that DECON can display a frame.

Rebuild the modules while holding the shared build lock:

```sh
tools/coord.sh inbox codex
tools/coord.sh lock kbuild codex "build display prototypes"
python3 tools/build-display-prototype.py
tools/coord.sh unlock kbuild codex
```

The builder checks the worker's unexpired lock, pinned resolved configuration
and AArch64 ELF outputs, and writes generated files under `build/`. It performs
no phone operation. If it fails, release the lock after inspecting `build.log`.

The disabled wiring candidate is
`kernel/dts/exynos7870-j7velte-display-prepared.dts`. Its compiled DTB is in
`build/kernel/j701f-display-prepared/`, with `wiring-validation.json`: all three
controllers stay disabled, simpledrm stays enabled, both supplies/reset resolve
to the measured pins/regulators, and the DSI graph and clock properties pass.
It is not an activation image and does not replace the installed charger top.

`j701f-display-info.c` is a separate one-shot diagnostic, not a panel driver.
It reads only a fixed list of known DECON/DSIM configuration registers and
SysMMU CTRL/CONFIG/STATUS/VERSION, after checking the J7velte compatible and
DISPAUD-on status. SysMMU STATUS is at **0x08**, CONFIG at 0x04. No FIFO or
interrupt-status registers are read and no MMIO register is written. The guard
does not prove the availability of every clock; first loading is coordinated
through the phone lock while firmware scanout is active. It is not autoloaded.

## Integration still required

### Additional DECON audit (offline)

The pinned Samsung header defines `VCLKCON_CLKVAL_F` at bits 16–23, whereas
the common mainline Exynos7 helper uses bits 0–7 for both SoCs. Prepared
`kernel/patches/staged/linux-decon7870-vclkdiv.patch` adds a per-SoC shift and
leaves Exynos7 unchanged. It is **staged, not an automatic build input and not
in displaytrial1**. Six actual-C commit tests pass under address/UB sanitizers:
the 7870 field, common-SoC preservation, divide-one, clamp, captured timing
words and an unset mode producing no writes.

A read-only CCF clock-summary check reported DECON VCLK 64 MHz and ECLK
199.875 MHz. At the prepared mode's 64.385 MHz target, the existing calculation
selects divide-one and skips the mismatched register write, so this finding
does not explain today's simpledrm performance. CCF is a software clock model,
not a physical frequency measurement. Vendor `decon_reg_set_clkval()` only
sets CLKVALUP and ignores its divider argument. The actual divider behaviour
and effect of a changed parent rate therefore still need hardware evidence.

The shared timing, geometry, stride/offset and RGB format fields match the
vendor definitions. Firmware WINCON0 was `0x1e001` (ARGB mode with window
enabled), despite the early fbdev channel description; a native colour test
must use explicit DRM formats. The generic driver's bit-18 triple-buffer OR
has no named equivalent in the pinned 7870 header. Absence from that header
alone does not prove it is unsupported; leave this as an integration question,
not a demonstrated defect. No register or clock setting was changed here.

1. Initial read-only capture is complete. Repeat known-register checks if the
   boot image or power/reset path changes; do not dump the PMU or debugfs regmap.
2. Keep physical DMA and SysMMU disabled for the first isolated display stage,
   consistent with the captured state and current `CONFIG_EXYNOS_IOMMU=n`.
   No bypass write is needed for this measured state. Preserve all framebuffer,
   ramoops and other reserved-memory protections. Enabling proper IOMMU support
   later needs its own address mapping and boot/framebuffer takeover plan.
3. Advance the disabled wiring candidate to a separate activation stage only
   after software timing checks. The separate trial top is now prepared; its
   graph, supplies, active-low gpd3-4 and explicit
   26 MHz PLL input, 477 MHz burst / 16 MHz escape requests are prepared.
   Do not replace the installed top in `STATE.md` merely because a candidate
   was prepared.
4. Plan takeover from simpledrm before the first modeset. Determine how the
   Exynos DRM aperture removal and compositor device selection work here;
   do not assume that loading the panel automatically hands over the display.
   Source review found no aperture-removal call in this Exynos DRM driver.
   Its bind path clears DECON channels, so deferred panel loading alone is
   not a promise that the firmware picture will survive controller binding.
5. Compare a colour pattern, frame timing, repeated page flips and recovery
   behaviour. The newer approved roadmap permits unattended trials, provided
   automatic return to the working image is proved. Record physical appearance
   as unseen unless the owner reports it; an old proximity reading does not
   establish where the phone is now.
6. Port calibrated gamma / AID / ELVSS brightness after scanout is established.
   A generic DCS `0x51` backlight is not a substitute for this panel's vendor
   dimming implementation. Blank/unblank and suspend are later stages.

DISPAUD also contains audio. Do not cycle the whole power domain or reset its
clock tree to bring up the display. The prototype touches panel supplies and
reset only; DECON/DSIM host behaviour still needs review. No audible test is
allowed, including incidental audio while testing video or a browser.

## Relationship to optimisation

Real DECON scanout is intended to provide page flips/vblank and avoid the
current simpledrm shadow-copy presentation path. It is not yet a measured
performance improvement. Compare the same scene, scale, clocks and session
before and after, recording frame intervals, CPU time and memory.

Claude owns the parallel phone-side optimisation work. His first Angelfish
capture showed repeated Panfrost purge/import warnings during memory pressure;
the relationship to black browser tiles needs an A/B test. A new display driver
must not be presented as a fix for that separate buffer-lifetime issue.

<!-- CODEX-END 2026-10-10 -->
