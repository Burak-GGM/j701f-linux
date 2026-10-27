# Lessons and pitfalls

A list of things that cost time, so they do not have to cost it twice. Each entry says what was seen, what the cause was, and what to do.

## Method

**Change one thing per image.** Every stage that went smoothly changed one thing. The one image that combined several new built-in drivers produced a boot loop with no way to tell which part was responsible.

**A success code is not a result.** Drawing calls returned success with a black screen. A tone "played without error" into a silent speaker. A benchmark ran against a blanked display. Decide what the real observable is — pixels, sound, a number read back from hardware — and check that.

**Measure the vendor system before guessing.** CPU voltages, GPU steps, the USB switch registers, the audio PLL frequency: all were read from the phone while the vendor kernel was running. Where values were assumed instead, they were usually wrong.

**Keep the failures.** `kernel/rejected-trials.json` and the incident notes in `docs/j701f-mainline.md` have prevented the same dead end more than once.

**New and risky means "off by default".** Frequency limits start at the bootloader's values; audio drivers are modules loaded after boot. A hang then leads to a reset into a working system instead of a loop.

## Boot and flashing

| Seen | Cause | Do |
| --- | --- | --- |
| Odin upload of the root filesystem rejected | Samsung's sparse image format differs from Android's generic one | Produce the vendor's chunk format; compare with a vendor image first |
| Boot loop: logo, text, restart | A built-in driver crashing during early boot; the watchdog restarts into the same kernel | Hold Power + Home + Volume Up, write the previous image back. Build new drivers as modules |
| A prepared update refuses to run | It expects a different image in `BOOT` than is there | Run `prepare-boot-update.py` again |
| U-Boot link fails with "Error 135" | The PC's `/tmp` (a RAM disk) is full of old build directories | Delete `/tmp/j701f-uboot-embedded-source/out-uboot-j701f-*` |
| "mounting fs with errors" on every boot | Hard resets left half-deleted files; the safe `e2fsck -p` refuses to fix them | One boot with `/etc/j701f-fsck-mode` set to `-fn` to read the report, then `-fy` to repair, then remove the file |
| GPU stuck at 343 MHz after an ordinary reboot | The reset guard mistook a quick reboot for a crash | Fixed by `j701f-stamps.stop`; otherwise remove the stamp file |

## Kernel and device tree

| Seen | Cause | Do |
| --- | --- | --- |
| No USB device on mainline | The MUIC switch between SoC and connector is open | Two I²C register writes from the initramfs |
| Wi-Fi chip does not answer | An added pin configuration held its power-enable line low | Do not add pin settings you cannot justify |
| Touch delivers one interrupt, then nothing | Edge-triggered interrupt on a level-signalled chip | Use level-low |
| Touch device ignored by the desktop | One axis reported zero resolution | Patch the driver to fill it in |
| eMMC became `mmcblk1` | A second MMC controller was enabled | Add `mmc0`/`mmc1` aliases |
| Kernel image far too large | Every SoC family enabled | Disable all `ARCH_*` except Exynos |
| I²S stream opens, every write fails with I/O error | Wrong register-layout variant; the controller never clocks | This SoC uses the old "v5" layout: `samsung,s5pv210-i2s` |
| eMMC in HS200: card starts, then every write fails | Mainline lacks this SoC's per-speed pin drive strengths and fine tuning | Stay on DDR52. Never test a storage timing mode on a read-write root; test from the initramfs first |
| Clock ends up at 4/5 of the wanted rate | Asking a divider for slightly less than its parent can give | Ask for a little more, as the vendor does |
| Audio PLL rate looks impossible | Described as an integer PLL; it is fractional | Compare with the rate the bootloader left |
| Codec address rejected | `0x04` is a reserved 7-bit address | Mark it as a ten-bit address in the device tree |
| Speaker clicks but no tone | Analog path fine, digital audio not reaching the codec | Check pin functions, the master-clock routing, the mixer's channel enable |
| Controls switch themselves off after playback | A power sequence and a user control share register bits | Do not expose bits a sequence owns |
| Volume keys have no effect | Volume control without a decibel scale | Add the scale |
| Bluetooth address from the device tree is ignored | After the patch firmware loads, the chip reports a default address the kernel does not recognise as "unset" | Add that address to the driver's list of defaults |
| Hardware video codec: registers work, firmware never starts, no interrupts | The SysMMU in front of the codec resets to "enabled and blocked", not to pass-through | Switch it to bypass (or drive it properly) before starting the codec. Check a SysMMU's control and status registers before assuming it is transparent |
| Hardware decoder works at 720p but fails on small videos | Without an IOMMU all buffers must lie above the codec's firmware; small buffers were allocated below it | Give the codec its own memory region so the firmware is the lowest allocation |
| Factory trim values read as zero | The registers keep their value over a warm reboot and had been overwritten | Write the factory values back when idle |

