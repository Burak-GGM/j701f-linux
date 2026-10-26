#!/bin/sh
# Written by Claude 2026-10-10. Power actions for the recovery UI (roadmap R.7).
#   power.sh system | recovery | download | off
# With J701F_RECOVERY_DRYRUN=1 it only prints what it would do (computer tests,
# and the UI running as an ordinary program on the installed system).
act=$1
say() { echo "power: $*"; }
# Before the real thing: Wi-Fi off and the read-only mounts released, so that
# nothing is cut off in the middle. In the initramfs there is no init system to
# ask, so reboot and poweroff are forced (-f) there.
here=$(dirname "$0")
force=; [ -e /recovery/scripts ] && force=-f
quiet() {
    sh "$here/mtp.sh" down >/dev/null 2>&1
    sh "$here/wifi.sh" down >/dev/null 2>&1
    for m in /mnt/root /mnt/sd; do grep -q " $m " /proc/mounts && umount "$m" 2>/dev/null; done
    sync
}
run() { if [ "${J701F_RECOVERY_DRYRUN:-0}" = 1 ]; then say "would run: $*"; else quiet; "$@"; fi; }
case "$act" in
    system)   run reboot $force ;;
    # reboot-recovery is the project's helper that sets Samsung's reboot reason.
    recovery) if command -v reboot-recovery >/dev/null 2>&1; then run reboot-recovery --execute; else say "reboot-recovery helper not installed"; exit 1; fi ;;
    download) run reboot $force download ;;
    off)      run poweroff $force ;;
    *) say "unknown action '$act'"; exit 2 ;;
esac
