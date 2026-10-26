# Panfrost board integration — 2026-10-08

The Linux 6.15 research build contains Panfrost, but the running phone still has the vendor 3.18 kernel and `/dev/mali0`. A read-only check found no DRM render nodes. The GPU was powered off during the snapshot, while the framebuffer terminal remained usable. The current GUI therefore does not demonstrate GPU acceleration.

The [Mesa driver supports Mali-T830](https://docs.mesa3d.org/drivers/panfrost.html), including OpenGL ES 3.1. That describes the driver/GPU family, not an established capability of this handset's current Linux port. Mali handles rendering; the Exynos display controller and actual panel need their own KMS integration.

## Measured and source-backed requirements

`kernel/j701f-gpu-evidence.json` records a non-identifying subset of the live vendor tree and GPU sysfs. `tools/j701f-gpu-evidence.py` regenerates it from local captures and checks that the vendor ASV/DVFS tables agree. It does not generate or enable mainline operating points.

| Requirement | Evidence | Remaining integration |
| --- | --- | --- |
| GPU registers and interrupts | Live GPU range `0x11400000`, size `0x5000`; job/MMU/GPU SPIs 282/283/281 match the pinned modern SoC tree. | Probe Panfrost on hardware and validate interrupt delivery. |
| GPU clocks | Modern SoC tree supplies `core` and `bus` from CMU G3D at `0x11460000`. | Coordinate provider probing and runtime PM with the G3D power domain before accessing its registers. |
| GPU supply | Running IKCONFIG selects Mali r28p0. The corresponding related SIMPLE source calls `regulator_get(NULL, "BUCK2")`. Live GPU `vol` and regulator readings both report 662,500 µV. | `mali-supply = <&vdd_buck2>` is now described on the **disabled** GPU node. This is source/runtime mapping evidence, not independent physical wiring verification. |
| Power domain | The live GPU phandle resolves to `pd-g3d@10484000`, size `0x20`. Vendor code uses Samsung's power/calibration interfaces. | The pinned modern generic Exynos domain driver matches only Exynos4210/5433. No Exynos7870 power-domain description/provider exists in this port. Port the actual sequence; a matching status mask alone does not justify borrowing another SoC compatible. |
| PMIC external control | Live PMIC properties include `g3d_en=1`, `buck2en_pin="etc1-3"`. | Audit the vendor GPIO/DVS/PMIC sequence against modern S2MPU05 handling. The modern driver's S2MPS14 external-control helper does not establish S2MPU05 BUCK2 support. |
| Frequency and voltage policy | The live driver exposes seven ASV-adjusted entries, listed below. | Preserve voltage margins and power/clock ordering, account for memory/interconnect QoS and establish an appropriate initial clock. These readings are not a portable OPP table or a validated mainline policy. |
| Display | Vendor framebuffer and software GUI work; diagnostic display/GPU remain disabled. | Exynos DECON/DSI, actual EA8061S J7VE panel, touch and buffer-sharing integration precede a Wayland compositor/Plasma Mobile. |

The selected vendor source is commit `29223d295a58ebe82e95347c8eb8468ea2b1c336`. Its `drivers/gpu/arm/t83x/r28p0/platform/exynos/gpu_exynos7870.c` SHA-256 is `bcb1668aaf31c30b18ad99144dc7940c70a854fcd837a11d32cb9313bcfe2a2e`. Source snapshots and hashes remain in ignored `build/kernel/vendor-gpu-reference-r28p0/`. The file's old r7p0 path in its comment is inherited upstream; the archive path and running configuration select r28p0. The source is related to the binary, not an attested exact reconstruction.

The observed ASV values from this handset/vendor kernel are:

| Reported clock (MHz) | Reported voltage (µV) |
| --- | --- |
| 343 | 600,000 |
| 450 | 637,500 |
| 545 | 681,250 |
| 676 | 743,750 |
| 728 | 762,500 |
| 845 | 837,500 |
| 1001 | 931,250 |

These are configured vendor entries, not measured stable performance under load or recommended clock settings. The instantaneous snapshot reports `power_state=0`, `clock=0`; BUCK2 remains supplied. No clocks or voltages were changed to obtain it.

## Diagnostic changes

Disabling the GPU consumer alone did not disable its clock provider. The pinned CMU driver probes independently and invokes a helper which reads/writes gate registers. The first USB/RAM tree now also disables CMU G3D, DISPAUD, ISP and MFCMSCL, whose consumers are outside that trial. MIF, FSYS and PERI remain for the diagnostic USB, PMIC I2C and UART paths.

The board verifier checks those four provider statuses, measured GPU registers/interrupt ordering and the disabled GPU's BUCK2 supply phandle. Two additional negative tests reject re-enabling CMU G3D or substituting an unrelated rail. The rebuilt diagnostic was subsequently flashed into RECOVERY under the user's explicit authorization. Its first boot trial gave no diagnostic USB console or return to normal SSH; successful execution remains unverified. See [the flash evidence and recovery route](j701f-mainline.md#first-authorized-recovery-flash-and-boot-trial).

## A rendering proof prepared for the next stage

`tools/panfrost-render-probe.c` inspects DRM identity by default. With `--render`, it requires an accessible **Panfrost render node**, creates a GBM/EGL surfaceless GLES context, rejects a renderer other than Mali-T830/Panfrost, runs a checkerboard fragment shader into a 64×64 texture and verifies all 4,096 RGBA pixels. It never opens a display or touch device. Its 15-second alarm bounds ordinary execution; it is not a kernel watchdog or recovery mechanism.

This uses the [Khronos surfaceless-context interface](https://registry.khronos.org/EGL/extensions/KHR/EGL_KHR_surfaceless_context.txt) and an OpenGL framebuffer object. A headless rendering pass would prove that narrow rendering path; it would not establish panel scanout, sustained performance, suspend/resume or Plasma readiness.

Build on Alpine using the already available development dependencies:

```sh
cc -O2 -Wall -Wextra -Werror tools/panfrost-render-probe.c \
  $(pkg-config --cflags --libs egl glesv2 gbm libdrm) -o panfrost-render-probe
./panfrost-render-probe --inspect
# After mainline boot, power/clock integration and render-node validation:
./panfrost-render-probe --render --device /dev/dri/renderD128
```

Success markers distinguish identity, software pipeline and hardware rendering:

- `PANFROST_UNAVAILABLE` (exit 2): no accessible Panfrost DRM node; no rendering was attempted.
- `PANFROST_DRM_IDENTITY_FOUND`: driver identity only; acceleration is unverified.
- `PIPELINE_SELF_TEST_PASS`: shader/readback test passed; `hardware_verified=false`.
- `PANFROST_T830_RENDER_PASS`: the hardware identity/renderer checks and shader pixel verification passed.

`tools/validate-panfrost-probe.py --phone 192.168.1.140` compiled the program natively in the phone's existing `/tmp` tmpfs, inspected DRM and ran only `LIBGL_ALWAYS_SOFTWARE=1 ... --self-test`. It reported no Panfrost node, then passed the shader test with llvmpipe/LLVM 22.1.3 and confirmed cleanup. No on-screen GUI, input device, hardware render request, persistent file or partition was changed. The host also passed the software pipeline test with llvmpipe/LLVM 22.1.8. Reports live in `build/kernel/phone-panfrost-probe-validation.txt` and `panfrost-probe-validation-report.json`.

The next hardware gates remain basic mainline USB/RAM boot, CPU startup, G3D power/clock/PMIC integration and an actual Panfrost render node. Only then can the prepared hardware rendering probe establish acceleration.

<!-- CLAUDE-BEGIN 2026-10-08: written by Claude (Anthropic), not ChatGPT Codex -->
## Update: hardware rendering verified on 2026-10-08

Everything above describes the state before mainline booted. Since then Linux 6.15 runs the installed Alpine system from the RECOVERY slot, Panfrost probes the Mali-T830 at 343 MHz, and `panfrost-render-probe --render` returned `PANFROST_T830_RENDER_PASS` with `GL_RENDERER=Mali-T830 MC1 (Panfrost)`. The G3D power domain needed no driver for this: S-BOOT leaves it on (`PMU 0x10484000 = 0xf`). Evidence, limits and next steps: the Claude section at the end of [j701f-mainline.md](j701f-mainline.md).
<!-- CLAUDE-END 2026-10-08 -->
