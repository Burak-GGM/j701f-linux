# 1. Starting point

## The phone

| | |
| --- | --- |
| Model | Samsung Galaxy J7 Neo / J7 Core, SM-J701F (`j7velte`) |
| System-on-chip | Samsung Exynos 7870, 8 × Cortex-A53 |
| GPU | ARM Mali-T830 MP1 |
| Memory / storage | 2 GB RAM (about 1.6 GB usable), 16 GB eMMC |
| Display | 720 × 1280 AMOLED, EA8061S panel |
| Stock software | Android with a Samsung 3.18 kernel |

A phone like this is a small computer with a very unfriendly boot process. There is no BIOS menu and no "boot from USB". The first program that runs is Samsung's bootloader, **S-BOOT**, and it will only start something that looks like an Android boot image stored in one of two partitions: `BOOT` (normal start) or `RECOVERY` (start with Power + Home + Volume Up held).

## The goal

The long-term goal was a usable Linux phone: a current kernel, a graphical desktop, and as much of the hardware working as possible. That is far too big to attempt in one step, so the work was cut into stages where each stage could be *proved* before the next one began:

1. Run any program of our own on the phone.
2. Get a shell we can type into.
3. Run a real Linux distribution on the old vendor kernel.
4. Replace the vendor kernel with a modern one.
5. Get the GPU and a desktop working.
6. Bring up the remaining hardware, driver by driver.

## Rules that were never broken

Phones can be bricked — left in a state from which they cannot be recovered without special hardware. A few rules kept that from happening:

!!! danger "Partitions that are never written"
    The partition table (PIT), the bootloader (BL / sboot), EFS (the phone's identity and calibration data), TrustZone, the modem firmware and RPMB are never touched. Only `BOOT`, `RECOVERY` and `USERDATA` are written, and only by tools that check sizes and hashes first.

- **Always keep one slot that works.** Experiments go into one of the two bootable slots while the other keeps a known-good system. If a new kernel does not start, the key combination for the other slot brings the phone back.
- **Read before you write.** Almost every fact used in this port — partition sizes, memory layout, register addresses, voltages — was read from the running phone first and saved in the repository, rather than taken from a data sheet or guessed.
- **Check, then trust.** Images are built with fixed hashes, verified on the host, and read back from the phone after writing.

## What you need on the desk

- A Linux PC, a USB cable, and the phone.
- [Odin](https://en.wikipedia.org/wiki/Odin_(firmware_flashing_software)) or Heimdall to write a partition from Download Mode. This is only needed for the very first image and for emergencies.
- A custom recovery image for this phone to start from. The project began with an **OrangeFox** recovery build, because it contains a kernel and device tree that are known to boot on this exact model.

The next chapter takes that recovery image apart and puts our own program inside it.
