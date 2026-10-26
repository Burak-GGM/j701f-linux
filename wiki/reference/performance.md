# Performance and tuning

After the critical drivers, making the phone *feel* usable is the main goal. This page records what was measured, what was changed and what each change bought. Numbers are from the phone itself; where something was not measured it says so.

## Where the time goes

| Measurement (2026-10-10) | Result |
| --- | --- |
| Angelfish, cold caches, six restored tabs: start → web view exists | 10.2 s |
| Same with two restored tabs | 7.5–7.9 s |
| Same, warm caches | 5.8 s |
| Settings application: busy after start (warm, rough) | about 7 s |
| Terminal (foot): busy after start | about 1 s |
| CPU frequency during an application start | at the 1586 MHz maximum almost throughout |
| GPU while scrolling a web page | lightly loaded (about a quarter busy at full brightness); see the next section |

A system-wide profile (`perf`) of a browser start corrected the first impression that start-up is simply "CPU-bound". The processor does run at full frequency, but on average only about one and a half of the eight cores are busy: the start is a chain of single-threaded steps, plus waiting for storage when the caches are cold. Where the 5.4 seconds of a warm start go:

| Step | Time |
| --- | --- |
| Loading the program and linking its libraries (the browser engine alone is a 172 MiB library) | 1.4 s |
| Starting the browser engine and its GPU process | 1.0 s |
| Loading the user interface (QML) | 0.9 s |
| Loading the ad-block lists | 1.2 s |
| Creating the first web view | 0.8 s |
| Each further restored tab | about 0.25 s |

Two things follow from that:

