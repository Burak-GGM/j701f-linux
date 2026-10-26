# Measuring browser scrolling

`bench/scroll/` is a fixed local page for comparing Angelfish under the same
workload. Its 96 cards contain text, coloured patterns and shadows. There are
no external resources, audio or video. A content security policy also blocks
media and connections from the page.

The page scrolls at 700 CSS pixels/s, warms up for two seconds and measures for
twelve seconds. It records `requestAnimationFrame` intervals, their median,
95th and 99th percentiles, and intervals longer than 25 or 50 ms. The estimated
missed 60 Hz intervals are a calculation from callback gaps, not measured
display flips. The **Tap response** button records event-to-handler and
handler-to-next-callback delays while a run is active.

## What this can establish

Compare at least three runs with the same viewport, scale, kernel, browser
flags and restored tabs. Record CPU/GPU frequencies, temperature, memory,
swap and kernel warnings alongside the results. Change one variable at a
time. By default any viewport/scale change invalidates the run, as do a hidden
tab or an expired watchdog. A cancelled run is retained but is not a measurement.

Angelfish can hide its toolbar while scrolling, changing only the page height.
For that case select **Allow browser toolbar height changes** or pass
`--viewport toolbar` to the controller. This explicit policy accepts height
changes within 25% of the starting height, updates the scroll extent, and records
each change, its phase and the height range in `viewport`. Width/scale changes
and larger height changes still invalidate the run. The policy cannot identify
what caused a resize; it is not proof that only the toolbar moved. Compare runs
with the same policy and similar height ranges/events, and keep resize costs in
the measured intervals rather than deleting slow frames. `--viewport fixed`
retains the strict default.

Browser callbacks do not establish physical panel frame rate or input-to-photon
latency. Programmatic scrolling differs from finger scrolling. Neither a good
timing result nor a compositor screenshot proves that black areas are absent
on the phone. Those require a separate physical check. The page also does not
measure network speed or cold application launch.

## Run by hand

Serve only the benchmark directory on the laptop:

```sh
python3 -m http.server 8765 --bind 127.0.0.1 --directory bench/scroll
```

For the phone, forward that server over the existing pinned SSH connection:

```sh
ssh -N -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=build/phone-ssh-known-hosts \
  -R 127.0.0.1:8765:127.0.0.1:8765 \
  burak-alpine@192.168.1.158
```

While holding the coordination `phone` lock, open
`http://127.0.0.1:8765/` in Angelfish. Keep it in the foreground, press Start
and save the JSON. The laptop server and SSH tunnel must remain running.
Stop both after testing; no permanent server or boot setting is needed.

## Collect automatically

`tools/scroll-benchmark.mjs` attaches to exactly one **already-open** benchmark
tab through a loopback Chrome DevTools Protocol endpoint. It never opens or
navigates other tabs. Use Node 22+, or Node 20 with
`--experimental-websocket`. Qt WebEngine must have its debugging endpoint
enabled before Angelfish starts; restarting a browser or changing its launch
environment is a coordinated phone operation. Keep the endpoint on loopback
and tunnel it, rather than exposing it to the network.
Qt documents the host-and-port form of
[`QTWEBENGINE_REMOTE_DEBUGGING`](https://doc.qt.io/qt-6/qtwebengine-debugging.html).

Once a loopback endpoint is available on laptop port 9222:

```sh
tools/coord.sh lock phone codex "Angelfish scroll baseline" 15
node --experimental-websocket tools/scroll-benchmark.mjs \
  --scope phone --worker codex --seconds 12 --warmup 2 --viewport toolbar \
  --out build/bench/phone-baseline-01.json
tools/coord.sh unlock phone codex
```

Do not take a lock another worker is actively using. A phone run requires a
fresh matching lock with enough time remaining. The controller rejects an
existing output file. JSON contains the page's user agent, viewport, individual
intervals, aggregate statistics and the controller's expected asset hashes.
Those hashes identify local source files; they do not attest the browser's
cache. Reload the page after changes. Use `--scope host-check` for desktop
functional checks, never for phone performance evidence.

## Counters alongside a run

`tools/phone-perf-sample.py` collects bounded read-only samples over the pinned
SSH connection. It requires the same worker's phone lock. Start it immediately
before the browser run in another laptop terminal:

```sh
python3 tools/phone-perf-sample.py --worker codex --samples 24 \
  --out build/bench/phone-baseline-01-counters.json
```

Keep the lock until both programs finish. No file is installed on the phone.
The collector reads aggregate and per-core CPU ticks, reported CPU/devfreq frequencies,
thermal zones, available memory, swap and selected VM reclaim/fault counters.
PSI is explicitly marked unavailable where `/proc/pressure` is absent, as on
the phone at this checkpoint. A reboot or reset of counters invalidates the
aggregate. Truncated output retains completed samples and is not a valid run.
The tool refuses to replace an existing JSON file.

Samples include phone uptime and whole-second wall time; the browser report
includes its wall time and performance time origin. These allow approximate
alignment, not exact frame attribution. Sampling sleeps one second between
reads and records its own read duration: it adds load and is not exactly 1 Hz.
CPU busy percentage is averaged across all cores and excludes iowait; it cannot
rule out a single busy thread. Frequencies alone do not establish a bottleneck.
Compare the same condition with and without collection if its cost is material.

## Verification so far

On 2026-10-10 an isolated desktop Chromium instance completed a bounded run.
Seven browser checks passed: page identity, bounds rejection, repeated-run
geometry, cancellation, an injected input sample, resize invalidation and
hidden-page lifecycle invalidation.
The rendered page was inspected. A subsequent 13-check Chromium run verified
bounded toolbar resizing and geometry restoration, strict height rejection,
large-height rejection, scale/width rejection and the original lifecycle/input
checks. Evidence: `build/bench/host-toolbar-browser-checks.json`.
Other host evidence is in `build/bench/host-*`.
**No phone result has been collected by this tool yet.**

The counter collector has eight integrity tests covering CPU guest accounting,
units, per-core accounting/hotplug, missing PSI, thermal names with spaces,
truncation, reboot and counter reset. Its actual shell script also completed two samples on the laptop
(`build/bench/host-telemetry-functional.json`). This is a host integration check,
not a phone benchmark.

The measurements use the documented
[requestAnimationFrame API](https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame)
and [CDP Runtime API](https://chromedevtools.github.io/devtools-protocol/tot/Runtime/).
