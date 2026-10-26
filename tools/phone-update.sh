#!/bin/bash
# Written by Claude 2026-10-13 (roadmap 3.6). Alpine package updates for the
# phone, done carefully:
#
#   tools/phone-update.sh              show what would be upgraded, change nothing
#   tools/phone-update.sh --apply      upgrade the packages that are not "sensitive"
#   tools/phone-update.sh --apply --include-sensitive     upgrade everything
#
# "Sensitive" are the packages this port leans on in ways an update has broken
# on other devices or could break here: the graphics stack and the desktop
# (Mesa, KWin, Plasma, Qt, SDDM), sound and camera (PipeWire, WirePlumber,
# libcamera), and what the phone needs to come up and be reachable (musl,
# BusyBox, OpenRC, eudev, D-Bus, elogind, NetworkManager, wpa_supplicant,
# OpenSSH, firmware). They are held back unless asked for, so that they are
# upgraded when somebody is there to look at the screen afterwards.
#
# Before anything is changed the installed versions are written to
# ~/j701f/updates/ on the phone (what to go back to), and afterwards the
# health check runs. There is no automatic rollback: Alpine's stable
# repository does not keep old versions, so going back means the package files
# apk leaves in its cache (/var/cache/apk) or a backup (tools/phone-backup.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
H=burak-alpine@${J701F_PHONE_IP:-$(cat .phone-ip 2>/dev/null || echo j701f.local)}
O=(-o BatchMode=yes -o ConnectTimeout=6)
APPLY=0; SENS=0
for a in "$@"; do case "$a" in --apply) APPLY=1 ;; --include-sensitive) SENS=1 ;; *) echo "unknown option $a"; exit 2 ;; esac; done
SENSITIVE='^(mesa|kwin|plasma|qt6-|kf6-|sddm|pipewire|wireplumber|libcamera|musl|busybox|openrc|eudev|udev|dbus|elogind|networkmanager|wpa_supplicant|openssh|linux-firmware|libdrm|wayland|xwayland|bluez|polkit)'
ssh "${O[@]}" "$H" APPLY=$APPLY SENS=$SENS SENSITIVE="'$SENSITIVE'" sh -s <<'REMOTE'
set -eu
sudo -n apk update >/dev/null 2>&1 || { echo "apk update failed (no network?)"; exit 1; }
# "(1/4) Upgrading name (old -> new)"
apk upgrade --simulate 2>/dev/null | sed -n 's/^([0-9/]*) Upgrading \([^ ]*\) (\(.*\))$/\1 \2/p' > /tmp/j701f-upgrades.txt
n=$(wc -l < /tmp/j701f-upgrades.txt)
[ "$n" -gt 0 ] || { echo "nothing to upgrade"; rm -f /tmp/j701f-upgrades.txt; exit 0; }
plain=; held=
while read -r name versions; do
    if echo "$name" | grep -qE "$SENSITIVE"; then held="$held $name"; echo "  sensitive  $name  $versions"
    else plain="$plain $name"; echo "  ordinary   $name  $versions"; fi
done < /tmp/j701f-upgrades.txt
rm -f /tmp/j701f-upgrades.txt
[ "$APPLY" = 1 ] || { echo "$n package(s) could be upgraded; nothing changed (use --apply)"; exit 0; }
if [ "$SENS" = 1 ]; then todo="$plain $held"; else todo=$plain; fi
[ -n "$(echo $todo)" ] || { echo "only sensitive packages are waiting; nothing changed (use --include-sensitive)"; exit 0; }
mkdir -p /home/burak-alpine/j701f/updates
before=/home/burak-alpine/j701f/updates/$(date +%Y%m%d-%H%M%S)-before.txt
apk info -v | sort > "$before"
echo "installed versions recorded in $before"
# shellcheck disable=SC2086
sudo -n apk upgrade $todo
echo "upgraded:$todo"
[ -z "$held" ] || [ "$SENS" = 1 ] || echo "held back:$held"
REMOTE
if [ "$APPLY" = 1 ]; then echo "--- health check"; bash tools/phone-health.sh | grep -v '^ok' || echo "all ok"; fi
