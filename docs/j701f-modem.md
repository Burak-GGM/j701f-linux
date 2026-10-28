# J701F modem bring-up (2026-10-28, Codex)

Status: diagnostic preparation only. Calls, SMS and mobile data do not work. A
read-only one-shot state module was loaded once and exited; no CP firmware was
sent, no modem service was started, and no partition was changed. The parser
passed against the header
of the local SM-J701F factory CP package: decompressed image 38,830,512 bytes;
BOOT at 512 for 5,900 bytes, MAIN at 6,432 for 0x0250677c bytes, NV external,
OFFSET contained within MAIN. Only the 512-byte header was retained under
ignored `build/modem/`. On 2026-10-28 Claude read exactly 512 bytes from the
phone's RADIO partition through USB serial, read-only. The installed RADIO is
92,274,688 bytes, passed the same validator, and its header was byte-identical
to the factory header. No EFS access was made. The modem has no SIM inserted
according to the last recorded check.

## Evidence and boundaries

- The factory device tree calls this integrated CP `ss315ap`. The host-CP
  interface is shared memory plus a Samsung MCU mailbox. The reserved CP
  region begins at `0xB0000000` and spans 120 MiB; the 4 MiB IPC region is at
  offset `0x07400000`. These are *host physical* addresses, distinct from the
  firmware's CP load addresses around `0x40000000`.
- The vendor GPL sources in ignored
  `build/kernel/vendor-modem-reference/` identify the control ioctl sequence,
  `modem_firmware` structure, mailbox operations and secure-monitor mediated
  power controls. `link_device_shmem.c` bounds-checks a firmware transfer
  against its boot window. Direct CPU reads of secure PMU CP registers caused
  an external abort in the earlier probe; `tools/kmod/j701f_modem_probe.c`
  uses the secure-monitor *read* call instead.
- A proprietary Android `cbd` binary copied into ignored reference material
  has strings naming `std_boot_modem_reset`, `BOOT_STAGE`, security requests,
  `MODEM ON`, `BOOT ON`, `BOOT START`, handshake and `BOOT OFF`. This shows the
  boot order is more than a power bit. The binary was not executed or copied
  into the public repository. Deep REA decompilation was unavailable on the
  host because no compatible Ghidra/Hopper/IDA provider is configured; those
  strings are static observations, not a complete reconstructed algorithm.
- A prior read-only phone check saw `CP_CTRL` 0xB through the secure monitor,
  but uninitialized IPC memory and zero mailbox values. That is not evidence
  of a running baseband. The earlier RADIO TOC log named `TOC`, `BOOT`, `MAIN`,
  `NV`, `OFFSET`, with `BOOT` and `MAIN` load addresses around `0x40000000`.
  The installed partition's header is now saved only in ignored `build/modem/`.
- Claude loaded `j701f_modem_state` once on 2026-10-28 with the `phone` lock.
  It exited with the intended `-ENODEV`, left no module resident and caused
  no oops or abort. It read `CP_CTRL_NS=0xb` via SMC, and mailbox pending,
  CP message, CP status and CP active were all zero. This repeats the earlier
  finding: the PMU bits alone do not mean the CP link is running.

