# ~/.config/plasma-workspace/env/j701f-webengine.sh
# Written by Claude 2026-10-10. Chromium switches for every QtWebEngine program
# (Angelfish is the main browser) on a 1.6 GB, eight-A53 phone:
#  - low-end device mode: smaller caches and tiles, fewer speculative work items
#  - at most three renderer processes instead of one per tab/site
#  - four raster threads (default is two), rasterise on the GPU
export QTWEBENGINE_CHROMIUM_FLAGS="--enable-low-end-device-mode --renderer-process-limit=3 --num-raster-threads=4 --enable-gpu-rasterization"
