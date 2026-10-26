#!/usr/bin/env python3
# Written by Claude 2026-10-10. Turns a raw frame captured by
# tools/kmod/j701f_cam_frame.c into a picture, on the computer.
# The receiver's DMA writes 10-bit Bayer samples packed as two 12-bit values in
# three bytes, little-endian, 3120 bytes per line for the 2072x1552 mode.
#   raw12-to-png.py FRAME.raw OUT.png [pattern [WIDTH HEIGHT]]   pattern: GRBG (default), RGGB, BGGR, GBRG
# Default size is the rear sensor's 2072x1552 mode; the line length is 1.5 bytes per
# pixel rounded up to a multiple of 16 pixels.
import sys
import numpy as np
from PIL import Image
W, H = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (2072, 1552)
LINE = (W + 15) // 16 * 16 * 3 // 2
d = np.fromfile(sys.argv[1], dtype=np.uint8)[:LINE * H].reshape(H, LINE)
a, b, c = (d[:, i::3].astype(np.uint16) for i in range(3))
img = np.empty((H, 2 * a.shape[1]), dtype=np.uint16)
img[:, 0::2] = a | ((b & 0x0f) << 8)
img[:, 1::2] = (b >> 4) | (c << 4)
img = img[:, :W].astype(np.float32)
print('raw: min %d max %d mean %.1f' % (img.min(), img.max(), img.mean()))
pattern = sys.argv[3] if len(sys.argv) > 3 else 'GRBG'
planes = {pattern[0]: [], pattern[1]: [], pattern[2]: [], pattern[3]: []}
for i, ch in enumerate(pattern):
    planes[ch].append(img[i // 2::2, i % 2::2])
rgb = np.stack([planes['R'][0], sum(planes['G']) / 2, planes['B'][0]], axis=-1)   # half resolution
rgb = np.clip(rgb - 64, 0, None)                         # black level
for ch in range(3):                                      # grey-world white balance
    m = rgb[..., ch].mean()
    if m > 0:
        rgb[..., ch] *= rgb[..., 1].mean() / m
hi = np.percentile(rgb, 99.5) or 1.0
out = (np.clip(rgb / hi, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
Image.fromarray(out).save(sys.argv[2])
