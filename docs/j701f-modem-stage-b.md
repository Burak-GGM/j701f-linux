# CP Stage B: bounded first power/start trial (2026-10-28, Codex)

This is an **offline review**, not a phone result. Stage A copied BOOT/MAIN to
the reserved CP window and the secure monitor accepted the security request.
There is no proven CP execution or IPC handshake yet. Claude owns the Stage A
module `tools/kmod/cp-boot/`; its code must be handed off before Stage B changes.

## Correct SMC contract

The vendor `pmu-cp.c` uses SMC `0x82000700` command 3 for control reads, and
command 4 for writes. Its read checks `a0 & 0xffff`: a nonzero low half-word
is an **error**, while a successful control value is `a0 >> 16`. The earlier
raw `a0=0xb` was error 11, not a register value. After Stage A the raw
`a0=0x06a00000` decodes to CP_CTRL_NS `0x06a0`, whose `PWRON` bit 1 is clear.
The separate CP_CTRL_S register has not been read; do not infer its `START`
bit 3 from the NS read. Never use a raw SMC return in a read-modify-write.

For a write, check the vendor's returned status (`>0` is failure in its
helper) and read the same control register again. Refuse to proceed if the
pre-read fails, reports unexpected power/start state, or the security call
did not succeed in this boot. The Stage A module currently prints the raw
SMC result without interpreting it; the first modification after handoff
should correct that and record both NS and S before any write.

Source: pinned [Samsung PMU CP driver](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/29223d295a58ebe82e95347c8eb8468ea2b1c336/drivers/soc/samsung/pmu-cp.c)
and [control definitions](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/29223d295a58ebe82e95347c8eb8468ea2b1c336/include/soc/samsung/pmu-cp.h).

## Vendor normal-power sequence to reproduce carefully

The factory J701F device tree identifies a 4 KiB `deliver_cp` region at
physical `0xAFFFF000`, a 120 MiB modem reservation at `0xB0000000`, and its
4 MiB IPC tail at `0xB7400000`. The mailbox is at `0x10500000`. The stock
`ss310ap_on()` clears 64 mailbox scratch registers, sets board info in index
33, copies the first `0x800` bytes of `deliver_cp` to IPC offset `0x1000`,
sets AP active in mailbox index 6, then powers the CP if off (NS `PWRON`
bit 1, S `START` bit 3) through SMC. It sleeps 300 ms and calls
`change_cp_pmu_manual_reset()`. On this factory config the latter is compiled
as a no-op because `CONFIG_REGULATOR_S2MPU01A` is absent. `ss310ap_boot_on()`
then polls CP status at mailbox index 5 for at most about 1–2 seconds.

The board info value combines hardware revision with a dual-SIM-detect GPIO
bit. The mainline boot does not provide Android's `androidboot.revision`
argument, and the GPIO has not been measured under mainline. Do not guess a
permanent value. Before a live trial, read-only inspect the GPIO and the
current `deliver_cp` bytes, verify the expected reservations in the running
device tree, and determine whether a copied bootloader block is actually
present. A zero/uninitialised block is a reason to stop; it is not safe to
fabricate this handoff content.

The first active trial should be one-shot and opt-in, with a short maximum
runtime and the normal Linux BOOT left unchanged. Prepare mailbox status and
interrupt handling **before** asserting CP start. Sample only metadata:
SMC return/status, mailbox status/active/message, pending interrupt bits and
bounded IPC control words. Do not dump firmware, NV, identifiers or SIPC
payloads. On timeout or test completion, clear CP power via the vendor SMC
path and verify that `PWRON` is clear. Do not autoretry, autoload at boot,
request cellular service, or attempt voice/audio.

The first success criterion is modest: CP status becomes nonzero or a boot
message arrives without an AP crash, then the trial powers the CP off and
ordinary Linux remains usable. Full FMT/RFS and `CMD_INIT_END` follow only
after a stable mailbox/IPC path. The vendor driver requires both FMT and RFS
open before sending `CMD_INIT_END`; sending it early would give a misleading
or stalled boot result. Do not call CP online based solely on mailbox status.

Sources: pinned [SS310AP control](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/29223d295a58ebe82e95347c8eb8468ea2b1c336/drivers/misc/modem_v1/modem_ctrl_ss310ap.c),
[shared-memory link](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/29223d295a58ebe82e95347c8eb8468ea2b1c336/drivers/misc/modem_v1/link_device_shmem.c),
and [MCU mailbox driver](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/29223d295a58ebe82e95347c8eb8468ea2b1c336/drivers/misc/mcu_ipc/mcu_ipc.c).
