#!/bin/sh
# Written by Claude 2026-10-10 (roadmap 2, D.1). Runs ON THE PHONE inside the
# logged-in Plasma session's environment; silent (nothing is played).
# For each application: start it, wait until its process has used almost no
# CPU for one second ("settled"), print the time to that point, the CPU time
# it used and its memory (PSS), then close it. Two runs each: the first after
# dropping the file cache (cold), the second straight after (warm).
#   usage: sh app-start-bench.sh [command ...]
P=$(pidof plasmashell | cut -d' ' -f1)
export $(tr '\0' '\n' < /proc/$P/environ | grep -E '^(DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR|WAYLAND_DISPLAY|QT_QUICK_CONTROLS_STYLE|QT_QUICK_CONTROLS_MOBILE|QT_QPA_PLATFORMTHEME|XDG_CURRENT_DESKTOP|KDE_FULL_SESSION|KDE_SESSION_VERSION)=')
export QT_QPA_PLATFORM=wayland
kscreen-doctor --dpms on >/dev/null 2>&1; sudo -n loginctl unlock-sessions
cat > /tmp/app-settle.py <<'PY'
import os, subprocess, sys, time
t0 = time.time()
p = subprocess.Popen(sys.argv[1:], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
def family():
    pids, todo = [], [p.pid]
    while todo:
        pid = todo.pop(); pids.append(pid)
        try:
            for t in os.listdir('/proc/%d/task' % pid):
                todo += [int(c) for c in open('/proc/%d/task/%s/children' % (pid, t)).read().split()]
        except OSError: pass
    return pids
def cpu():
    total = 0
    for pid in family():
        try:
            f = open('/proc/%d/stat' % pid).read().rsplit(')', 1)[1].split(); total += int(f[11]) + int(f[12])
        except OSError: pass
    return total
def pss():
    kb = 0
    for pid in family():
        try:
            kb += sum(int(l.split()[1]) for l in open('/proc/%d/smaps_rollup' % pid) if l.startswith('Pss:'))
        except OSError: pass
    return kb // 1024
last, quiet = cpu(), 0
while time.time() - t0 < 40:
    time.sleep(0.25); c = cpu(); d = c - last; last = c
    quiet = quiet + 1 if d <= 2 else 0
    if quiet >= 4 and time.time() - t0 > 1.5: break
print('%5.1f s to settle  %5.1f s cpu  %4d MiB' % (time.time() - t0 - 1.0, last / 100.0, pss()))
try: os.killpg(p.pid, 15)
except OSError: pass
time.sleep(1.5)
try: os.killpg(p.pid, 9)
except OSError: pass
PY
[ $# -gt 0 ] || set -- angelfish plasma-settings kalk kclock gnome-software audiotube koko kweather kasts marknote pure-maps
for app in "$@"; do
    command -v "$app" >/dev/null 2>&1 || { echo "$app: not installed"; continue; }
    for run in cold warm; do
        [ $run = cold ] && { sync; echo 3 | sudo -n tee /proc/sys/vm/drop_caches >/dev/null; sleep 1; }
        qdbus6 org.freedesktop.ScreenSaver /ScreenSaver org.freedesktop.ScreenSaver.SimulateUserActivity >/dev/null 2>&1
        printf '%-16s %-4s %s\n' "$app" "$run" "$(python3 /tmp/app-settle.py "$app")"
        sleep 2
    done
done