## Debugging on the live phone

| Seen | Cause | Do |
| --- | --- | --- |
| Reading a regmap `registers` file in debugfs kills the reader with a kernel oops; the next reboot hangs | The dump touches every register of the block; some PMU registers fault, and the lock stays held | Never dump a whole MMIO regmap. Read single, known registers |
| Phone frozen with the screen on after `reboot` | A hang after the watchdog was stopped for shutdown | Volume Down + Power for ten seconds |

| The video codec hangs after its power domain was switched off and on by hand | The domain also holds the codec's clock controller; a bare register write resets it behind the kernel's back | Leave a domain alone unless nothing in it is used; a domain in use needs a real driver |

## Desktop

| Seen | Cause | Do |
| --- | --- | --- |
| Black screen after the Plasma logo | Session manager needs Xwayland | Install it; create `/tmp/.X11-unix` |
| Phone "reboots" on a short power-key press | elogind's default action | Set the power key to "ignore" |
| Firefox window black or half-drawn | Mesa shader compiler bug on this GPU family | Software rendering for Firefox; Angelfish for GPU rendering |
| A video in Firefox never starts | `/tmp` was 16 MB and filled up | `/tmp` is now 256 MB |
| Screenshots come out as broken PNG files | The display scale changed, so the capture is no longer 720 × 1280 | Use the size the capture tool reports |
| Black areas in the browser; kernel warnings in `panfrost_gem_open` | The kernel discards GPU buffers that Mesa marked as disposable, including ones the browser's other thread still imports | Local Panfrost setting `shrinker_purge=2`; see [performance](performance.md) |
| After "never discard GPU buffers" the home screen did not start | The desktop allocates up to 1.2 GB of GPU buffers for a moment at start; with nothing reclaimable an allocation failed | Never pin a cache to cure a symptom: measure what it holds first (`/proc/PID/fdinfo` shows GPU memory per program) |
| An application "hangs" after five minutes in the background | It was stopped on purpose by the background freezer | It continues when activated; exclusions and the off switch are in `~/.config/j701f-freezer.conf` |
| Everything on screen runs at half the frame rate when the brightness is turned down | With no backlight device the compositor darkens the picture in an extra rendering pass | Give it a backlight device, even a software one applied in the kernel's frame copy; Plasma also needs `polkit` running and an "internal" connector type to use it ([details](performance.md#frame-rate-the-display-path)) |
| A graphics test reports nothing, or wildly different numbers from one run to the next | The lock screen was up (applications hidden), or the screen had dimmed | Unlock and simulate user activity before every measurement |
| A GTK 4 application shows black areas | GTK's GL renderer with its default optimisations does not draw correctly on Panfrost/Mali-T830 | `GSK_RENDERER=gl GSK_GPU_DISABLE=all` (the software renderer `cairo` also works but is slow) |
| A killed command took the SSH session with it | `pkill -f NAME` matched the shell running it | Match on a path that only the target has |

## Working remotely

