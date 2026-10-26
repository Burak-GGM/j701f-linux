#!/bin/sh
# Written by Claude 2026-10-10 (roadmap 2, B.2). Installed on the phone as
# /usr/local/sbin/j701f-display-switch with the owner's permission of 2026-10-10.
#
# Switches the running system from the firmware framebuffer (simpledrm) to the
# native display driver (DECON + DSIM + EA8061S panel) before the display
# manager starts. The steps are those of Codex's tools/native-display-trial.sh,
# which passed on this kernel; nothing in BOOT changes - the device-tree
# overlay lives in RAM.
#
# /etc/j701f-display-native holds "once" (this boot only; the file is removed
# first) or "always". Ways back to the firmware framebuffer:
#   - hold Volume Down while the phone boots;
#   - a reset before the session has been up for 150 s leaves the stamp
#     /var/lib/j701f-display.pending behind, and the next boot skips the switch
#     (one boot; the one after tries again). A clean shutdown removes the stamp;
#   - remove /etc/j701f-display-native.
# Never fails the boot: every path ends in "exit 0" or a reboot.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
D=/home/burak-alpine/j701f/modules/display
FLAG=/etc/j701f-display-native
STAMP=/var/lib/j701f-display.pending
exec >> /run/j701f-display.log 2>&1
echo "== $(date -u) =="
[ -r "$FLAG" ] || { echo "not enabled"; exit 0; }
mode=$(head -1 "$FLAG")
case "$mode" in once) rm -f "$FLAG"; sync ;; always) ;; *) echo "unknown mode '$mode'"; exit 0 ;; esac
# One boot only: the stamp is removed here, so the boot after this one tries
# again. (First version kept it until removed by hand - and the very first
# reboot under "always", made less than 150 s after a native boot, left the
# phone on the firmware framebuffer for good. Same flaw as the GPU guard had.)
[ ! -e "$STAMP" ] || { rm -f "$STAMP"; sync; echo "stamp present: the last switch did not survive; firmware framebuffer for this boot only"; exit 0; }
[ "$(sha256sum < /sys/kernel/notes | cut -d' ' -f1)" = "$(cat "$D/kernel-notes.sha256" 2>/dev/null)" ] ||
    { echo "running kernel is not the one these modules were tried on"; exit 0; }
if python3 - <<'PY'
import fcntl, glob, sys
KEY_VOLUMEDOWN = 114
for dev in glob.glob('/dev/input/event*'):
    try:
        with open(dev, 'rb') as f:
            keys = bytearray(96)
            fcntl.ioctl(f, 0x80604518, keys)   # EVIOCGKEY(96): keys held right now
            if keys[KEY_VOLUMEDOWN // 8] >> (KEY_VOLUMEDOWN % 8) & 1:
                sys.exit(0)
    except OSError:
        pass
sys.exit(1)
PY
then echo "Volume Down held: staying on the firmware framebuffer"; exit 0; fi

firmware=
for card in /sys/class/drm/card[0-9]*; do
    [ -L "$card/device/driver" ] || continue
    [ "$(basename "$(readlink -f "$card/device/driver")")" = simple-framebuffer ] || continue
    firmware=$(basename "$(readlink -f "$card/device")")
done
[ -n "$firmware" ] || { echo "no firmware framebuffer device (already native?)"; exit 0; }

: > "$STAMP"; sync
takeover() {
    set -e
    printf '%s' "$firmware" > /sys/bus/platform/drivers/simple-framebuffer/unbind
    echo Y > /sys/module/samsung_dsim/parameters/j701f_vendor_timing
    insmod "$D/panel-j701f-ea8061s.ko" allow_init=1
    insmod "$D/j701f-display-overlay.ko" allow_apply=1
    [ "$(cat /sys/module/j701f_display_overlay/parameters/result)" = 0 ]
    sleep 1
    [ -L /sys/bus/platform/devices/exynos-drm/driver ] ||
        printf '%s' exynos-drm > /sys/bus/platform/drivers/exynos-drm/bind
    sleep 1
    for card in /sys/class/drm/card[0-9]*; do
        [ -L "$card/device/driver" ] || continue
        [ "$(basename "$(readlink -f "$card/device/driver")")" = exynos-drm ] && return 0
    done
    return 1
}
( takeover ) &
job=$!
n=0
while kill -0 "$job" 2>/dev/null; do
    n=$((n + 1))
    [ "$n" -le 40 ] || { echo "switch hung for 40 s: rebooting, stamp stays"; sync; reboot -f; }
    sleep 1
done
if wait "$job"; then
    echo "NATIVE display active (mode $mode)"
    # The stamp goes away only once a desktop has really been running on it.
    ( sleep 150
      if pidof kwin_wayland >/dev/null 2>&1; then rm -f "$STAMP"; sync
      else echo "no compositor after 150 s: rebooting, stamp stays" >> /run/j701f-display.log; sync; reboot; fi ) > /dev/null 2>&1 &
else
    echo "switch FAILED: rebooting, stamp stays"; sync; reboot -f
fi
exit 0
