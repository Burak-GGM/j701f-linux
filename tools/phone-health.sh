#!/bin/bash
# Written by Claude 2026-10-13. A read-only health check of the running phone:
# the things that have silently gone wrong at least once in this project, each
# as one line. Changes nothing on the phone. Exit status 1 when something FAILs.
#
#   tools/phone-health.sh            (J701F_PHONE_IP overrides the address)
#   tools/phone-health.sh --usb      the same checks over the USB serial shell,
#                                    for a phone without network or SSH key
set -uo pipefail
cd "$(dirname "$0")/.."
H=burak-alpine@${J701F_PHONE_IP:-$(cat .phone-ip 2>/dev/null || echo j701f.local)}
O=(-o BatchMode=yes -o ConnectTimeout=6)
[ -f build/phone-ssh-known-hosts ] && O+=(-o StrictHostKeyChecking=yes -o UserKnownHostsFile=build/phone-ssh-known-hosts)
WANT_ID=$(python3 -c "import json;print(json.load(open('build/kernel/boot-slot.json')).get('kernel_build_id',''))" 2>/dev/null || true)

if [ "${1:-}" = --usb ]; then
    # The phone-side part below, run through tools/usb-run.py instead of SSH.
    tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
    sed -n "/^ssh .*<<'REMOTE'$/,/^REMOTE$/p" "$0" | sed '1d;$d' > "$tmp"
    python3 tools/usb-run.py "$tmp" WANT_ID="$WANT_ID"
    exit $?
fi
ssh "${O[@]}" "$H" WANT_ID="$WANT_ID" sh -s <<'REMOTE'
fail=0
ok()   { echo "ok    $*"; }
warn() { echo "WARN  $*"; }
bad()  { echo "FAIL  $*"; fail=1; }
up=$(cut -d. -f1 /proc/uptime)

if awk '$2=="/"{exit substr($4,1,2)!="rw"}' /proc/mounts; then ok "installed system, up ${up} s, $(uname -r)"
else bad "root is read-only: this is the recovery, not the installed system"; fi

id=$(sudo -n sh -c 'cat /sys/kernel/notes' 2>/dev/null | od -An -tx1 | tr -d ' \n' | grep -o '474e5500[0-9a-f]\{40\}' | head -1 | cut -c9-)
if [ -z "$WANT_ID" ]; then ok "kernel build ID $id"
elif [ "$id" = "$WANT_ID" ]; then ok "kernel build ID as recorded"
else warn "kernel build ID $id, the record says $WANT_ID"; fi

drv=
for c in /sys/class/drm/card[0-9]; do
    [ -L "$c/device/driver" ] && d=$(basename "$(readlink -f "$c/device/driver")") || continue
    case "$d" in exynos-drm|simple-framebuffer) drv=$d ;; esac
done
case "$drv" in
    exynos-drm) ok "display: native driver" ;;
    simple-framebuffer) if [ "$(head -1 /etc/j701f-display-native 2>/dev/null)" = always ]; then warn "display: firmware framebuffer although the native driver is enabled ($(tail -1 /run/j701f-display.log 2>/dev/null))"; else ok "display: firmware framebuffer (native not enabled)"; fi ;;
    *) bad "display: no known display driver bound" ;;
esac
pidof kwin_wayland >/dev/null && pidof plasmashell >/dev/null && ok "desktop running" || bad "desktop not running (kwin_wayland / plasmashell)"

st=$(ls /var/lib 2>/dev/null | grep '^j701f-.*\.pending$' | tr '\n' ' ')
if [ -z "$st" ]; then ok "no start-up guard stamps"
elif [ "$up" -lt 200 ]; then ok "guard stamps still armed, normal this early: $st"
else warn "guard stamps left behind: $st"; fi

g=$(cat /sys/class/devfreq/*gpu*/max_freq 2>/dev/null | head -1); c=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq 2>/dev/null)
if [ "$g" = 1001000000 ] && [ "$c" = 1586000 ]; then ok "frequency limits: GPU 1001 MHz, CPU 1586 MHz"
elif [ "$up" -lt 200 ]; then ok "frequency limits not raised yet (GPU $g, CPU $c), normal this early"
else warn "frequency limits: GPU $g Hz, CPU $c kHz (expected 1001 MHz / 1586 MHz)"; fi

for m in j701f_s2mu005_charger j701f_adc j701f_camera udmabuf s5p_mfc; do
    grep -q "^$m " /proc/modules || warn "module $m not loaded"
