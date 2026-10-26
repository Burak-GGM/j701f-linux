#!/usr/bin/env python3
"""Written by Claude 2026-10-09. Inject one key press+release into an evdev
device by name (root, on the phone), to check what the Plasma session does with
a key code when nobody can press the physical key.
Usage: inject-key.py "<device name>" <keycode-number>"""
import glob, os, struct, sys, time
name, code = sys.argv[1], int(sys.argv[2])
dev = None
for d in glob.glob('/sys/class/input/event*'):
    if open(d + '/device/name').read().strip() == name:
        dev = '/dev/input/' + os.path.basename(d)
if not dev:
    sys.exit('no input device named ' + name)
fd = os.open(dev, os.O_WRONLY)
def emit(t, c, v):
    now = time.time()
    os.write(fd, struct.pack('llHHi', int(now), int(now % 1 * 1e6), t, c, v))
for value in (1, 0):
    emit(1, code, value); emit(0, 0, 0); time.sleep(0.08)
print(dev, 'key', code, 'sent')
