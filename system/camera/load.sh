#!/bin/sh
# Written by Claude 2026-10-10. Installed as ~/j701f/modules/camera/load.sh and
# run at boot by /etc/local.d/j701f-audio.start (behind its reset guard, like
# the audio and video-decoder modules). Loads the camera driver and what it
# needs: two V4L2 helper modules of the kernel build, the project's
# j701f_camera.ko, and udmabuf.ko (libcamera's software image processing needs
# a dma-buf provider; the kernel in BOOT has none built in).
cd "$(dirname "$0")" || exit 1
# Claude 2026-10-28: enables the rear focus motor's I2C bus (optional; without
# it the lens is simply not moved).
[ -f j701f_camaf.ko ] && insmod j701f_camaf.ko 2>/dev/null
for m in videobuf2-vmalloc v4l2-async v4l2-fwnode udmabuf j701f_camera; do
    insmod "$m.ko" 2>/dev/null || grep -q "^$(echo "$m" | tr - _) " /proc/modules || { echo "insmod $m failed"; exit 1; }
done
ls -l /dev/media0 /dev/media1 2>/dev/null
