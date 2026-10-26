#!/bin/sh
# Written by Claude 2026-10-13. On the phone: ~/j701f/boot-swap/reboot-recovery.sh
# Restarts the phone into the recovery, leaving the filesystems clean.
#
# The helper "reboot-recovery" only syncs and calls reboot(RESTART2,
# "recovery"): services are not stopped and the root filesystem stays mounted
# read-write, so every trip to the recovery was an unclean shutdown (journal
# replay, start-up guard stamps left behind). This wrapper removes the stamps
# (what system/stamps-stop does at a normal shutdown), stops the desktop, has
# the kernel remount everything read-only (SysRq u) and only then restarts.
[ "$(id -u)" = 0 ] || exec sudo -n "$0" "$@"
[ "$1" = --execute ] || { echo "PLAN: clean restart into the recovery; use --execute"; exit 0; }
H=${0%/*}
rm -f /var/lib/j701f-*.pending
rc-service -q sddm stop >/dev/null 2>&1
sync
echo 1 > /proc/sys/kernel/sysrq
echo u > /proc/sysrq-trigger
sleep 2
exec "$H/reboot-recovery" --execute
