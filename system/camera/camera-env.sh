# Written by Claude 2026-10-10. Installed as ~/.config/plasma-workspace/env/j701f-camera.sh.
# libcamera's software image processing can run on the GPU or on the CPU. On
# this phone the GPU path tries to hand its buffers to the display driver,
# which refuses them ("buffer chunks must be mapped contiguously"), and the
# camera test program aborted in about every third start. The CPU path was
# stable in every run.
export LIBCAMERA_SOFTISP_MODE=cpu
