#!/bin/sh
# One-shot native display experiment. Must be a child of the watchdog
# supervisor; BOOT, RECOVERY and runlevel/autostart configuration stay intact.
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[ "${J701F_DISPLAY_TRIAL_ARMED:-}" = 1 ]
[ "${J701F_DISPLAY_SUPERVISOR_PID:-}" = "$PPID" ]
kill -0 "$PPID"
cd "$(dirname "$0")"
exec > trial.log 2>&1
echo NATIVE_TRIAL_STARTED
date -u
uname -a
sha256sum -c hashes.sha256
if [ -f ./native-display-gui.py ]; then
    python3 ./native-display-gui.py baseline
fi
# BusyBox dmesg has no -w here. Read the kernel log device directly to preserve
# progress if a probe blocks before the final snapshot; also collect pstore.
cat /dev/kmsg > dmesg-follow.txt 2>&1 &
# Capture and validate only the local SDDM Wayland scope, before PAM removes
# its loginctl entry. SSH and the watchdog supervisor must remain outside it.
kwin=$(pidof kwin_wayland)
case "$kwin" in ''|*[!0-9]*) echo 'Expected one KWin process'; exit 1;; esac
scope=$(sed -n 's/^0:://p' "/proc/$kwin/cgroup")
printf '%s\n' "$scope" | grep -Eq '^/c[0-9]+$'
session=${scope#/}
[ "$(loginctl show-session "$session" -p Type --value)" = wayland ]
service=$(loginctl show-session "$session" -p Service --value)
case "$service" in sddm|sddm-autologin) ;; *) exit 1;; esac
gui_scope=/sys/fs/cgroup$scope
[ -f "$gui_scope/cgroup.kill" ]
if grep -qx "$$" "$gui_scope/cgroup.procs" ||
   grep -qx "$J701F_DISPLAY_SUPERVISOR_PID" "$gui_scope/cgroup.procs"; then
    echo 'Trial/supervisor unexpectedly belongs to graphical scope'; exit 1
fi
timeout -s KILL 15 rc-service sddm stop
# OpenRC reports this phone's SDDM stopped even though its supervise-daemon and
# session run. Stop that exact supervisor to prevent automatic relogin.
if pidof sddm >/dev/null 2>&1; then
    echo SDDM_RUNTIME_SUPERVISOR_STOP
    timeout -s KILL 15 env RC_SVCNAME=sddm supervise-daemon sddm --stop --retry TERM/8/KILL/2
fi
sleep 2
# elogind closes the PAM session without killing every child on this system.
# Kill only the already verified graphical cgroup if its compositor survives.
if pidof kwin_wayland plasmashell >/dev/null 2>&1 && [ -f "$gui_scope/cgroup.kill" ]; then
    echo "SDDM_REMAINING_SCOPE_STOP $session"
    printf '1' > "$gui_scope/cgroup.kill"
fi
count=0
while pidof sddm kwin_wayland plasmashell >/dev/null 2>&1 && [ "$count" -lt 10 ]; do
    sleep 1
    count=$((count+1))
done
if pidof sddm kwin_wayland plasmashell >/dev/null 2>&1; then
    echo 'Graphical session still running; refuse takeover'
    exit 1
fi
# Determine the firmware device from the DRM parent, not an assumed card index.
firmware=
for card in /sys/class/drm/card[0-9]*; do
    [ -L "$card/device/driver" ] || continue
    driver=$(basename "$(readlink -f "$card/device/driver")")
    [ "$driver" = simple-framebuffer ] || continue
    [ -z "$firmware" ] || { echo 'Multiple firmware devices'; exit 1; }
    firmware=$(basename "$(readlink -f "$card/device")")
