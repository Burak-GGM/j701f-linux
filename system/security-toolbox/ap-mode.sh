#!/bin/sh
# Local, time-limited Wi-Fi AP for the phone owner. Never runs at boot.
set -eu
D=/run/j701f-lab-ap
mode=${1:-status}
[ "$(id -u)" = 0 ] || { echo 'root required' >&2; exit 1; }
connected_uuid() {
    nmcli -t -f UUID,DEVICE connection show --active | awk -F: '$2=="wlan0" {print $1; exit}'
}
restore() {
    [ -r "$D/return-uuid" ] || { echo 'No AP session to restore' >&2; return 0; }
    uuid=$(cat "$D/return-uuid")
    nmcli connection up uuid "$uuid" >/dev/null
    rm -rf "$D"
    echo 'Restored saved Wi-Fi connection.'
}
start_guard() {
    token=$(cat /proc/sys/kernel/random/uuid)
    printf '%s\n' "$token" > "$D/token"
    ttl=${J701F_AP_TTL_SECONDS:-600}
    case "$ttl" in *[!0-9]*|"") echo "invalid AP TTL" >&2; exit 2;; esac
    [ "$ttl" -ge 30 ] && [ "$ttl" -le 600 ] || { echo "AP TTL outside 30..600 seconds" >&2; exit 2; }
    nohup sh "$(dirname "$0")/ap-restore.sh" "$token" "$ttl" </dev/null >/run/j701f-lab-ap-restore.log 2>&1 &
}
case "$mode" in
    status)
        if [ -r "$D/return-uuid" ]; then
            printf 'Lab AP active or restoring. SSID: J701F-Lab\nPassword: '
            cat "$D/password"
        else
            echo 'Lab AP inactive.'
        fi ;;
    start)
        [ -e /etc/j701f-lab-ap-experimental ] || {
            echo 'AP disabled after failed automatic Wi-Fi restoration; requires a supervised repair trial' >&2
            exit 1
        }
        [ ! -e "$D/return-uuid" ] || { echo 'Lab AP already active; use extend or stop' >&2; exit 1; }
        uuid=$(connected_uuid)
        [ -n "$uuid" ] || { echo 'No connected home Wi-Fi profile to restore' >&2; exit 1; }
        mkdir -m 700 "$D"
        printf '%s\n' "$uuid" > "$D/return-uuid"
        password=$(od -An -tx1 -N12 /dev/urandom | tr -d ' \n')
        printf '%s\n' "$password" > "$D/password"
        chmod 600 "$D"/*
        # Arm rollback before switching wlan0 away from the management LAN.
        start_guard
        if ! nmcli device wifi hotspot ifname wlan0 ssid J701F-Lab band bg password "$password"; then
            restore
            exit 1
        fi
        printf 'SSID: J701F-Lab\nPassword: %s\nReturns to home Wi-Fi after 10 minutes.\n' "$password" ;;
    extend)
        [ -r "$D/return-uuid" ] || { echo 'Lab AP is not active' >&2; exit 1; }
        start_guard
        echo 'AP time limit extended by 10 minutes.' ;;
    stop) restore ;;
    *) echo 'unknown AP action' >&2; exit 2 ;;
esac
