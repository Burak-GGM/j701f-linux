#!/bin/sh
# Run from the USB root console or sudo over SSH. Original terminal resumes on exit.
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[ "$(id -u)" = 0 ] || { printf 'Use sudo to run the framebuffer trial.\n' >&2; exit 1; }
[ "$(cat /etc/j701f-system-version)" = BURAK_ALPINE_0_1 ]
case "${1:-180}" in ''|*[!0-9]*) exit 1;; esac
seconds=${1:-180}
[ "$seconds" -le 3600 ]
app=/home/burak-alpine/j701f-gui/j701f-gui
[ -x "$app" ]
umask 077
mkdir -p /run/j701f-gui
paused=''
child=''
resume() {
    if [ -n "$child" ]; then kill "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi
    for pid in $paused; do kill -CONT "$pid" 2>/dev/null || true; done
    printf 'J701F_GUI_ORIGINAL_TERMINAL_RESUMED\n'
}
trap resume EXIT
trap 'exit 0' INT TERM HUP
for proc in /proc/[0-9]*/exe; do
    executable=$(readlink "$proc" 2>/dev/null) || continue
    case "$executable" in /bin/ondevice-terminal|/bin/fb-heartbeat) ;; *) continue;; esac
    path=${proc%/exe}; pid=${path##*/}
    if kill -STOP "$pid"; then paused="$paused $pid"; fi
done
printf 'Paused framebuffer processes:%s\n' "$paused"
export XDG_RUNTIME_DIR=/run/j701f-gui
export TERM=xterm-256color
"$app" --seconds "$seconds" --screenshot > /run/j701f-gui/gui.log 2>&1 &
child=$!
printf '%s\n' "$child" > /run/j701f-gui/gui.pid
result=0
wait "$child" || result=$?
child=''
rm -f /run/j701f-gui/gui.pid
cat /run/j701f-gui/gui.log
exit "$result"
