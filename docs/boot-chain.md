# Boot chain and development stages

```text
Samsung BootROM
  -> existing Samsung early boot chain / stock bootloader
  -> RECOVERY image selected by the device's recovery boot route
  -> unchanged OrangeFox kernel + complete Samsung DTBH/DTB payload
  -> replacement LZMA newc initramfs
  -> /init interpreted by static AArch64 BusyBox /bin/sh as PID 1
  -> virtual mounts, RAM logs, touchscreen terminal + PTY shell and USB serial shell
```

The bootloader supplies the actual kernel command line and hardware selection context. The image-header command line and built-in kernel configuration are separate inputs: the inspected config contains `androidboot.selinux=permissive` with `CONFIG_CMDLINE_EXTEND=y`. `/proc/cmdline` is the runtime authority. This project does not change either input.

Linux executes `/init` from the unpacked initramfs. BusyBox provides its shell and small utilities without Android's dynamic linker or shared libraries. `init` mounts proc, sysfs, devtmpfs (with a static-node fallback), devpts and tmpfs. It logs the greeting, uname, kernel version, runtime command line and available consoles. It starts a child shell and stays alive after that shell exits. See the kernel's [initramfs documentation](https://docs.kernel.org/filesystems/ramfs-rootfs-initramfs.html) for PID 1 and early userspace behavior.

## Storage boundary

| Area | Policy |
| --- | --- |
| RECOVERY | May be overwritten by the explicit recovery-only flash helper. |
| BOOT | Planned future kernel/loader target; remains untouched during validation development. |
| SYSTEM / DATA | No automatic mount or modification. Explicit `boot-manager check` may inspect DATA as ext4 with `ro,noload`; SYSTEM stays untouched. DATA is the selected future Linux root, with installation separate. |
| PIT, BL/sboot, EFS, TrustZone, modem, RPMB-related areas | Never written by this project. |
| RAM filesystems | `/init` may mount and write these. |
| External storage / future persistent rootfs | Not used by Stage 1; requires a separately identified target and explicit later plan. |

No scripts use partition numbers, `dd` to a block device, filesystem formatting, repartitioning, or a bootloader exploit. OrangeFox reference files contain device-specific paths but are inert documentation; their storage mounts are not reused. The interactive root shell can issue arbitrary commands, so these are automation boundaries rather than a security sandbox.

## Staged roadmap

| Stage | Work and completion evidence |
| --- | --- |
| 1 — BusyBox shell | Custom /init, BusyBox and an interactive shell are confirmed on hardware. PID 1 supervises console shells; the local terminal also restarts its PTY shell after exit. |
| 2 — USB debugging | Inspect the saved original USB `.rc` and actual sysfs nodes in working OrangeFox. This kernel uses the legacy Android gadget (`CONFIG_USB_G_ANDROID=y`, `CONFIG_USB_CONFIGFS` disabled), so a generic configfs recipe is inappropriate. The current build configures the discovered ACM function and starts a USB serial shell. An interactive host USB serial session is confirmed on hardware. ADB and networking are not implemented. |
| 3 — Read-only eMMC inspection | Discover names and sizes live using read-only commands. For ext4, read-only mounting also needs journal replay suppressed (`ro,noload`); filesystem-specific flags must be chosen after identification. Do not import OrangeFox's automatic mount rules. |
| 4 — Alpine AArch64 | Check compatibility with the old 3.18 kernel, required syscalls, devtmpfs and console access. Initially stage a rootfs in RAM or verified external storage; hand off with `switch_root` only after the new `/sbin/init` is verified. |
| 5 — Persistent root | Prefer identified external storage. No safe internal partition is assumed or allocated. Formatting or selecting a persistent target requires a separate explicit decision; forbidden partitions stay forbidden. |
| 6 — Display | Framebuffer output and startup heartbeat are confirmed on hardware. Current-mode activation and a scoped red/blue correction are implemented; the local terminal is confirmed in RAM. |
| 7 — Touch/input | The runtime-discovered touchscreen, on-screen keyboard and local PTY shell are confirmed in RAM. Incremental cell repaint removed the reported whole-screen flashes. The latest terminal archive still needs a reflash/reboot check. |
| 8 — Wi-Fi | Identify the actual driver, firmware and calibration requirements from the working kernel/device; do not modify EFS. |
| 9 — Video acceleration | Investigate exposed codec interfaces and required userspace components. No acceleration is promised. |
| 10 — Mainline + DTB | Separate experimental recovery image after mapping hardware and driver support; preserve the original recovery fallback. |
| 11 — Second-stage bootloader | Investigate U-Boot or another loader launched from RECOVERY, with verified entry protocol and memory map. Do not replace Samsung early boot components or attempt secure-boot bypasses. |

USB serial, framebuffer display and a touchscreen terminal are implemented, with hardware evidence recorded in [hardware-status.md](hardware-status.md). The display/input stages were brought forward to make the device usable locally. The storage, Alpine, networking and bootloader stages remain separate work. The user confirmed the power menu works and moved to loader development. The first read-only validation component is implemented; the selected future layout is BOOT for kernel/loader and DATA for the Linux root, with SYSTEM untouched. The [internal layout](internal-system-layout.md) records measured capacities and current limits. Alpine installation and actual PID 1 handoff remain separate work in [next-goals.md](next-goals.md).