done
grep -q '^j701f_s2mu005_charger ' /proc/modules && ok "modules: $(wc -l < /proc/modules) loaded"

FG=/sys/class/power_supply/s2mu005-fuel-gauge; CH=/sys/class/power_supply/s2mu005-charger
if [ -r $FG/capacity ]; then
    cap=$(cat $FG/capacity); mv=$(( $(cat $FG/voltage_avg) / 1000 )); ma=$(( $(cat $FG/current_avg) / 1000 ))
    line="battery $cap %, $mv mV, $ma mA, charger $(cat $CH/status 2>/dev/null), cable $(sed -n 's/.*\[\(.*\)\].*/\1/p' $CH/usb_type 2>/dev/null), limits $(( $(cat $CH/input_current_limit) / 1000 ))/$(( $(cat $CH/constant_charge_current) / 1000 )) mA"
    # a resting or gently charging cell above 4.25 V is nearly full; below 3.6 V nearly empty
    if [ "$mv" -gt 4250 ] && [ "$ma" -lt 500 ] && [ "$cap" -lt 85 ]; then warn "$line - percentage too low for this voltage: gauge has drifted"
    elif [ "$mv" -lt 3600 ] && [ "$ma" -gt -500 ] && [ "$cap" -gt 25 ]; then warn "$line - percentage too high for this voltage: gauge has drifted"
    else ok "$line"; fi
else bad "no fuel gauge"; fi
pgrep -f 'j701f-batter[y]' >/dev/null && ok "battery helper running" || warn "battery helper not running (gauge mode and temperature limits are not looked after)"
t=
for h in /sys/class/hwmon/hwmon*; do [ "$(cat $h/name 2>/dev/null)" = j701f_adc ] && t=$(cat $h/temp1_input 2>/dev/null); done
if [ -z "$t" ]; then warn "battery temperature not readable"
elif [ "$t" -gt 45000 ] || [ "$t" -lt 5000 ]; then warn "battery temperature $(( t / 1000 )) degC"
else ok "battery temperature $(( t / 1000 )) degC"; fi

if command -v fbcli >/dev/null 2>&1; then
    P=$(pidof plasmashell | cut -d' ' -f1)
    prof=$(env $(tr '\0' '\n' < /proc/$P/environ 2>/dev/null | grep -E '^(DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR)=') gsettings get org.sigxcpu.feedbackd profile 2>/dev/null)
    # in its default profile "full" the vibration service also plays sounds for the same events
    [ "$prof" = "'quiet'" ] && ok "vibration service: profile quiet (vibration only)" || warn "vibration service profile is ${prof:-unknown}, expected 'quiet' (in 'full' it also plays sounds)"
else warn "vibration service (feedbackd) not installed: the desktop cannot vibrate"; fi

y=$(date +%Y); [ "$y" -ge 2026 ] && ok "clock $(date '+%F %T %Z')" || warn "clock is wrong: $(date)"
[ -e /etc/localtime ] || warn "no time zone set (UTC shown)"
ry=$(cat /sys/class/rtc/rtc0/date 2>/dev/null | cut -d- -f1); [ "${ry:-0}" -ge 2026 ] || warn "hardware clock says year ${ry:-?}: the next boot starts with a wrong date until Wi-Fi is up"

if [ -b /dev/mmcblk2p1 ]; then
    mountpoint -q /media/sdcard && ok "SD card mounted at /media/sdcard" || warn "SD card present but not mounted"
else ok "no SD card in the slot"; fi
pidof umtprd >/dev/null && ok "MTP server running" || warn "MTP server not running"
ip -4 addr show dev wlan0 2>/dev/null | grep -q 'inet ' && ok "Wi-Fi: $(iw dev wlan0 link 2>/dev/null | sed -n 's/.*signal: //p')" || warn "Wi-Fi has no address"

n=$(dmesg | grep -c -E 'Unable to handle kernel|Internal error: Oops|Kernel panic|BUG:|WARNING: CPU')
[ "$n" = 0 ] && ok "kernel log: no oops or warning" || bad "kernel log: $n oops/warning line(s)"
awk '/MemAvailable/{a=$2} /SwapFree/{s=$2} END{printf "%s    memory: %d MB available, %d MB swap free\n", (a<150000)?"WARN":"ok", a/1024, s/1024}' /proc/meminfo
df -P / | awk 'NR==2{u=$5+0; printf "%s    root filesystem %s used, %d MB free\n", (u>=90)?"WARN":"ok", $5, $4/1024}'
exit $fail
REMOTE
