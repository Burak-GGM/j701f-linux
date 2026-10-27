# Engineering notes

These are the working notes of the port, written while the work happened. Many describe an
earlier state and are kept as a record; the [wiki](../wiki/index.md) is the maintained,
readable account and the place to look first.

IP addresses in these notes have been replaced by addresses in `192.168.1.0/24`.

## Current

| File | Contents |
| --- | --- |
| [j701f-mainline.md](j701f-mainline.md) | The detailed work log of the mainline port, newest entries at the end |
| [roadmap.md](roadmap.md), [roadmap-2.md](roadmap-2.md) | The agreed goals and their status |
| [third-party.md](third-party.md) | Provenance and licences of everything fetched or reused |
| [j701f-display.md](j701f-display.md) | Bring-up of the native display driver |
| [panfrost-bringup.md](panfrost-bringup.md), [kernel-build.md](kernel-build.md) | GPU and kernel build notes |
| [recovery-design.md](recovery-design.md) | Design of the graphical recovery |
| [recovery-zip-device-test.md](recovery-zip-device-test.md) | Which OrangeFox to use for the release ZIP's device test, and the way back to rec8 |

## The first stages (historical)

| File | Contents |
| --- | --- |
| [stage1-recovery.md](stage1-recovery.md) | The original README: a BusyBox userspace in the vendor recovery image |
| [recovery-image-format.md](recovery-image-format.md), [boot-chain.md](boot-chain.md), [internal-system-layout.md](internal-system-layout.md) | Image format, boot chain and partition layout as first measured |
| [usb-console.md](usb-console.md), [debugging.md](debugging.md) | The USB serial console and early debugging |
| [alpine-ram-trial.md](alpine-ram-trial.md), [system-flashing.md](system-flashing.md) | Alpine in RAM, then installed on DATA, on the vendor kernel |
| [hardware-status.md](hardware-status.md), [driver-status.md](driver-status.md), [next-goals.md](next-goals.md) | Status on the vendor 3.18 kernel |
| [ssh.md](ssh.md), [wifi.md](wifi.md), [admin-cpu.md](admin-cpu.md), [gui.md](gui.md), [ondevice-terminal.md](ondevice-terminal.md) | Networking, administration and the first on-device UI on the vendor kernel |
| [j701f-mainline.md](j701f-mainline.md) (first half) | The early mainline diagnostic trials through RECOVERY |

Notes that mention `docs/coordination/` refer to the lock and message files the two
assistants used to share the phone; that folder is kept out of the public repository.
