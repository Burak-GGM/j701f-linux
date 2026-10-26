# 11. A first camera

**Goal:** a picture from the phone's camera in an ordinary camera application.

The first roadmap put the camera last, "because it is the hardest". On Android this phone's cameras are run by FIMC-IS: a large Samsung driver plus closed firmware for an image processor inside the SoC. None of it exists in mainline Linux, and there is no documentation.

## The question that made it possible

The useful question was not "how do we port FIMC-IS" but "what is the least hardware a frame has to pass through".

```text
sensor → CSI-2 receiver → image processor → memory        (Android)
sensor → CSI-2 receiver → memory                           (here)
```

A camera sensor sends raw pixel values over a fast serial link. A receiver in the SoC takes them in. On Android they then go through the image processor, which turns them into a finished picture. But this SoC's receiver can also write what it receives straight into memory, and turning raw pixels into a picture is something software can do: libcamera has a software image processor for exactly this case. So the closed part could be left out altogether.

## Five milestones

1. **Is it there?** Power the rear sensor in the vendor's order and read its identity over I²C. A small test module; the answer was the right chip number.
2. **One frame.** Program the sensor with the vendor's register table for one mode, point the receiver at a piece of memory, look at what arrives.
3. **A frame that is a picture.** The first frames came with checksum errors. The camera block's clocks were still on the slow oscillator the bootloader leaves them on; with three selectors switched to the real clocks the errors stopped.
4. **The other camera.** The front sensor streamed and its receiver saw nothing. The vendor's PHY driver sets one more bit in a system register than the mainline one knows about.
5. **A real camera device.** A driver that presents each sensor the way Linux expects, so that libcamera - and with it Plasma Camera - finds "Internal back camera" and "Internal front camera" without knowing anything about this phone.

## Things nobody tells you

- **libcamera's generic pipeline only accepts a list of known platform drivers.** The driver here gives its name as one from that list. It is a workaround and is labelled as one; the clean fix is one more line in libcamera.
- **The software image processor needs a kind of memory buffer the kernel in `BOOT` could not provide.** The kernel's own driver for it was built separately as a module rather than building a new kernel.
- **Processing on the GPU crashed in about one start in three.** The session tells libcamera to use the CPU: about 50 ms per frame, good enough for a preview.

## Two mistakes worth their paragraphs

**A shared switch.** Both sensors' interface voltage is switched by one pin. Asking for that pin from two places "non-exclusively" worked - until a module was reloaded, and the kernel crashed in a way that also hung the reboot. The pin is now described once, as a regulator both sensors refer to, which is what a regulator is for.

**140 kilobytes too many.** A test of another data layout sized its buffer from the picture's dimensions and forgot that the layout used more bytes per pixel. The hardware wrote past the end of the buffer into whatever came next. The phone was restarted at once, before anything could depend on the damaged memory. A device that writes into memory by itself does not respect a C array's bounds; the buffer has to be sized from what the hardware will write, and checked.

## The owner's verdict

The first photographs the owner took were upside down. The rotation of a sensor cannot be read from anywhere; the first value had been a guess from the vendor's files, and it was wrong by half a turn.

Where it stands: preview, photographs and switching cameras work in Plasma Camera. Video recording produces an empty file, there is no autofocus, the resolution is a quarter of what the sensor can do, and the colours are whatever untuned software makes of them. It is a first camera, not a good one, and the work is paused.

## What to take from it

- Before porting a large vendor subsystem, ask which parts of it a result has to pass through. The answer may leave most of it out.
- Bring hardware up in steps that each prove one thing: identity, one frame, a clean frame, a device.
- When hardware writes into memory on its own, the size of that memory is a safety matter.

Reference: [Camera](../reference/camera.md).
