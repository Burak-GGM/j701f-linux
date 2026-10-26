#!/usr/bin/env python3
"""Written by Claude 2026-10-09. Inject a single-finger swipe into an evdev
touchscreen by writing input events to its node (root). Used to test Plasma
Mobile gestures on the phone without physical access.
Usage: inject-swipe.py /dev/input/event0 X0 Y0 X1 Y1 [steps] [hold_seconds]"""
import os, struct, sys, time
dev, x0, y0, x1, y1 = sys.argv[1], *map(int, sys.argv[2:6])
steps = int(sys.argv[6]) if len(sys.argv) > 6 else 30
hold = float(sys.argv[7]) if len(sys.argv) > 7 else 0.0
EV_SYN, EV_KEY, EV_ABS = 0, 1, 3
SLOT, TOUCH_MAJOR, POS_X, POS_Y, TRACKING, PRESSURE, BTN_TOUCH = 0x2f, 0x30, 0x35, 0x36, 0x39, 0x3a, 0x14a
fd = os.open(dev, os.O_WRONLY)
def emit(*events):
    now = time.time(); sec, usec = int(now), int((now % 1) * 1e6)
    os.write(fd, b''.join(struct.pack('llHHi', sec, usec, t, c, v) for t, c, v in events)
             + struct.pack('llHHi', sec, usec, EV_SYN, 0, 0))
emit((EV_ABS, SLOT, 0), (EV_ABS, TRACKING, 4242), (EV_ABS, POS_X, x0), (EV_ABS, POS_Y, y0),
     (EV_ABS, PRESSURE, 60), (EV_ABS, TOUCH_MAJOR, 8), (EV_KEY, BTN_TOUCH, 1))
for i in range(1, steps + 1):
    time.sleep(0.012)
    emit((EV_ABS, SLOT, 0), (EV_ABS, POS_X, x0 + (x1 - x0) * i // steps), (EV_ABS, POS_Y, y0 + (y1 - y0) * i // steps))
time.sleep(hold)
emit((EV_ABS, SLOT, 0), (EV_ABS, TRACKING, -1), (EV_KEY, BTN_TOUCH, 0))
