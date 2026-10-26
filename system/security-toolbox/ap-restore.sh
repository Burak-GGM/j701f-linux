#!/bin/sh
# Separate watchdog survives loss of the Wi-Fi SSH path.
set -eu
token=${1:?token required}
sleep "${2:?ttl required}"
D=/run/j701f-lab-ap
[ -r "$D/token" ] || exit 0
[ "$(cat "$D/token")" = "$token" ] || exit 0
[ -r "$D/return-uuid" ] || exit 0
uuid=$(cat "$D/return-uuid")
n=0
while [ "$n" -lt 18 ]; do
    nmcli connection down Hotspot >/dev/null 2>&1 || true
    if nmcli connection up uuid "$uuid"; then
        rm -rf "$D"
        exit 0
    fi
    n=$((n + 1))
    sleep 10
done
echo 'Home Wi-Fi restoration failed after 18 retries; rebooting known-good BOOT' >&2
# This is the last independent route back to the saved Wi-Fi profile. The AP
# experiment is disabled by default; only a supervised trial can arm it.
[ -r "$D/token" ] && [ "$(cat "$D/token")" = "$token" ] || exit 0
sync
reboot
exit 1
