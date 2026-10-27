# Mainline Linux on the Samsung Galaxy J7 (SM-J701F)

Mainline **Linux 7.1** with **Alpine Linux 3.24** and **KDE Plasma Mobile** on the
Samsung SM-J701F (`j7velte`, Exynos 7870), a 2017 Android phone. The phone boots its own
kernel from the BOOT partition, keeps its root filesystem on the DATA partition, and has
a graphical recovery of this project's own in the RECOVERY partition.

[Wiki (English / Türkçe)](https://burak-ggm.github.io/j701f-linux/) · [Hardware status](wiki/reference/hardware.md) ·
[Kernel and patches](wiki/reference/kernel.md) · [Tools and workflow](wiki/reference/tools.md) ·
[Lessons and pitfalls](wiki/reference/lessons.md)

> **This is an experiment on one phone, not a product.** Flashing images built from this
> repository onto another device, even another J7 variant, can leave it unable to boot.
> Nothing in this project writes to the bootloader, the partition table (PIT), EFS, the
> modem or TrustZone, and you should keep it that way.

## Status

| Area | State |
| --- | --- |
| Kernel | Linux 7.1.13, six community Exynos 7870 patches, about 25 local patches and out-of-tree modules |
| Display | Native DECON + MIPI DSI + EA8061S panel driver at 59.6 fps, panel brightness, blanking; the bootloader framebuffer is the fallback |
| GPU | Panfrost (Mali-T830), frequency scaling 343–1001 MHz |
| CPU | All eight cores, frequency scaling 546–1586 MHz |
| Touch, Wi-Fi, USB (serial, MTP), eMMC, SD card | Working |
| Bluetooth | Controller up and scanning; pairing and audio untested |
| Sound | Speaker and main microphone; headset detection and calls do not work |
| Battery gauge, charger, temperatures, watchdog | Working; the battery helper is not yet a boot service |
| Rotation, flashlight, hardware video decoding | Working |
| Vibration | Motor driven by the desktop's feedback service; not yet confirmed by touch |
| Camera | Preview and photographs from both cameras; no video recording or autofocus |
| Suspend | Suspend-to-idle by hand; not automatic yet |
| Recovery | Own LVGL recovery: kernel update with read-back and rollback, backup, files over USB, terminal, English/Turkish |
| Modem, FM radio | Not working; modem bring-up has only begun |

The full table, with the evidence behind each line, is on the
[hardware and status](wiki/reference/hardware.md) page.

## Repository layout

| Path | Contents |
| --- | --- |
| `kernel/` | Pinned inputs (`inputs.json`), kernel configurations, device-tree sources (`dts/`), patches (`patches/`), early diagnostic sources |
| `tools/` | Host tools: kernel build, image packaging, update and backup of the phone, display trials, benchmarks; out-of-tree kernel modules in `tools/kmod/` |
| `system/` | Files installed on the phone's Alpine system: boot scripts, services, udev rules, the battery helper, camera and display switches |
| `recovery/` | The graphical recovery (C and LVGL) and its scripts |
| `ramdisk/`, `scripts/`, `Makefile` | The first stage: a BusyBox userspace repacked into the vendor recovery image |
| `gui/`, `bench/` | An early Qt terminal and a browser scroll benchmark |
| `tests/` | Host-side unit tests (Python and C) for the tools, patches and recovery scripts |
| `wiki/` | The bilingual MkDocs wiki: the story of the port and the reference documentation |
| `docs/` | Engineering notes and the detailed work log ([index](docs/README.md)) |

## Building

The host used so far is Arch Linux on x86-64. The kernel is cross-compiled with LLVM;
all sources are fetched from pinned URLs and checked by SHA-256.

```sh
python3 tools/build-kernel.py panfrost --jobs "$(nproc)"
tools/build-mainline-image.sh NAME kernel/dts/exynos7870-j7velte-camera.dts "--allow-audio --allow-sd --allow-mfc"
```

The first command fetches, patches, configures and compiles the kernel; the second packages
it with the device tree and initramfs into a BOOT image under `build/kernel/` and runs the
checks. Installing that image on a phone that already runs this system goes through the
project's recovery (`tools/run-recovery-update.sh NAME`), which writes BOOT, reads it back
and keeps the previous image for rollback. The [tools page](wiki/reference/tools.md)
describes every step and its pitfalls.

Host tools talk to the phone over SSH. Put the phone's address in a file `.phone-ip` in
the repository root (it is ignored by git) or set `J701F_PHONE_IP`.

Unit tests:

```sh
python3 -m unittest discover -s tests
```

Tests that need build products, a prepared kernel tree or a connected phone skip
themselves when those are missing.

Wiki (published at <https://burak-ggm.github.io/j701f-linux/> from `main` after the tests pass):

```sh
python3 -m venv build/wiki-venv
build/wiki-venv/bin/pip install -r wiki/requirements.txt
build/wiki-venv/bin/mkdocs serve
```

## Installing

USERDATA holds the Alpine system; BOOT and RECOVERY hold the project's kernel loader and
recovery. Three routes, all described on the [installation page](wiki/reference/installation.md):

- **Reinstalling a phone that already runs this system:** `scripts/install-release.py`
  stages a release from `tools/build-release.py` on the SD card, can back up the old USERDATA
  first, and writes and fully reads back the new one from the RAM recovery. First run on the
  project's phone on 2026-10-27: backup, write, read-back and boot all verified.
- **From TWRP or OrangeFox:** a flashable ZIP from `tools/build-recovery-zip.py`
  ([recovery page](wiki/reference/recovery.md)); tested only on a simulated phone so far.
- **From stock Android:** Odin archives from `tools/prepare-first-install.py` and the host-side
  checks of `scripts/first-install.py`; a [plan](docs/installer-first-install-plan.md), not
  yet run on hardware.

All of them erase USERDATA, Android's data included.



- Samsung firmware, the stock ROM, `odin4`, the OrangeFox and TWRP images used in the first
  stage, and the device's own data (EFS and other partition backups).
- Proprietary blobs loaded at run time (Wi-Fi/Bluetooth firmware, the video codec
  firmware). They come from the phone's own Android partitions.
- Fetched sources (Linux, U-Boot, LVGL, uMTP-Responder, vendor kernel references); their
  pinned URLs and hashes are in `kernel/inputs.json` and [docs/third-party.md](docs/third-party.md).
- Build outputs (`build/`).

## How it was made

The phone belongs to Burak Serçe, who did every physical step: button combinations, cables,
flashing, looking at the screen. Most of the code and investigation was written by AI
coding assistants (OpenAI Codex and Anthropic Claude) working with him, which is why the
work log in `docs/j701f-mainline.md` is unusually detailed. The community
[exynos7870-mainline](https://gitlab.com/exynos7870-mainline/linux) project supplied the
base the kernel work starts from.

## License

GPL-2.0-only, see [LICENSE](LICENSE). Patches and files taken from other projects keep
their own notices; see [docs/third-party.md](docs/third-party.md).
