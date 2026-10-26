# 3. Alpine on the phone

**Goal:** a real, installed Linux distribution with a package manager, still on the vendor kernel.

## Why Alpine

[Alpine Linux](https://alpinelinux.org/) is small (the base system is about 8 MB), has current AArch64 packages including KDE Plasma Mobile, and uses the *musl* C library and BusyBox, which makes it undemanding about the kernel underneath. That last point mattered: the vendor kernel is version 3.18 from 2014, and many modern distributions refuse to run on something that old.

## Try it in RAM first

Before writing anything to storage, the Alpine "minirootfs" archive was sent to the running recovery over the USB shell, unpacked into a RAM filesystem and entered with `chroot`. `tools/alpine-ram-test.py` automates this, including checking the archive's checksum and signature. The trial showed that Alpine's programs start, that `apk` (the package manager) works, and that the old kernel is good enough — all without touching a single partition. Rebooting erased every trace.

## Choosing where to install

The phone's storage has no spare room, so something had to give. The layout that was chosen:

| Partition | Size | Role |
| --- | --- | --- |
| `BOOT` | 32 MiB | Kernel + a small loader initramfs |
| `RECOVERY` | 38 MiB | The rescue environment from chapter 2 |
| `SYSTEM` | 3 GiB | Left alone |
| `USERDATA` | 11.1 GiB | The Alpine root filesystem (replaces Android's data) |

The partition table itself was not changed. Android's user data was given up on purpose.

## The loader

`BOOT` got the same known-good kernel as the recovery, with a different initramfs. Its `/init` has one job: find `USERDATA`, check that it really contains our system, mount it, and hand control to it with `switch_root`. If anything looks wrong it stops instead of guessing — a missing or damaged root should never lead to a half-started system.

## A flashing failure worth knowing about

The first attempt to write the 11 GB root filesystem failed at the connection-closing stage in Download Mode. Its generic Android *sparse* encoding differed from the supplied Samsung firmware: Samsung's image used larger headers and no "fill" chunks. That was a plausible compatibility problem, but not a proved sole cause. The failure left the contents of `USERDATA` uncertain.

`BOOT` had not been touched, but the phone showed an update-error screen and the recovery key combination returned to that screen. Reflashing only the verified recovery archive restored the terminal. This produced a rule that has held since: **compare your image with the vendor's own before sending it.** The image writer was rewritten to match the chunk format found in Samsung's firmware. A later read-only check verified the installed Alpine root and its startup files; normal boot then succeeded. The user had agreed to replace Android's DATA, and no DATA backup was available. `docs/system-flashing.md` has the details.

## A usable system

With Alpine installed, the ordinary tools of a Linux system could be added one at a time:

- a user account and `sudo`,
- **Wi-Fi** using the vendor's Broadcom driver, with firmware files taken from Samsung's own firmware package, which gave the phone internet access and therefore `apk add`,
- **SSH** over that Wi-Fi connection, so development no longer depended on the serial shell,
- a first graphical program: a Qt terminal drawn straight into the framebuffer.

At this point the phone was a small Linux computer. But it was stuck in 2014: no GPU acceleration (the vendor GPU driver only talks to Android's graphics stack), no way to run a Wayland desktop, and a kernel nobody maintains. Everything after this chapter is about replacing that kernel.

!!! info "Details in the repository"
    `docs/alpine-ram-trial.md`, `docs/internal-system-layout.md`, `docs/system-flashing.md`, `docs/ssh.md`, `docs/wifi.md` and `docs/gui.md`.
