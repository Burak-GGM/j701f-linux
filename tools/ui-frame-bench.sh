#!/bin/sh
# Written by Claude 2026-10-10 (roadmap 2, D.4). Runs ON THE PHONE as root.
# Counts the frames the compositor really presented while a finger gesture is
# injected: KWin only presents when something changed, so presented frames per
# second during a gesture is the animation's frame rate. Silent.
#   usage: sudo sh ui-frame-bench.sh   (needs perf and ~/j701f/recovery-build/inject-swipe.py)
INJ=/home/burak-alpine/j701f/recovery-build/inject-swipe.py
T=/dev/input/event0
loginctl unlock-sessions
# Frame counter: the kernel here has no tracing, so the framebuffer attached to
# the primary plane is polled in the DRM debug state (about 400 times a second)
# and every change is one presented frame. Needs the native display driver.
cat > /tmp/ui-flips.py <<'PY'
import re, sys, time
secs = float(sys.argv[1]); path = sys.argv[2]
pat = re.compile(rb'fb=(\d+)')
last = None; flips = 0; start = time.time(); end = start + secs; bins = {}
with open(path, 'rb', buffering=0) as f:
    while time.time() < end:
        f.seek(0); m = pat.search(f.read(600))
        if m and m.group(1) != last:
            if last is not None:
                flips += 1; b = int((time.time() - start) * 10); bins[b] = bins.get(b, 0) + 1
            last = m.group(1)
# "moving": tenths of a second in which at least one frame was presented;
# full tenths have 6 frames at 60 Hz
moving = len(bins); full = sum(1 for v in bins.values() if v >= 5)
print(flips, moving, full)
PY
STATE=
for d in /sys/kernel/debug/dri/*/; do
    [ "$(cat "$d/name" 2>/dev/null | cut -d' ' -f1)" = exynos ] && STATE=$d/state
done
[ -n "$STATE" ] || { echo "native display driver not active: nothing to count"; exit 1; }
run() {  # label seconds x1 y1 x2 y2: swipe there and back until the time is up
    label=$1; secs=$2; shift 2
    python3 /tmp/ui-flips.py "$secs" "$STATE" > /tmp/ui-frames.txt &
    end=$(( $(date +%s) + secs ))
    while [ "$1" != "$3" -o "$2" != "$4" ] && [ "$(date +%s)" -lt "$end" ]; do
        python3 $INJ $T $1 $2 $3 $4 ${STEPS:-12} 0.35; sleep 0.45
        python3 $INJ $T $3 $4 $1 $2 ${STEPS:-12} 0.35; sleep 0.45
    done
    wait
    read n moving full < /tmp/ui-frames.txt
    [ "$moving" -gt 0 ] || moving=1
    echo "$label: $n frames; while moving: $((n * 10 / moving)) per second; $((full * 100 / moving)) % of the moving time at 50-60"
}
run "idle (no gesture)        " 4 0 0 0 0
run "top panel down and up    " 8 360 5 360 900
run "app drawer up and down   " 8 360 1000 360 300
run "home pages left and right" 8 600 600 120 600
