# 9. A battery number you can believe

**Goal:** a battery percentage that is true, and charging that looks after the battery.

This chapter is out of order on purpose. Between sound and this one came the real display driver, the recovery and the first camera; they are told in chapters 10 to 12, which were written later. The battery is told as a story because it is the best example in the project of something that was "working" for a week and was not.

## What was there

The phone's charger, fuel gauge and USB switch are one chip, the Samsung S2MU005. Mainline Linux has a driver for the fuel-gauge part, and it had been enabled early: the desktop showed a percentage, a voltage, a charging symbol. The charger part had a small local driver that only reported what the chip was doing. The chip itself did the charging with whatever settings the bootloader had left.

The status table said "Battery gauge ✅".

## The number that did not add up

A routine look at the phone's state showed this:

```text
capacity   43 %
voltage    4.35 V
current    +0.19 A
charger    Full
```

A lithium cell at 4.35 V that is taking almost no current is full. The charger chip said so itself. The gauge said 43 %.

Reading the gauge's registers showed that nothing was misconfigured: the battery's model table in the chip matched the one in the factory device tree. The raw value really was 43 %. The chip was simply wrong.

## Why

The gauge counts charge. Every second it adds what flowed in and subtracts what flowed out. Small measurement errors add up, and after days the count is far from the truth.

Samsung's driver knows this. Near full and near empty, where the cell's voltage says much more than a count, it switches the chip into another mode in which the chip pulls its number toward what the voltage implies; in between it switches back to counting. One register does it. The mainline driver only reads the chip, so on this phone the count had been drifting since the day Android left.

The proof took two minutes: write that one register by hand and watch.

```text
43 %  →  47 %  (two minutes)  →  91 %  (half an hour)  →  100 %
```

## A second opinion

How do we know 100 % is right and not just a nicer wrong number? Later the same evening the charger driver learned to switch charging off. With charging off and the phone running from the cable, no current flows through the battery, and its voltage settles to its resting value: 4.28 V. For this kind of cell that is a battery well above 90 %. Two independent measurements now agree.

## Temperature, without a new kernel image

A charger should slow down when the battery is cold or hot, and Samsung's does. That needs the battery's temperature, which comes from a thermistor read through the SoC's analogue-to-digital converter - a device the mainline device tree does not mention.

Describing new hardware normally means a new device tree and therefore a new `BOOT` image. Here a small kernel module carries a device-tree **overlay** - a patch to the device tree that is applied while the system runs - and adds the converter's node itself.

The first attempt used the kernel's existing Exynos ADC driver. It bound to the device, and every conversion timed out. Writing the vendor's start-up sequence into the registers by hand worked at once: this chip's variant is initialised differently and keeps its result at another address. So the module also brings its own forty-line driver, and the phone now reports:

```text
battery  24.4 °C
board    32.5 °C
```

## Charging

With cable type and temperature both known, charging could be made sensible:

| Situation | Before | Now |
| --- | --- | --- |
| Computer port | 450 mA | 450 mA |
| Wall charger | 450 mA | 1000 mA, up to 1500 mA between 15 and 41 °C |
| Battery cold or hot | 450 mA | reduced; off above 50 °C or below 0 °C |
| "Stop at 80 %" | not possible | optional |

The wall-charger row is honest about its state in the reference pages: it is written and tested against a simulated system, and has not yet met a real wall charger.

The decisions (gauge mode, temperature limits, the optional charge limit) live in one small script, `system/battery/j701f-battery`, with a test file that runs it against a pretend phone made of temporary files. One of those tests failed on its first run - and the test was wrong, not the script: the vendor's rule for "nearly empty" corrects the voltage for the load, which the test's author (the same author) had forgotten.

## What to take from it

- "It shows a number" is not a test. Look for two values that have to agree and compare them. The project's health check (`tools/phone-health.sh`) now compares percentage and voltage every time it runs.
- When a mainline driver exists, it may still do only half of what the vendor driver did. The missing half is often not a feature but a correction.
- A device-tree overlay loaded by a module is a legitimate way to describe a small piece of hardware without reflashing anything.

Details and file names: [Userspace → Battery percentage, temperature and charging](../reference/userspace.md#battery-percentage-temperature-and-charging).
