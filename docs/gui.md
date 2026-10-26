# First Qt GUI — 2026-10-08

This is a first graphical application for the existing Alpine system: a real QTermWidget terminal with a touch keyboard, directory browser, status page and an Exit GUI button. It is implemented in `gui/main.cpp`. Plasma Mobile and GPU acceleration are later milestones.

## Installed dependencies and build

The following were installed on the phone's existing DATA root through normal signed Alpine packages:

```sh
sudo apk add qt6-qtbase-dev qtermwidget-dev g++ pkgconf font-dejavu
cd /home/burak-alpine/j701f-gui
make
```

Qt is 6.11.1; QTermWidget is 2.4.0. The source, Makefile and trial wrapper are copied into `/home/burak-alpine/j701f-gui`. The app was compiled natively on the phone with warnings enabled. Development dependencies occupy substantially more space than a future runtime-only image; the full installed package set reported roughly 1.1 GiB after this installation.

## Temporary launch

From SSH, launch a three-minute trial with:

```sh
sudo /bin/sh /home/burak-alpine/j701f-gui/run-trial.sh 180
```

Run this over SSH or USB, rather than inside the native on-device terminal: the wrapper pauses that terminal during the trial. Exit GUI, terminal `exit`, or the timeout ends the trial and resumes the original terminal process and its existing shell. Startup has not been switched to this GUI. The wrapper also resumes paused processes if its shell receives a termination signal. A normal GUI exit restores the saved framebuffer pixels before resuming them.

The presenter runs as root because it needs framebuffer and input access. Its terminal drops to the existing UID 1000 `burak-alpine` using sudo; commands can use the previously approved `sudo` rule. Files shows directory names and supports entering a directory or returning to its parent; file editing is not implemented. The keyboard supports letters, numbers, Shift, Ctrl, Space, Delete, Enter, Escape, Tab, slash, hyphen and cursor keys. It is a preliminary keyboard, not a complete mobile input method.

## Graphics and input route

This kernel has no Linux virtual consoles and no DRM display nodes. The application uses Qt's `offscreen` software raster platform to render a 720 × 1280 QWidget tree, then presents that image through a small adapter for the framebuffer layout already measured on this phone. It activates/unblanks `/dev/fb0`, validates pixel format and bounds, handles the confirmed Samsung red/blue channel correction, and submits changed pixels without clearing the screen first. The current renderer collects Qt paint regions in screen coordinates and schedules one deferred redraw after those paint events. It updates only those regions in the RAM image; geometry and visibility changes conservatively redraw the whole interface. It compares rows against a RAM image before writing changed rows to the framebuffer, without reading mapped framebuffer pixels during every frame. This does not demonstrate Mali acceleration or KWin/Wayland support.

The input adapter selects the measured multitouch event device, exclusively grabs it for the session, and translates contacts into Qt mouse events for the touch widgets. The exclusive grab keeps GUI taps out of the paused original terminal's input queue. The grab is released on exit. No permanent device permission changes are needed for this trial.

Qt's general embedded Linux display/input interfaces are described in the [Qt documentation](https://doc.qt.io/qt-6/embedded-linux.html). Our presenter is a local adapter, rather than the stock Qt LinuxFB plugin. Plasma Mobile uses [KWin/Wayland](https://plasma-mobile.org/about/), which will require a separate graphics integration stage. Installing desktop packages alone does not establish a compatible GPU/display stack.

## Verification and limits

The native build passed. A five-second offscreen run opened the PTY, executed a shell command and returned UID 1000; the screenshot was visually checked for layout and keyboard fit. Reports: `build/phone-gui-build.txt`, `build/phone-gui-offscreen-test.txt`, and `build/phone-gui-preview.png`.

The first physical three-minute trial initialized successfully with `J701F_FRAMEBUFFER_READY 720x1280 swap_rb=1`, `J701F_TOUCH_READY event2` and `J701F_QT_GUI_READY`, then exited cleanly and logged `J701F_GUI_ORIGINAL_TERMINAL_RESUMED`. Its log is saved in `build/phone-gui-trial.txt`. The user confirmed the GUI and touch work but reported slower response than the original native terminal; the user did not separately confirm the return to that terminal.

An idle CPU measurement reproduced the excessive work: 771 process CPU ticks over eight seconds in the initial renderer, approximately 96% of one CPU core with Linux USER_HZ 100. The renderer was revised as described above. The same measurement then used 37 ticks over 8.01 seconds, approximately 4.6% of one core, around 21 times less CPU time. The revised 12-second idle trial submitted two frames, with 120 ms total presentation work and 76 ms worst frame time; startup accounts for one of these frames. Both trials exited cleanly and resumed the original terminal.

