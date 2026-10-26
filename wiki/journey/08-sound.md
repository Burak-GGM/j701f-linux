# 8. Sound

**Goal:** hear something from the phone's speaker.

Sound was the largest single piece of hardware work in the project, and the first where no mainline driver existed for the central chip. It is told here in the order it happened, mistakes included, because the mistakes are the instructive part.

## How the phone makes sound

Four blocks are involved, and all four have to be right before the speaker moves:

```text
application → PipeWire → I2S controller → audio mixer → codec → speaker
                          (in the SoC)     (in the SoC)  (in the PMIC)
```

- The **I²S controller** sends digital audio out of the SoC. Mainline has a driver.
- The **audio mixer** (Samsung "S1402X") sits between the I²S controller and the codec and can combine audio from the application processor, the modem and Bluetooth. No mainline driver.
- The **codec** (Samsung "COD3026X") turns digital audio into the analog signal for the speaker, the earpiece and the headphone jack. It is not a separate chip: it lives inside the power-management chip. No mainline driver.
- Around them are the audio clocks, a DMA controller that feeds the I²S controller, and a block of reset bits Samsung calls **LPASS**.

## Reading the vendor code

With no data sheet for the codec, the only description of how it works is Samsung's own driver in the vendor kernel: 4,300 lines for the codec, 2,400 for the mixer. The owner gave standing permission to read vendor and custom-ROM kernels and port from them. The files used are saved under `build/kernel/vendor-audio-reference/` with their source commit and checksums.

Porting did not mean copying 7,000 lines. Most of the vendor code deals with things not needed for a first sound: voice calls, FM radio, headset buttons, water detection. The useful core is a few **sequences** — "to switch the speaker on, write these registers in this order with these waits". Those were lifted out and placed in new, much smaller drivers written for the current kernel.

## Stage 1: clocks and plumbing

The first stage enabled the audio clock controller and wrote a small LPASS driver that releases the reset bits.

One finding came out of the clock work: mainline described the audio PLL as an *integer* PLL. The bootloader leaves it running at 98,304,019 Hz — a frequency an integer PLL fed by 26 MHz cannot produce. It is a *fractional* PLL, as in the vendor code, and the clock driver was corrected.

!!! failure "The boot loop"
    The first image with these drivers built in did not survive boot: penguins, text, restart, repeat. The watchdog did its job, but restarting into the same broken kernel helps nobody. The owner had to hold the recovery key combination, and the previous image was written back from the vendor system.

    Because the crash log was lost, the exact cause was never pinned down. What changed was the *method*: from then on, new audio drivers were built as **modules** that are not loaded automatically. They are loaded by hand over SSH after boot. If one crashes, the phone resets into a system that works, and the log survives.

## Stage 2: codec, mixer, sound card

Next came the codec driver (playback only), the mixer setup and a "machine driver" that ties I²S, mixer and codec together into a sound card. The codec was found at I²C address `0x04` — an address the I²C standard reserves, which is why the device tree has to mark it as a ten-bit address to get it accepted.

A sound card named `J701F` appeared and PipeWire picked it up. The first test tone failed with an I/O error: the I²S controller never started clocking. This SoC uses an *older* register layout than the one the "Exynos 7" name suggests. With the matching variant selected, data flowed.

And the speaker stayed silent.

## Stage 3: the last three switches

From here, progress depended on the one instrument no remote tool can replace: the owner's ears.

| Attempt | What was fixed | What was heard |
| --- | --- | --- |
| 1 | — | Nothing |
| 2 | The four I²S wires between mixer and codec were never switched to their audio function (pin control) | Nothing |
| 3 | On this phone the codec's master clock leaves the mixer on a different pin (a board option in the vendor device tree) | Clicks |
| 4 | The mixer's "channel 1 enable" bit, which lets application audio into the mix | **The notes — very loud** |

The clicks were good news: they were the speaker amplifier switching on and off, which meant the analog half worked and only the digital path was still broken.

## Polishing

- **Too loud, then distorted.** The speaker gain register accepts 0–15, but the vendor's own comment gives the real range as 0–9. The control is now capped at 8.
- **Hiss after a sound.** The amplifier stayed on for a few seconds after playback. It is now switched off immediately.
- **A click at the start.** The codec is kept digitally muted until the audio stream has really started.
- **The second sound never played.** The vendor power-down sequence clears register bits that were also exposed as user switches, leaving the path "off". Those switches were removed.
- **Volume keys did nothing.** Without a decibel scale the desktop saw only nine coarse steps, and a 5 % key press rounded back to where it was. Adding the vendor's scales fixed it.

## Where sound stands

The speaker plays, system sounds are clean, the volume keys work, and the drivers load at boot behind the same reset guard as the frequency limits. Recording from the main microphone was added the same way, by lifting the vendor's power-up sequence, and was checked without anyone listening: the phone played a quiet tone and found that tone in its own recording. Headphones and the earpiece are written but untested. The second and headset microphones, headset detection and call audio are not ported.