- **Cold versus warm is 1.6 seconds**, all of it reading files. A boot script now reads the browser engine into the page cache 75 seconds after start (2.4 seconds of background reading), so the first start after boot is already a warm one.
- No single step dominates, so there is no cheap trick left that halves the time. A faster memory allocator (mimalloc, preloaded) was tried: 0.4 s quicker for 50 MB more memory per application, not adopted. The effective answer is not to start applications at all: leave them open and let the [background freezer](#applications-in-the-background) keep them from costing anything.

Fewer restored browser tabs helps as well (the first measurements were taken with six).

**Start-up is sensitive to things that look unrelated.** Repeating the same measurement on every image of the night (three runs each) showed two steps: 5.9–6.0 s on the early images, 6.6–6.7 s once the faster display path was in, and 7.0–7.3 s while the keys were wake-up sources as well. The last step was removed again. The middle one is the current state: the browser takes about 0.7 s longer to show its first view than it did when the screen was drawn at 38 frames per second. The raw speed of the processor, of memory and of starting a process is identical on all of these images, so this is something in how the application and the faster compositor interact; it has not been tracked down.

**What did help:** telling Qt Quick to draw from the application's main thread instead of a separate render thread (`QSG_RENDER_LOOP=basic`). Three starts each: 6.0–6.3 s with the default, 5.5 s with `basic`, and the scroll test is unchanged (52.7 against 52.3 callbacks per second). A start with the window hidden behind the lock screen takes 5.7–6.0 s, so about half a second of a normal start is drawing frames nobody needs yet. The setting is applied to Angelfish only, through a copy of its launcher in `~/.local/share/applications/`; it has not been tried on the home screen or other applications.

## Frame rate: the display path

How smooth the screen feels is decided by the path from the compositor (KWin) to the panel, not by the GPU. There is no real display driver yet, so for every frame KWin renders on the GPU, reads the picture back, and the kernel converts and copies it into the bootloader's framebuffer.

| Measurement (2026-10-10) | Result |
| --- | --- |
| The GPU alone, drawing a small test scene off-screen | about 3460 frames per second |
| The same kind of scene through KWin, full screen | 38 frames per second |
| …after the device-tree change below | 44 |
| …with the faster copy routine in the kernel (current state) | 49.5 |
| …current state while the screen is being touched (frequency floor raised) | 54 |
| …with NEON copy loops and the 902 MHz screen-on floor (current), full brightness / dimmed | 55 / 51 |
| KWin's own rendering time per frame | 3 ms |
| From the end of rendering until the frame is on the framebuffer | 25–50 ms |
| Scrolling a test page in Angelfish (browser callbacks per second, median interval) | 45 per second, 16.7 ms |
| The same at 50 % brightness, before the backlight fix below | 18 per second, 50 ms |

What follows from this:

- **Brightness used to halve the frame rate; that is fixed.** With no backlight control, KWin darkened the picture itself in an extra, expensive rendering pass (42 → 20 frames per second at any brightness below 100 %, and whenever the screen dimmed after being idle). Now the kernel offers a backlight device, `/sys/class/backlight/j701f-panel`, and applies its level to each pixel while the frame is being copied anyway. Plasma uses it like any real backlight. A first version held 49 frames per second only for a few seconds and then settled at 32 at the owner's 89 % setting; with the copy loops rewritten in NEON it is a steady 55 at 100 % and 51 at any lower setting. Two things were needed besides the kernel patch: the display connector is now reported as DSI, so Plasma treats the screen as the built-in panel, and the `polkit` service was installed, without which Plasma's backlight helper cannot write the level. (Offering KWin a gamma table instead was tried first and does not work; KWin does not use one for brightness.)
- **The framebuffer copy was needlessly slow.** The kernel treated the framebuffer as device memory and wrote it through a slow accessor. Naming the reserved memory region in the device tree (`memory-region`) lets it use ordinary memory access: 26.5 → 23 ms per frame. The pixels were checked by reading the framebuffer memory back and comparing it with a screenshot. A local kernel patch then replaced the conversion routine itself (two pixels per 64-bit operation, no temporary buffer): 44 → 49.5 frames per second. Mapping that memory cacheable was also tried and gave nothing; that patch is kept under `kernel/patches/staged/` for reference.
- **The CPU frequency governor holds the pipeline back.** Drawing a frame is many short steps on several threads, none of which looks busy, so the governor leaves the frequency low. A small service (`j701f-inputboost`) keeps the frequency floor at 902 MHz whenever the screen is on (546 MHz when it is off) and raises it to 1144 MHz while the screen is being touched and for 3 seconds afterwards: 49.5 → 52–53 frames per second untouched, 54 while touching.
- **Browser switches make no difference to scrolling.** With GPU rasterisation on, off, or no switches at all, the scroll test gave the same 45 per second.
- The remaining gap to 60 needs the real display driver, where the GPU's picture goes to the panel without any copy.

Two traps in measuring this: the lock screen hides every application (a hidden test draws nothing and reports nothing), and a web address given to Angelfish on the command line opens in a background tab behind the restored ones.

## Black areas in the browser

Symptom: black rectangles while scrolling in Angelfish. What the kernel log showed while the browser ran under memory pressure: bursts of Panfrost "Purging …" lines and `WARNING … panfrost_gem_open`.

The mechanism, as far as the evidence goes:

- Mesa keeps recently freed GPU buffers in a cache and tells the kernel they may be thrown away ("purged") when memory is short.
- The warning's call trace shows the browser's two rendering threads (`Chrome_InProcGpu` and `QSGRenderThread`) importing buffers from each other that were in exactly that throw-away state.
- A buffer that is purged while the other thread still shows it has no contents any more.

This is the working explanation, **not a proven one**: the automated screen captures never caught a black area, with or without the change, so only use of the browser can confirm it.

The fix is a small local kernel patch that adds a setting, `/sys/module/panfrost/parameters/shrinker_purge`:

| Value | Behaviour | Result on this phone |
| --- | --- | --- |
| `1` | Upstream: purge anything marked as disposable | 3–7 warnings per browser run |
| `0` | Never purge | Tried first and rejected: the on-screen keyboard alone kept 220 MB of GPU memory pinned, and at the next start of the desktop a GPU allocation failed and the shell did not come up |
| `2` | Purge only buffers nobody else refers to; a buffer that a second user opens becomes "needed" again | **Used.** No warnings in two runs under 700 MB of artificial memory pressure, while purging still frees memory (Shmem 270 → 36 MB in one check) |

## What happens to memory when the desktop starts

Sampling memory once a second during start-up showed a spike: for a few seconds the desktop allocates 600–900 MB of GPU buffers, then lets go of almost all of it. With purging switched off that spike reached 1.26 GB and pushed everything else into swap; with setting `2` the kernel reclaims those buffers as they become disposable. One minute after start:

| | Free memory | GPU/shared memory |
| --- | --- | --- |
| Purging off (setting `0`) | about 485 MB | 568 MB |
| Setting `2` | about 1000 MB | 115 MB |

The spike comes from two programs, measured per program from the kernel's GPU accounting: the home screen (plasmashell, about 560 MB for a moment) and the on-screen keyboard (about 240 MB). In both, nine tenths of it is memory they have already finished with and that is merely waiting in Mesa's cache, which is exactly what the kernel may reclaim.

## Memory

| Change | Why |
| --- | --- |
| 1.2 GB compressed swap in RAM (zram), enabled at every boot | There was no swap at all; one heavy page pushed the desktop into reclaim |
| `swappiness` 100, `page-cluster` 0 | Swapping to RAM is cheap; reading ahead from it is pointless |
| …but `swappiness` 10 for the first 75 seconds, then one explicit reclaim pass | While the desktop starts, the GPU spike described above made the kernel swap out 270–290 MB of the desktop it had just loaded. Now nothing is swapped during start-up, and the leftover GPU buffers are reclaimed once (374 → 101 MB) |
| `earlyoom` service | When RAM and swap are nearly exhausted it ends the largest web renderer instead of letting the desktop freeze; it never touches the compositor, the shell or the audio daemons |
| Browser switches (`QTWEBENGINE_CHROMIUM_FLAGS`): low-end device mode, at most three renderer processes, four raster threads | Browser memory (PSS) with three tabs went from 782 MB to 764 MB — a small gain; kept because it also bounds the number of processes |
| Update notifier and calendar-alarm autostart entries disabled for the user | Background processes nobody uses on this phone |

## Applications in the background

An application that has been out of the foreground for five minutes is **stopped**: it keeps its window and its state but gets no CPU time, and because it no longer touches its memory, the kernel can move that memory to compressed swap when something else needs room. The moment its window comes to the front again it continues. Applications are not closed.

A small service in the user's session does this (`j701f-freezer`). KWin tells it which window is in front; it stops and continues whole process trees, so a browser's helper processes are included.

Never stopped:

- the home screen, the compositor, the on-screen keyboard, terminals, the dialer and the messaging application;
- anything that is playing or recording sound at that moment;
- anything while the home screen is in front (so the task switcher always shows live applications);
- programs named in the configuration file.

If KWin needs an answer from a stopped application — for example because it was closed from the task switcher — the service continues it at once; in a test the application closed about two seconds after the request.

The lock screen counts as an ordinary foreground: applications left open behind a locked screen are stopped after the idle time. The side effect to know about: **a stopped application cannot receive messages or finish a download.** A chat client that should stay reachable belongs in the exclusion list.

Settings are in `~/.config/j701f-freezer.conf` and are read again every 15 seconds:

```ini
enabled = 1          # 0 switches the whole thing off and continues everything
idle_seconds = 300
exclude =            # program names, comma separated
```

What it does is logged in `~/.local/state/j701f-freezer.log`. Verified on the phone with two applications: stopped after the idle time, continued on activation, closed correctly while stopped. Not yet measured: how much memory and battery it saves in daily use.

## Storage

| Change | Effect |
| --- | --- |
| eMMC in DDR52 instead of the legacy mode | Sequential read 22 → 60–80 MB/s |
| Root filesystem mounted `noatime` | No write for every file read |
| Read-ahead 512 KiB | Fewer round trips when an application's files are read at start |

## Desktop

- Animation duration halved (`AnimationDurationFactor` 0.5).
- KWin runs without the blur and background-contrast effects (they were already off).
- The display scale is 160 % (logical 450 × 800). Fractional scaling makes every application render at a non-integer factor; whether an integer scale is noticeably faster has not been measured.

## Video

Hardware H.264 decoding works through the Samsung codec (H.264, HEVC and VP8 give exactly the pictures of the software decoder, MPEG-2 nearly; a local patch was needed because the upstream driver threw away the first key frame of everything except H.264. MPEG-4 part 2 does not start) ([details](userspace.md)). A 720p H.264 file needs about 24 times less CPU time than software decoding. `mpv` uses it; VLC does not (its attempt showed a black window, see [userspace](userspace.md)); the browsers do not yet, so video inside the browser is still decoded on the CPU.

## Where the settings live

| File on the phone | Source in the repository |
| --- | --- |
| `/etc/local.d/j701f-tune.start` | `system/tune` |
| `/etc/conf.d/earlyoom` | `system/earlyoom.conf` |
| `~/.config/plasma-workspace/env/j701f-webengine.sh` | `system/session/webengine-env.sh` |
| `/etc/local.d/j701f-gpufreq.start` (CPU and GPU frequency limits) | `system/gpufreq-limit` |
| `/usr/local/sbin/j701f-inputboost` (started by the tune script) | `system/inputboost` |
| `~/.local/lib/j701f-freezer/`, `~/.config/autostart/j701f-freezer.desktop`, `~/.config/j701f-freezer.conf` | `system/session/freezer/` |

## Not done yet

- A real display driver: today every frame is copied to the bootloader's framebuffer, with no hardware vertical sync, and brightness is applied in software rather than by the panel.
- Hardware video decoding inside the browser.
- A comparison with the phone's Android figures using a standard benchmark.

## Application start-up, first table (2026-10-10)

`tools/app-start-bench.sh` starts an application on the phone, waits until it has stopped using the processor for a second, and reports the time, the processor time used and the memory. Once after emptying the file cache, once warm.

| Application | Cold | Warm | Processor time | Memory |
| --- | --- | --- | --- | --- |
| Settings | 7.3 s | 4.8 s | 5 s | 128 MiB |
| Calculator | 9.3 s | 7.3 s | 6–7 s | 135 MiB |
| Gallery (Koko) | 7.0 s | 4.3 s | 4–5 s | 100 MiB |
| Podcasts (Kasts) | 7.8 s | 5.3 s | 5 s | 139 MiB |
| AudioTube | 9.5 s | 8.8 s | 9 s | 210–220 MiB |
| GNOME Software | 21 s | 22 s | 21–24 s | 160–180 MiB |

Clock, Weather and Pure Maps never come to rest - they keep drawing (Weather uses half a processor core just showing its page) - so this measure does not apply to them. Angelfish's figures were inconsistent because its web engine starts helper processes late.

What the table says: a warm start is hardly faster than a cold one, so storage is not the brake. Each Qt application spends four to seven seconds of pure processor time before it is ready, a GTK one over twenty. The cause inside the toolkits has not been looked for yet.

A first profile of the calculator's start shows where that processor time goes: about a third in the C library's dynamic loader (Alpine's musl resolves every symbol of every library and plug-in when the program starts), a fifth each in Qt's QML engine and Qt Core. The caches for compiled QML and shaders exist and are used. This is one profile of one application; no remedy has been tried.

Measured directly on 2026-10-13: the loader alone, with nothing else of the program running (`/lib/ld-musl-aarch64.so.1 --list PROGRAM`, which loads every library and resolves every symbol and then exits), median of six runs with everything in the file cache:

| Program | Libraries | Loader time |
| --- | --- | --- |
| Calculator | 94 | 0.54 s |
| Settings | 97 | 0.57 s |
| Gallery (Koko) | 134 | 1.09 s |
| Angelfish | 170 | 1.12 s |
| GNOME Software | 126 | 0.81 s |

That is the part paid before the program's first own instruction; the plug-ins a Qt application loads afterwards (QML modules, platform and style plug-ins) are resolved the same way and account for the rest of the loader's share in the profile. So between half a second and a second of every start is spent in the loader before anything else, on a warm cache, and the remedy would be in how the distribution builds its libraries (fewer, or pre-bound, symbols), not in this port. For the loader's share this is the floor on this processor and distribution. A second profile of the calculator the same day (warm start, 8 seconds, sampled 499 times a second) gives the whole picture: loader 27 %, Qt's QML engine 17 %, the kernel 16 % (mostly handing out and clearing memory pages), Qt Core 15 %, Qt Gui and Quick 4 % and 3 %, the GPU driver 3 %, the calculator's own mathematics library and the XML parser it reads its definitions with 6 % together, fonts 1 %. Inside Qt no single function takes even one per cent: the time is spread over creating and connecting thousands of small objects. There is no hot spot to remove. What does help today is not starting at all: the freezer keeps recently used applications in memory.

## Home-screen gestures (2026-10-10, native display driver)

`tools/ui-frame-bench.sh` injects a finger gesture and counts the frames that were really presented while something moved.

| Gesture | First measurement | With the GPU limit restored |
| --- | --- | --- |
| Top panel down and up | 52–54 per second | 54 |
| Application drawer: the animation after the finger lifts | 20–40 per second | 55–60 |
| Home pages left and right | 24–25 per second | 42 |

The first column was measured on a phone that was, unnoticed, running with its GPU held at the boot loader's 343 MHz: a safety stamp that guards the raising of the speed limits after boot had been left behind by a deliberate reboot, and it used to stay until removed by hand. The start-up script now lets such a stamp cost one boot only. KWin's blur effect is not active on this phone; switching it on for a comparison made the top panel slower.
