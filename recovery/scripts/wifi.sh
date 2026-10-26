#!/bin/sh
# Written by Claude 2026-10-10. Wi-Fi and SSH for the recovery (owner's wish of
# 2026-10-10). The driver and its firmware are in the recovery itself; the
# programs (wpa_supplicant, udhcpc, sshd), the saved network and the SSH host
# keys are borrowed from the installed system, which is mounted read-only.
# So this only works while that system's files are readable; the USB shell is
# the path that never depends on them.
#
#   wifi.sh up | down | status
#
# An SSH login lands inside the installed system's files (read-only), with the
# recovery's kernel, /dev, /proc and /sys.
set -u
here=$(dirname "$0")
R=/mnt/root
say() { echo "wifi: $*"; }
die() { say "REFUSED: $*"; exit 1; }
mounted() { grep -q " $1 " /proc/mounts; }
addr() { ip -4 addr show dev wlan0 2>/dev/null | sed -n 's/.*inet \([0-9.]*\).*/\1/p' | head -1; }

down() {
    for f in "$R/run/sshd-recovery.pid" "$R/run/wpa-recovery.pid"; do
        [ -r "$f" ] && kill "$(cat "$f")" 2>/dev/null
    done
    # sessions and anything else still running from the installed system's files
    for p in /proc/[0-9]*; do
        [ "$(readlink "$p/root" 2>/dev/null)" = "$R" ] && kill "${p#/proc/}" 2>/dev/null
    done
    sleep 1
    for p in /proc/[0-9]*; do
        [ "$(readlink "$p/root" 2>/dev/null)" = "$R" ] && kill -9 "${p#/proc/}" 2>/dev/null
    done
    ip link set wlan0 down 2>/dev/null
    for m in "$R/run/recovery" "$R/run/recovery-state" "$R/dev/pts" "$R/dev" "$R/proc" "$R/sys" "$R/tmp" "$R/run"; do
        mounted "$m" && umount "$m" 2>/dev/null
    done
}

case "${1:-}" in
up)
    [ -d /sys/class/net/wlan0 ] || die "no wlan0 (driver or firmware did not start)"
    [ -n "$(addr)" ] && { say "UP already, address $(addr)"; exit 0; }
    sh "$here/storage.sh" mount-root >/dev/null || die "the installed system cannot be mounted"
    [ -x "$R/sbin/wpa_supplicant" ] && [ -r "$R/etc/wpa_supplicant/wlan0.conf" ] || die "no wpa_supplicant or no saved network"
    mounted "$R/run" || mount -t tmpfs -o mode=755 tmpfs "$R/run" || die "tmpfs on $R/run"
    # wpa_cli makes its reply socket in /tmp (found in the second trial)
    mounted "$R/tmp" || mount -t tmpfs -o mode=1777 tmpfs "$R/tmp" || die "tmpfs on $R/tmp"
    mounted "$R/dev" || mount -o bind /dev "$R/dev" || die "bind /dev"
    mounted "$R/dev/pts" || mount -t devpts devpts "$R/dev/pts" 2>/dev/null
    mounted "$R/proc" || mount -t proc proc "$R/proc" || die "proc"
    mounted "$R/sys" || mount -t sysfs sysfs "$R/sys" || die "sysfs"
    # the recovery's own scripts and state, for whoever logs in over SSH:
    # /run/recovery/scripts/flash-boot.sh etc., state in /run/recovery-state
    mkdir -p "$R/run/recovery" "$R/run/recovery-state"
    mount -o bind /recovery "$R/run/recovery" 2>/dev/null
    mount -o bind /run/recovery-state "$R/run/recovery-state" 2>/dev/null
    ip link set lo up; ip link set wlan0 up || { down; die "wlan0 does not come up"; }
    chroot "$R" /sbin/wpa_supplicant -B -D nl80211 -i wlan0 -c /etc/wpa_supplicant/wlan0.conf \
        -P /run/wpa-recovery.pid >/dev/null 2>&1 || { down; die "wpa_supplicant did not start"; }
    n=0
    until chroot "$R" /sbin/wpa_cli -i wlan0 status 2>/dev/null | grep -qx 'wpa_state=COMPLETED'; do
        n=$((n + 1)); [ $n -gt 20 ] && { down; die "not associated after 40 s"; }
        sleep 2
    done
    # the hook also tries to write /etc/resolv.conf and fails on the read-only
    # system; the address and route are set before that
    chroot "$R" /sbin/udhcpc -i wlan0 -n -q -t 5 -T 3 -s /sbin/j701f-wifi-dhcp >/dev/null 2>&1
    [ -n "$(addr)" ] || { down; die "no address from DHCP"; }
    ssh=off
    [ -x "$R/usr/sbin/sshd" ] && chroot "$R" /usr/sbin/sshd -o PidFile=/run/sshd-recovery.pid 2>/dev/null && ssh=on
    say "UP address $(addr), SSH $ssh"
    ;;
down) down; say "DOWN" ;;
status)
    if [ -n "$(addr)" ]; then say "UP address $(addr)"; else say "DOWN"; fi ;;
*) echo "usage: wifi.sh up | down | status" >&2; exit 2 ;;
esac
