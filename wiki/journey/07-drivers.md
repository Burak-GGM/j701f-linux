# 7. Drivers, one stage at a time

**Goal:** turn "it boots and shows a desktop" into a phone whose hardware behaves.

Each item below was done as its own small stage: build one image, install it, verify, take a screenshot, write it down. Changing one thing at a time is slow on paper and fast in practice, because when something breaks there is only one suspect.

## A newer kernel first

The first mainline boots used Linux 6.15 with the whole exynos7870-mainline tree. Before investing in drivers the base was moved to **Linux 7.1.13** from kernel.org plus only the six community patches that are not upstream yet. A newer base means fewer private patches to carry, and it is easier to do early than late. The old kernel configuration is kept in the repository in case a comparison is ever needed.

## Battery gauge

The fuel gauge is part of the S2MU005 chip and has a mainline driver. It only needed a device-tree node on the right I²C bus. The desktop's battery indicator started showing a real percentage.

## Temperature

The SoC's temperature sensor (TMU) has no mainline support for this chip. A small **read-only** driver was written: it reads the calibration values and converts the sensor reading to degrees, and never writes to the hardware. On top of it the device tree defines three thresholds: slow down at 70 °C, warn at 85 °C, switch off at 105 °C.

## Watchdog

A watchdog is a timer that resets the machine unless software keeps "feeding" it. The SoC has one and mainline supports it. It is armed from the first moment of boot with a 30-second limit. This turned every later experiment from "the phone is frozen, someone has to hold the power button" into "the phone restarts itself".

## CPU frequency scaling

Out of the box the mainline kernel left all eight cores at the bootloader's 902 MHz. The vendor kernel runs them between 546 and 1586 MHz. Changing a CPU's clock while it is running is delicate, and no mainline driver exists for this chip, so one was written from measurements:

1. **Measure.** Under the vendor kernel, every frequency step was selected in turn and the supply voltage (regulator `BUCK1`) read back. That table is saved in `build/kernel/vendor-opp-measurement.txt`.
2. **Sequence.** To change frequency: raise the voltage if going up; move the cores to a spare "switch" clock; reprogram the PLL and wait for it to lock; move the cores back; lower the voltage if going down.
3. **Margin.** Every voltage gets 12.5 mV added.

All eleven steps were verified. A single-core benchmark scales as expected, from 254 events/s at 546 MHz to 741 at 1586 MHz.

## Keys, Bluetooth, accelerometer

- The two **touch keys** are a Coreriver TC360 chip. The mainline driver nearly fits, but this chip reports presses as a bitmap rather than as key codes; a small patch adds that format. They are mapped to "task switcher" and "back".
- The **Bluetooth** half of the Wi-Fi chip is described in the device tree and the controller appears. User-space pairing has not been set up.
- The **accelerometer** (ST LIS2HH12) has a mainline driver and only needed a node.

## GPU frequency scaling

Like the CPU, the GPU was stuck at its boot frequency, 343 MHz, while the vendor kernel uses up to 1001 MHz. The fix has three parts:

- Teach the clock driver the GPU PLL's settings for the seven vendor steps.
- A small driver that moves the GPU to the spare clock while its PLL changes, exactly as for the CPUs.
- A table of frequencies and voltages in the device tree for Panfrost's own scaling logic.

Because a mistake here could hang the phone at every boot, it was built to be **opt-in**: the kernel starts with the GPU limited to 343 MHz, and the limit is raised by a script 40 seconds after boot. If the phone resets shortly after the raise, the script notices on the next boot and leaves the limit alone.

Result: an unsynchronised rendering test went from about 250 to about 800 frames per second.

The same pattern — a safe default in the kernel, a guarded raise from user space — is now used for the CPU's top speed and for loading the audio drivers.

## Tying heat to speed

Finally the CPU and the GPU were both registered as "cooling devices" on the 70 °C threshold, so the kernel slows them down together when the chip gets hot. Four minutes with all eight cores at 1586 MHz and the GPU at 1001 MHz took the sensor from 54 to 60 °C — below the threshold, so throttling has been checked by hand but has not yet happened on its own.

## A later round: storage, small parts, Bluetooth

After sound ([chapter 8](08-sound.md)) the work returned to this list, in the order the owner set: performance first, then everyday phone features.

- **eMMC** was running in its slowest mode. Allowing the faster ones took sequential reads from 22 to 60–80 MB/s. The next mode up (HS200) started and then failed every write; it was reverted, and it left a rule behind: never try a storage mode on the filesystem you boot from.
- **Vibration motor, microSD slot and proximity sensor** each turned out to need only a device-tree node, because mainline already has drivers that fit: the motor is a switched regulator, the card slot matches a sibling phone, and the sensor is supported by an existing driver under a different name. All three were prepared while the phone was unreachable and worked on the first boot.
- **Bluetooth** got its patch firmware, a fixed address and the BlueZ service; scanning finds nearby devices.
- **Hardware video decoding** took two attempts. At first the driver loaded but the codec's own firmware never started. The codec's registers answered, the firmware image was in place, and not one interrupt arrived. The cause was a memory-management unit that sits between the codec and memory: it leaves reset *enabled and blocking*, so the codec could not read its own firmware. Switching that unit to pass-through was a one-register fix, and a 720p video then decoded with about 24 times less CPU time than in software.

One incident belongs here too. Reading a debug file that dumps every register of the power-management block crashed the reading process inside the kernel and left a lock held; the next reboot hung with the watchdog already switched off, and the phone had to be restarted by hand. The watchdog now stays armed through shutdown.

## What could not be done

- **Camera.** Samsung's camera pipeline (FIMC-IS) has no mainline driver for this chip, and porting it is a project of its own.
- **The real display driver.** The parameters of the panel and display controller are recorded, but writing and testing that driver needs someone watching the screen.
- **Modem, suspend, charger control** have not been started.
