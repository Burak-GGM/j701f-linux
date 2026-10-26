#!/usr/bin/env python3
"""Written by Claude 2026-10-09. Convert a raw KWin ScreenShot2 capture
(QImage ARGB32_Premultiplied, i.e. BGRA bytes) from tools/kwin-screenshot.c to PNG.
Usage: raw-to-png.py IN.raw OUT.png [width height stride]"""
import struct, sys, zlib
src, dst = sys.argv[1], sys.argv[2]
w, h, stride = (int(v) for v in sys.argv[3:6]) if len(sys.argv) > 5 else (720, 1280, 2880)
raw = open(src, 'rb').read()
rows = bytearray()
for y in range(h):
    line = raw[y * stride:y * stride + w * 4]
    rgb = bytearray(w * 3)
    rgb[0::3] = line[2::4]; rgb[1::3] = line[1::4]; rgb[2::3] = line[0::4]
    rows += b'\0' + rgb
def chunk(tag, data):
    return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data))
open(dst, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                      + chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b''))
