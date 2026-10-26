# 5. GPU and the slot swap

**Goal:** hardware-accelerated graphics, then make the new kernel the phone's normal one.

## Panfrost

The Mali-T830 in this phone belongs to ARM's "Midgard" family. ARM's own driver is closed and only serves Android. **Panfrost** is the open-source replacement: a kernel driver plus a user-space part in Mesa that provides OpenGL ES.

For Panfrost to start, the device tree has to describe the GPU correctly: its register address (`0x11400000`), three interrupts, its clocks from the `CMU_G3D` clock controller, and its power supply (regulator `BUCK2` of the PMIC). Each of those was checked against what the vendor kernel reported on the live phone before being enabled.

One worry turned out to be unnecessary. The GPU sits in its own power domain, and mainline has no driver for the Exynos 7870's power domains. But the bootloader leaves that domain switched on, so the GPU was simply reachable.

The proof was a small test program, `tools/panfrost-render-probe.c`. It opens the GPU without any display, renders a checkerboard into a 64×64 texture, reads it back and compares all 4,096 pixels. It printed:

```text
GL_RENDERER = Mali-T830 MC1 (Panfrost)
PANFROST_T830_RENDER_PASS
```

A test like this matters because "the driver loaded" and "the GPU draws correct pixels" are different claims.

## Swapping the slots

Until now the layout was *BOOT = vendor kernel, RECOVERY = experiments*. With the mainline kernel able to start the installed system, the roles were reversed:

| Slot | Before | After |
| --- | --- | --- |
| `BOOT` (normal power-on) | vendor 3.18 | **mainline** |
| `RECOVERY` (Power + Home + Vol Up) | experiments | **vendor 3.18, as the fallback** |

The swap was done from the phone itself, with a guarded script that checks the hash of what it is about to overwrite, writes, and reads everything back. A copy of the old `BOOT` image is kept on the phone and as an Odin archive on the PC.

This arrangement has a very practical benefit: **new kernels can be installed without a cable or Download Mode.** The procedure became:

1. From the running mainline system, reboot into the vendor system in `RECOVERY`.
2. From there, write the new image to `BOOT` and verify it.
3. Reboot normally.

`tools/run-boot-update.sh` does all three over the network. If a new kernel fails, holding the recovery key combination brings back the vendor system, from which the previous image can be written again. This safety net was needed for real more than once — see [chapter 8](08-sound.md).

## Touch

The touchscreen is a Melfas MIP4 controller, and mainline has a driver for it. It still took three separate fixes before a finger moved anything:

1. **Wrong interrupt type.** The device tree said "falling edge"; the chip holds its line low until it is read, so it needs "level low". With the wrong setting the first interrupt was the last.
2. **Asked too early.** The driver queried the chip before it had finished starting, and got nonsense back. A small patch gives the driver a power supply to switch on and a 300 ms wait.
3. **Rejected by the desktop.** The chip reported a resolution of zero for one axis; the input library used by the desktop refuses such devices. Another small patch copies the missing value from the other axis.

None of these would show up as an error message. Each was found by looking at what actually arrived — interrupt counts, raw packets, the input library's debug output.

## Wi-Fi on mainline

The Wi-Fi chip is a Broadcom BCM43430 on an SDIO bus, supported by the mainline `brcmfmac` driver once it is described in the device tree and given its firmware files. Two things are worth recording:

- A pin configuration copied in "to be safe" pulled the chip's power-enable line low and kept it off. Removing the extra configuration fixed it. More description is not always better.
- The chip's real MAC address lives in the EFS partition, which this project never reads. A fixed, locally administered address is set in the device tree instead. As a side effect the router always gives the phone the same IP address.

With storage, GPU, touch and network working on the new kernel, the phone was ready for a desktop.