- Wake the display before any screenshot or graphics test.
- Do not put placeholders in commands meant to be pasted; they get pasted as they are.
- When the owner is away, anything that could need Download Mode waits.
- Some things cannot be verified remotely at all: sound, physical keys, how something feels. Say so plainly and ask.

## A good number can mean nothing happened

VLC with the hardware video decoder used a third of one processor core and reported no late frames. It was also showing a black window: the decoder had delivered one picture and stalled. The measurement was taken as proof that the setting worked, and nobody looked at the screen until the owner did. Since then a video test includes a dump of the framebuffer during playback and a count of the pixels that are not black.

## Do not rearrange a running desktop to measure it

To see whether KWin's blur effect cost frames, the effect was loaded and unloaded in the running session. The desktop shell was using Wayland interfaces those effects provide, lost its connection with a protocol error and exited; the phone showed a session without a shell until it was restarted by hand. Compare such settings across a restart of the session, not inside one.

## A safety net that stays down silently is a fault of its own

Raising the GPU and processor speed limits after boot is guarded by a stamp file: if the phone resets while the stamp exists, the next boot leaves the limits low. It used to leave them low on every boot after that, until somebody removed the file - and nothing said so. One deliberate reboot at the wrong moment left the phone at a third of its GPU speed for a session, during which several measurements were taken and the home screen was judged slow. A guard should cost one boot and then try again, and it should be visible when it has tripped.

## A number nobody questions

The battery percentage had been listed as "working" since the fuel gauge driver first loaded: it showed a number, the number moved. On 2026-10-13 it read 43 % on a battery the charger called full. The chip counts charge and drifts unless someone corrects it near full and near empty, which the vendor kernel does and the mainline driver does not - so the number had been wrong by an unknown amount all along. What caught it was comparing two things that must agree (the percentage and the cell voltage); `tools/phone-health.sh` now makes that comparison every time it runs. A value that is merely present has not been tested.

## The same fix does not survive a second edit

`tools/build-kernel.py` applies each local patch once and records that. When a patch was edited later, the tool tried to apply the new version on top of the old one, failed, and the habit grew of copying the changed file into the work tree by hand - which works until the tree is rebuilt from scratch and the hand-carried state is gone. The tool now keeps a copy of what it applied and takes the old version out first. If a tool makes the correct way harder than the shortcut, the tool is what needs fixing.

## An installer meets the hardware (2026-10-27)

The release installer passed every host test and still stopped four times on its first run on the phone. Each fault lived in something the tests had copied from a guess instead of from the device:

- **Which USB serial number the shell has.** The host looked for the stage-1 console's name; the mainline initramfs and the recovery call their gadget `j701f-diagnostic`. The recovery had received the first command, the host just never recognised the port.
- **A command that cuts its own line.** Stopping MTP unbinds the USB gadget; run from the USB serial shell, it hangs up that shell and dies before binding the gadget again, leaving the phone without USB. Anything that touches the gadget runs detached, and the caller waits for USB to come back.
- **A field that means "now".** `0` as the shadow "last password change" day tells PAM the password must be changed immediately; SDDM's autologin fails and the phone stops at a login screen. Leave the field empty.
- **Prompts in the output.** The serial shell's prompt can stick to the first line of output; parse by searching for the expected pattern, not by splitting lines.

The SD backup and the full read-back worked first time: the parts that were checked against the real phone beforehand (partition sizes, hashes, the BOOT marker) held.

## Small traps met again

- A command that kills processes by pattern (`pkill -f`) also matches the shell that carries the command, if the pattern appears in it: the session ends silently before anything else runs. Send such things as a script file.
- The computer's tool shell changed (to fish) and a command with an options variable ran as one word: nothing happened and nothing complained. Multi-step commands go through a `bash` script.
- A device-tree overlay handed to the kernel from a module must be aligned to eight bytes ("Invalid overlay_fdt header" otherwise).
- A module without an exit function cannot be replaced without a reboot; while developing, load test copies under another name.