done
[ -n "$firmware" ]
echo "FIRMWARE_DRM_UNBIND $firmware"
printf '%s' "$firmware" > /sys/bus/platform/drivers/simple-framebuffer/unbind
echo Y > /sys/module/samsung_dsim/parameters/j701f_vendor_timing
insmod ./panel-j701f-ea8061s.ko allow_init=1
insmod ./j701f-display-overlay.ko allow_apply=1
dmesg > dmesg-after-overlay.txt
[ "$(cat /sys/module/j701f_display_overlay/parameters/result)" = 0 ]
# The virtual DRM master initially had no native components. Reprobe only
# after both controllers have been created by the OF reconfiguration notifier.
sleep 1
if [ ! -L /sys/bus/platform/devices/exynos-drm/driver ]; then
    printf '%s' exynos-drm > /sys/bus/platform/drivers/exynos-drm/bind
fi
sleep 1
native=
for card in /sys/class/drm/card[0-9]*; do
    [ -L "$card/device/driver" ] || continue
    driver=$(basename "$(readlink -f "$card/device/driver")")
    [ "$driver" = exynos-drm ] || continue
    native=/dev/dri/$(basename "$card")
done
[ -n "$native" ]
echo "NATIVE_DRM $native"
timeout -s KILL 20 ./native-display-kms "$native" > kms.log 2>&1 &
kms=$!
count=0
while ! grep -q NATIVE_PANEL_HOLD_FOR_DCS_READ kms.log; do
    kill -0 "$kms" || { cat kms.log; exit 1; }
    [ "$count" -lt 12 ] || { cat kms.log; exit 1; }
    sleep 1
    count=$((count+1))
done
insmod ./j701f-panel-status.ko allow_read=1
cat /sys/module/j701f_panel_status/parameters/result
cat /sys/module/j701f_panel_status/parameters/power_mode
insmod ./j701f-display-info.ko
dmesg > dmesg.txt
cat kms.log
wait "$kms"
if [ -x ./native-display-prime ]; then
    # The host stages this optional probe only with --prime-probe. It allocates
    # one linear GPU buffer, imports it and creates an FB object without modeset.
    render=
    for node in /sys/class/drm/renderD*; do
        [ -L "$node/device/driver" ] || continue
        [ "$(basename "$(readlink -f "$node/device/driver")")" = panfrost ] || continue
        [ -z "$render" ] || { echo 'Multiple Panfrost render nodes'; exit 1; }
        render=/dev/dri/$(basename "$node")
    done
    [ -n "$render" ]
    if timeout -s KILL 10 ./native-display-prime "$render" "$native" render > prime.log 2>&1; then
        echo NATIVE_PRIME_PROBE_EXIT=0
    else
        echo "NATIVE_PRIME_PROBE_EXIT=$?"
    fi
    cat prime.log
    if timeout -s KILL 10 ./native-display-prime "$render" "$native" display > prime-display.log 2>&1; then
        echo NATIVE_DISPLAY_GBM_PROBE_EXIT=0
    else
        echo "NATIVE_DISPLAY_GBM_PROBE_EXIT=$?"
    fi
    cat prime-display.log
    if [ -x ./native-display-egl ]; then
        if timeout -s KILL 10 ./native-display-egl render "$render" > egl-render.log 2>&1; then
            echo NATIVE_RENDER_EGL_EXIT=0
        else
            echo "NATIVE_RENDER_EGL_EXIT=$?"
        fi
        if timeout -s KILL 10 ./native-display-egl display "$native" > egl-display.log 2>&1; then
            echo NATIVE_DISPLAY_EGL_EXIT=0
        else
            echo "NATIVE_DISPLAY_EGL_EXIT=$?"
        fi
        cat egl-render.log egl-display.log
    fi
    if [ -x ./native-display-dmabuf ]; then
        if timeout -s KILL 15 ./native-display-dmabuf "$render" "$native" > shared-render.log 2>&1; then
            echo NATIVE_SHARED_RENDER_EXIT=0
        else
            echo "NATIVE_SHARED_RENDER_EXIT=$?"
        fi
        cat shared-render.log
    fi
    dmesg > dmesg.txt
fi
if [ -f ./native-display-gui.py ]; then
    python3 ./native-display-gui.py native
    dmesg > dmesg.txt
fi
echo 'NATIVE_TRIAL_FINISHED; supervisor always resets to original BOOT'
