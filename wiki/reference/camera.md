# Camera

!!! success "Status: both cameras are ordinary Linux cameras (2026-10-10)"
    In Plasma Camera on the mainline kernel: live preview, taking a photograph and switching between rear and front camera work (tried with injected taps). **Video recording does not** - the file comes out empty. The owner has taken photographs with it; they came out upside down, the rotation was corrected, and a photograph confirming the correction is still awaited. Camera work is paused at the owner's request (2026-10-13).

## What works

Both sensors appear to libcamera as "Internal back camera" and "Internal front camera", so applications built on libcamera - Plasma Camera first of all - see them. The driver loads at boot.

| | Rear | Front |
| --- | --- | --- |
| Sensor | Samsung S5K3L2, 13 MP | Samsung S5K5E3, 5 MP |
| Mode offered | 2072 × 1552 (3.2 MP), 30 frames per second | 1280 × 960 (1.2 MP), 30 frames per second |

Colour, exposure and white balance are done by libcamera's software image processing on the CPU, about 50 ms per frame for the rear camera.

## How it works

Nothing of Samsung's camera software is used - not its driver, not its closed image-processor firmware.

1. **Sensor.** Powered in the vendor's order and programmed over I2C with the vendor's register tables for one mode.
2. **CSI-2 receiver.** This SoC's receiver has its own DMA output and writes raw Bayer frames straight into memory, as plain 16-bit samples when its packing is switched off - a standard V4L2 raw format. No further hardware block is needed.
3. **`tools/kmod/j701f_camera.c`.** For each sensor a media device with a sensor sub-device (exposure and gain controls) and a capture video node. The receiver writes into two buffers in turn and a small thread copies each finished frame to the application.
4. **libcamera** (Alpine's package, unmodified) with its generic pipeline and software image processing, then the application.

## What had to be found

- **Clocks.** The camera block's clock controller has no driver in our tree, and the boot loader leaves its selectors on the 26 MHz oscillator. Frames arrived with checksum errors until three selectors were switched to the real clocks.
- **The block's IOMMU** starts enabled with no page table, like the video decoder's; the driver sets it to pass addresses through while it captures.
- **The front camera's receiver** saw nothing although the sensor was streaming: the vendor PHY driver sets one more bit in a system register that the mainline PHY driver does not know.
- **libcamera only accepts known platform drivers** in its generic pipeline. The media device therefore gives its driver name as `qcom-camss`, a listed entry with software processing. Nothing else about it is Qualcomm's; the clean alternative is a libcamera with one more line in that list.
- **A dma-buf provider.** libcamera's software processing needs one and the kernel in BOOT has none; the kernel's `udmabuf` driver was built separately as a module, with one check removed that needs a function the kernel does not export.
- **GPU or CPU.** On the GPU path libcamera's test program aborted in about one start in three on this phone; the session sets `LIBCAMERA_SOFTISP_MODE=cpu` (`~/.config/plasma-workspace/env/j701f-camera.sh`, installed by the release since 2026-10-27; the first release lacked it and Plasma Camera crashed when switching cameras and lagged).

## Mistakes made on the way

- Requesting a GPIO shared by both sensors "non-exclusively" from two devices broke after a module reload and oopsed the kernel. The switch is now a regulator in the device tree.
- A test of the unpacked layout wrote 140 kB past its buffer: the size guard checked the sensor mode, not the bytes per pixel. The phone was rebooted at once; buffers are now sized from the layout.
- A test module left loaded made the first snapshot launchers fail for the owner with "FileNotFoundError".

## What is missing

- Full resolution (one mode per sensor so far), autofocus (the rear lens motor is not driven: it sits on `hsi2c@138b0000` at 0x0c, a bus controller the project's device tree does not enable yet; the rear EEPROM with the calibration is on the same bus at 0x58), flash while taking a picture.
- Sensor tuning: no colour matrix, no lens-shading correction; libcamera knows neither sensor and says so.
- Automatic exposure climbs slowly: in a dim room the picture needs a few seconds to brighten.
- Image rotation: the first guess for the rear camera gave upside-down photographs (the owner's report); it is 270° now. The front camera's 90° is the mirrored assumption and unchecked.
- Video recording in Plasma Camera produces an empty file. Not yet proven on the phone; the off-phone investigation of 2026-10-27 (below) points to memory.

## Video recording: what the computer can show

Plasma Camera 2.1.1 records by handing each preview image (a `QImage`) to QtMultimedia's `QVideoFrameInput`, with `QMediaRecorder` set to MP4, H.264 and MP3, and the default microphone attached. `tools/camera/qt-recorder-probe.cpp` repeats exactly that, built against the release's own AArch64 Qt 6.11.1 and run under `qemu-aarch64` on the computer:

- **The path itself works.** With and without a microphone the probe writes a valid MP4 (H.264 plus MP3). Qt 6.11 does not use the V4L2 hardware encoders for recording at all (its codec list switches `*_v4l2m2m` encoders off), so the encoder is always the software `libx264` with its default `medium` preset; Qt only sets the quality (`crf`).
- **Colour format.** From RGB images Qt picks YUV 4:4:4, so the file is H.264 *High 4:4:4 Predictive*, which hardware decoders (the phone's MFC included) and many players cannot play. Planar YUV 4:2:0 frames give ordinary *High* profile and let more frames through (56 of 60 instead of 18 at camera size).
- **Memory.** Peak memory of the recording process, 60 frames: 195 MB at 320 × 240, 485 MB at 960 × 540, 622 MB at 1280 × 720, **1.07 GB at 2072 × 1552** — the rear camera's frame size, which Plasma Camera's default "Auto" resolution records at. The phone has about 1.2 GB free with the desktop running, before the camera's own buffers; at that point the system swaps heavily and `earlyoom` (`-m 4 -s 8`) kills the largest process, the camera application. Either leaves an empty or truncated file.

Recording the camera-size frames at Plasma Camera's 540p preset brings the peak down to 403 MB, but the 4:3 picture is squeezed into 16:9 (960 × 540, square pixels): Plasma Camera only offers 16:9 presets. So 540p is a test, not a default. To confirm on the phone: record with the default setting while watching `free -m`, the swap and the earlyoom log; then set the video resolution to 540p (`videoResolution=1` in `~/.config/plasmacamerarc`, group `General`) and repeat. A lasting fix would send YUV 4:2:0 frames from Plasma Camera, record below the sensor size, and ideally use a lighter x264 preset, which Qt does not expose.
- Proper drivers for the block's clocks, power domain and IOMMU instead of register writes; the receiver's interrupt instead of polling; no copy per frame.
- Applications that use PipeWire's camera portal or plain V4L2 instead of libcamera have not been tried.

## Where things are

| Path | Contents |
| --- | --- |
| `kernel/dts/exynos7870-j7velte-camera.dts` | the two sensor nodes: buses, supplies, GPIOs, clocks, D-PHYs, orientation |
| `tools/kmod/j701f_camera.c`, `s5k3l2-tables.h`, `s5k5e3-tables.h`, `gen-s5k3l2-tables.py` | the driver and the converted vendor tables |
| `tools/kmod/udmabuf-out-of-tree.patch` | the change to the kernel's udmabuf for building it as a module |
| `system/camera/` | boot loader script for the modules, udev rule, session environment; `j701f-photo` (earlier snapshot tool) |
| `tools/kmod/j701f_cam_probe.c`, `j701f_cam_frame.c`, `j701f_cam_stream.c` | the three test modules of the bring-up |
| `build/kernel/vendor-camera-reference/` | the vendor files consulted (not part of the repository) |
