# J701F modem userspace preparation (2026-10-28, Codex)

This is a host-only protocol prototype. The CP is not booted into an IPC link,
and no call, SMS, mobile data or SIM service has been tested. Nothing here opens
a device node, RADIO, EFS or a private NV file. No modem traffic is sent.

## What the public code establishes

The factory GPL modem driver uses SIPC5 frames: the first byte starts with
`0xf8`; a two-byte length is measured from the start of the link header;
bit `0x04` requests padding to the kernel's `sizeof(size_t)` alignment (eight
bytes on this AArch64 build). A `0x02` extension uses a 32-bit length, while
`0x03` adds a one-byte multi-frame control field. The driver groups channel
215-224 as BOOT, 225-234 as DUMP, 235-244 as FMT and 245-254 as RFS. Its
J701F device tree names BOOT 215, FMT 235 and RFS 245. In the vendor driver,
the SIPC5 link header is removed before a character device delivers FMT/RFS
to userspace; a future driver must state which side owns framing so it is not
added or stripped twice. The shared-memory boot completion path requires both
FMT and RFS endpoints open before `CMD_INIT_END`.

Replicant's `libsamsung-ipc` defines a six-byte RFS envelope as little-endian
32-bit total length, one-byte command index and one-byte ID. Within RFS group
`0x42`, index 1 is NV read and index 2 is NV write. The NV request contains
little-endian offset and length; write appends the data. Its default NV size
is 2 MiB for supported devices, but the J701F RADIO table declares a 1 MiB
external NV load. That table does **not** prove the live J701F RFS image size
or the exact CP response dialect. The separate J701F implementation must
measure those before sending any answer.

Sources: pinned [vendor SIPC5 header](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/29223d295a58ebe82e95347c8eb8468ea2b1c336/drivers/misc/modem_v1/include/sipc5.h),
[shared-memory command handler](https://github.com/samsungexynos7870/android_kernel_samsung_exynos7870/blob/29223d295a58ebe82e95347c8eb8468ea2b1c336/drivers/misc/modem_v1/link_device_shmem.c),
[Replicant RFS definitions](https://git.replicant.us/replicant/hardware_replicant_libsamsung-ipc/tree/include/rfs.h),
and [RFS header conversion](https://git.replicant.us/replicant/hardware_replicant_libsamsung-ipc/tree/samsung-ipc/ipc_utils.c).

## Implemented boundary

`tools/modem/sipc5.py` encodes/decodes bounded link frames and reassembles
partial input. `tools/modem/rfs.py` parses only the two known NV item requests
and applies them to an exact 1 MiB *RAM-only* image supplied by its caller.
It refuses unknown commands, bad lengths and out-of-range access. It emits no
wire response, has no CLI and does not access the real EFS/firmware. Unit
tests use synthetic bytes only. These components are a format-checking base,
not a production RFS daemon. The 1 MiB size is a provisional J701F bound from
the RADIO TOC, not a license to read or overwrite EFS.

If a live trial eventually needs NV, use the owner's existing private backup
from ignored storage; keep a separate immutable original, serve reads from a
private RAM copy and hold CP writes in RAM. Redact payloads, identifiers and
secrets from logs. Never commit the backup, copy it into the public tree, or
write the EFS partition. Before any live response, validate the CP's RFS
length, response confirm byte and sequence behavior against captured traffic
without transmitting a request.

## Telephony stack decision

`libsamsung-ipc` already has a `herolte` shared-memory implementation, but its
device registry has no `j7velte`. Its boot code and command types are
references; installing it unchanged will not provide J701F support.
`samsungipcd` is an early AT proxy over `libsamsung-ipc` that can present a
modem to ModemManager or oFono. Once the J701F kernel link, boot handshake and
RFS service actually work, add a J701F backend to `libsamsung-ipc` and then
test `samsungipcd` with ModemManager for text/SIM/network status first.
Voice and data require further device-specific validation. No audio playback
is part of bring-up, per the owner's instruction.

Sources: [Replicant device registry](https://git.replicant.us/replicant/hardware_replicant_libsamsung-ipc/tree/samsung-ipc/devices/ipc_devices.c),
[herolte backend](https://git.replicant.us/replicant/hardware_replicant_libsamsung-ipc/tree/samsung-ipc/devices/herolte/herolte.c),
[samsungipcd README](https://gitlab.com/sleirsgoevy/samsungipcd/-/blob/master/README.md).

## Next live gates

1. CP Stage B: power/start with mailbox interrupt handling and a bounded
   timeout; observe whether the CP requests the known boot handshake. Preserve
   the installed BOOT and recovery path. Only the holder of the `phone` lock
   should do this.
2. Implement FMT and RFS endpoints, verify boot messages and both-open
   `CMD_INIT_END`, then measure the CP's actual RFS requests with payloads
   redacted. A timeout must leave ordinary Linux boot usable.
3. Confirm the correct private NV image, response wire format and retention
   policy before answering. Only after this should the telephony bridge run.