The 32-byte TOC entry layout (12-byte name, then five little-endian 32-bit
fields) is corroborated by the [Comsecuris Samsung TOC template](https://github.com/Comsecuris/shannonRE/blob/master/010/sam.bt)
and its [reader](https://github.com/Comsecuris/shannonRE/blob/master/modem/unpack_modem.py).
The fifth field's meaning is not established here; the tool calls it
`unknown`, not CRC.

## First implementable slice

`tools/modem-radio-toc.py` reads only the first 512 bytes of a regular host
file and validates BOOT/MAIN and any other file-backed sections against the
declared image size. `OFFSET` is bounds-checked but allowed to overlap MAIN,
as it does in the factory package. It rejects truncated, out-of-bounds,
duplicate and overlapping load-image entries; it neither extracts payloads
nor reads NV/EFS. A full
RADIO image can be passed directly. For a 512-byte header-only copy, the full
partition size must be supplied explicitly, for example:

```sh
python3 tools/modem-radio-toc.py --image-size 92274688 build/modem/radio-header.bin
```

That command is a format check only. A pass does not establish firmware
integrity, signature validity or CP compatibility. Do not commit firmware or
device-unique NV material.

## Next steps, in order

1. Compare the installed RADIO header with the factory package and check
   section bounds. **Done**, read-only over USB serial; headers match.
2. Test the prepared **read-only**
   `tools/kmod/modem-state/j701f_modem_state.c` module. It samples CP power
   through the secure monitor and only three CP-to-AP mailbox words plus the
   pending-interrupt register; it does not clear interrupts or change power.
   **Done** by Claude, once; the module is not kept loaded. Its `vermagic` is
   `7.1.13-BURAK-PANFROST-01 SMP preempt mod_unload aarch64`; `W=1` and
   `checkpatch` reported zero source warnings. The output tree lacks
   `Module.symvers`, so modpost emitted unresolved-symbol warnings, as for
   other externally built modules on this host. The host Clang/Rust versions
   also no longer reproduce the pinned old `.config` hash, so the module was
   built directly against the current output tree with `KBUILD_MODPOST_WARN=1`.
   The phone trial used Claude's separately compiled module against the
   running kernel's output tree. Never directly read secure PMU CP registers.
3. Implement the CP boot path in small testable stages using the vendor
   interface: reserved-memory mapping, mailbox IRQ, secure-monitor power,
   bounded BOOT/MAIN transfer, security request, handshake, SIPC5 channels.
   Keep boot support opt-in and modular so failure does not prevent Linux
   from starting. Do not use `cbd` as an opaque Android binary in production.
4. Keep any authorized NV data in a private copy with writes in RAM until the
   CP is stable. RFS/telephony userspace and then calls, SMS and data come
   after a successful link. Cellular transmissions have not been attempted.

Every phone-side stage must preserve the existing BOOT recovery path. Never
play audio during modem trials, per the owner's standing order.

## Stage 3A design before CP writes

The target is to test firmware *staging and secure validation* without
releasing the CP. This is a proposed design, not an executed step. Firmware
source is the installed RADIO block device, opened read-only. Recheck the
partition name and 92,274,688-byte size; compare the 512-byte header with the
already verified copy; parse it with the same bounds as the host tool. `BOOT`
and `MAIN` must have the measured names, file offsets, sizes and CP load
addresses. Never use `OFFSET` as a separate load image; it overlaps MAIN.

Map only the reserved CP firmware window, host physical `0xB0000000` to
`0xB73FFFFF`, which the current device tree marks `no-map`. Translate CP load
address `0x40000000` to host `0xB0000000`: BOOT occupies the first 5,900
bytes; MAIN begins at `+0x10000` and ends before `+0x4900000`. The source and
destination must each be checked for integer overflow, partition bounds,
firmware-window bounds and overlap *before* any write. Copy in bounded
chunks, then read back and compare a digest before any SMC call. Do not load
NV yet; its CP destination is `+0x4900000`, and it comes from private EFS
backup, never from the RADIO image. No EFS partition access is part of 3A.

For secure validation, the pinned vendor's
[`modem_v1.h`](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/29223d295a58ebe82e95347c8eb8468ea2b1c336/drivers/misc/modem_v1/modem_v1.h)
defines `SMC_ID_CLK=0x82001011`, enable 0 and disable 1. The matching
`link_device_shmem.c` and `shm_ipc.c` call SMC `0x82000700`, mode 0, with
BOOT size 5,900 and MAIN size 0x0250677c between clock enable/disable calls.
The first trial should log all three return values and verify the clock is
disabled even on an error. It must **not** call CP power/reset/start or send
a mailbox interrupt in this stage. This SMC changes TrustZone state even if
the CP is not released, so the phone trial needs Claude's review, the phone
lock, a known-good recovery path and a bounded return to normal Linux.