Comparative short trials are saved in `build/phone-gui-perf-before.txt` and `build/phone-gui-perf-after.txt`. The revised app logs total/worst rendering milliseconds and submitted frame count on exit. The second three-minute trial completed with status 0, two presented frames, 100 ms total presentation work, 50 ms worst frame time, and `J701F_GUI_ORIGINAL_TERMINAL_RESUMED`. It is recorded in `build/phone-gui-trial-optimized.txt`. That frame count indicates no further visible interaction in this trial; the user's responsiveness report is still pending. Idle CPU measurements and a clean timed exit do not prove touch responsiveness.

The revised running app used about 90 MB resident memory and the expected CPU mask 0–3 (`build/phone-gui-running-status.txt`). The wrapper passed shell syntax checking. This remains a manual trial application, with no change to normal GUI startup.

On 2026-10-08, the user reported that the revised application is actually fast overall, with a remaining delay specifically in the graphical terminal. This confirms the practical responsiveness improvement. The terminal's input/output-to-paint path was subsequently measured separately, as recorded below. CPU hotplug or missing GPU acceleration has not been established as the cause. The user did not separately report the Exit GUI return behavior.

## Terminal latency measurement and revision

The remaining terminal delay was measured on the running phone using the actual GUI and QTermWidget, with `--no-fb --latency-test`. Its test PTY runs a small shell echo loop with local echo and cursor blinking disabled. Sixteen unique tokens per run measure time to PTY receipt, the next normal terminal paint, and completion of our software image composition. This mode requires `--no-fb`, never opens the framebuffer or input devices, and does not run the user's login shell or write shell history.

Three runs of each behavior used the **same compiled binary and source hashes**; `--full-render --poll-render` selects the previous rendering behavior as a control. The comparison contains 48 samples per behavior:

| Measurement | Full interface redraw, 30 ms polling | Partial redraw, deferred event scheduling |
| --- | --- | --- |
| Median PTY-to-image time | 78.51 ms | 16.33 ms |
| 95th percentile | 98.47 ms | 17.33 ms |
| Median image rendering work | 56.66 ms | 1.27 ms |
| Median PTY response | 2.08 ms | 2.14 ms |
| Median Qt paint delay after receipt | 11.44 ms | 11.46 ms |

The median measured path improved about 4.8 times. Most of the original cost came from repainting the whole widget tree for a small terminal change. The revision also removes the 30 ms polling wait. QTermWidget's paint delay remains; these results do not identify a CPU hotplug or GPU defect as its cause.

`--check-render` compares the complete 720×1280 output image against a separate full redraw after every submitted frame. A native phone run passed 29 frame comparisons, including eight automated interactions covering Files/Status/Terminal page changes, Shift/Ctrl state changes, keyboard input and parent-directory navigation. These are Qt widget interactions, not physical touchscreen tests. Region rendering uses the source region's bounding-box origin as the target offset, as described by [QWidget::render](https://doc.qt.io/qt-6/qwidget.html#render); the comparisons check that changed areas land at the correct image coordinates and unchanged areas stay valid.

Reports and exact source bundles are in `build/gui-latency/`. `comparison.json` combines `full-render-control.json` and `event-render-optimized.json`; `event-render-check.txt` contains the pixel comparison markers. Repeat the RAM-only checks with:

```sh
python3 tools/benchmark-gui.py --phone 192.168.1.140 --label control --full-render --poll-render
python3 tools/benchmark-gui.py --phone 192.168.1.140 --label optimized
python3 tools/benchmark-gui.py --phone 192.168.1.140 --label pixels --runs 1 --check-render
```

`tools/install-gui.py` requires matching source hashes, at least 48 optimized samples and the full-image comparison report. It rebuilds in phone RAM, requires the same compiled binary hash, repeats the offscreen latency/pixel checks, preserves the previous manual GUI files, and replaces the manual-launch binary. It does not launch an on-screen session or change startup.

Installation succeeded with binary SHA-256 `10583aae330f4631083ec106d10287cdd1562a5c13051431990e12509d81f097`. The previous files are in `/home/burak-alpine/j701f-gui/backups/latency-10583aae330f`, with their checksums in the adjacent `.sha256` file. The installation repeated all 29 full-image comparisons and eight interactions successfully. Reports: `build/gui-latency/install.txt` and `install.json`. The existing manual trial command above launches this revision.

The measured times exclude physical touch acquisition, framebuffer conversion/copy/pan and panel scanout. The existing interactive CPU governor was left unchanged, so the measurements are sequential trials rather than a frequency-pinned performance study. Physical typing responsiveness and the revised framebuffer presentation still require a later supervised GUI trial.

CPU hotplug remains unresolved: the tested Android header argument did not reach the kernel, and the original working BOOT was restored and checksum-verified. Four working cores are sufficient to try this GUI. See [CPU diagnosis](admin-cpu.md).

These GUI packages and files are live changes on DATA. Existing `build/system` flashing images predate this provisioning; reflashing DATA would erase it and the private Wi-Fi/SSH setup. This GUI stage does not replace BOOT, recovery, SYSTEM, Samsung's early bootloader or the current init service configuration.
