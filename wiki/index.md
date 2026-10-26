# Linux on the Samsung Galaxy J7 Neo (SM-J701F)

This wiki tells the story of putting a real Linux system on a 2017 Samsung phone, and documents the result well enough that someone else — a curious reader or the next person working on the project — can follow what was done and why.

The phone is a **Samsung SM-J701F** (code name `j7velte`): an Exynos 7870 system-on-chip with eight Cortex-A53 cores, a Mali-T830 GPU, 2 GB of RAM and a 720×1280 AMOLED panel. It shipped with Android and a Samsung 3.18 kernel. Today it boots **Linux 7.1.13**, runs **Alpine Linux 3.24**, and shows a GPU-accelerated **KDE Plasma Mobile** desktop with working touch, Wi-Fi and sound.

## Where things stand

| Area | State |
| --- | --- |
| Kernel | Linux 7.1.13 with community Exynos 7870 patches and a set of local drivers |
| Display | Native panel driver (59.6 frames per second, brightness, blanking); the bootloader's framebuffer is the fallback |
| GPU | Panfrost, with frequency scaling from 343 to 1001 MHz |
| CPU | All eight cores, frequency scaling from 546 to 1586 MHz |
| Touch, Wi-Fi, USB (serial, network, files over MTP), eMMC, SD card | Working |
| Sound | Speaker playback and the main microphone work; headset detection and calls do not |
| Battery gauge, charging, temperature, watchdog | Working; the battery percentage needs a helper script that is not started at boot yet |
| Rotation, flashlight, hardware video decoding | Working |
| Recovery | The project's own graphical recovery: kernel update and rollback, backup, files over USB |
| Suspend | Suspend-to-idle works when started by hand; not automatic yet |
| Camera | Preview and photographs from both cameras; no video recording, no autofocus |
| Modem | Not working, not planned for now |

The full table is on the [hardware and status](reference/hardware.md) page.

## What comes next

Most of the first plan is done: the real display driver, faster storage, hardware video decoding, Bluetooth, brightness, vibration, the flashlight, rotation, a recovery and a first camera. What is still open, roughly in the order it matters in daily use:

1. **Speed of the desktop:** applications start slowly and the task switcher is not smooth.
2. **Camera:** video recording, autofocus, full resolution, colours.
3. **Power:** automatic suspend with wake-up by key, battery temperature (so that a wall charger can be used at full current), the battery helper as a boot service.
4. **Sound:** headset and earpiece confirmed by ear, occasional half-second drop-outs.

The modem and FM radio are not planned for now.

## How to read this wiki

**[The journey](journey/01-starting-point.md)** is the story in order, written as a tutorial. It starts with the smallest possible step — making the phone print one line of our own text — and so far goes on to a desktop, sound, a battery gauge that tells the truth, a recovery of the project's own, a first camera and the real display driver. Each chapter explains what the goal was, what stood in the way and how it was solved. Read it if you want to understand *how* a port like this is done.

**[Reference](reference/hardware.md)** is the documentation: which kernel and patches are used, how the boot chain works, what every script on the phone does, how to build and install a new image, and a list of mistakes worth not repeating. Read it if you need a fact.

## Who made this

The project belongs to Burak, who owns the phone and did every physical step: button combinations, cables, flashing with Odin, listening for sound. The code and most of the investigation were written by AI coding assistants working with him in turns — first ChatGPT Codex, then Claude — which is why the repository keeps unusually detailed notes: each assistant had to pick up where the other stopped. This wiki is the readable version of those notes.

!!! warning "This is an experiment, not a product"
    Everything here was done on one specific phone. Flashing images built from this repository onto another device, even another J7 variant, can leave it unable to boot. Nothing in this project writes to the bootloader, the partition table, the modem or the EFS partition, and you should keep it that way.
