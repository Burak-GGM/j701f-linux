#!/bin/sh
# Written by Claude 2026-10-10 (roadmap 2, F.3). Small settings of the recovery
# that must survive a reboot (so far: the interface language). The recovery has
# no writable filesystem of its own and never writes to the installed system,
# so they live in one 512-byte block of the RECOVERY slot itself, 1 MiB before
# its end - far behind the image (16 of 38 MiB) and untouched when a new image
# is installed (tools/install-recovery.sh writes only the image's length).
#
#   settings.sh get KEY          prints the value (nothing if unset)
#   settings.sh set KEY VALUE    letters, digits, "-" and "_" only
#
# Tests: J701F_RECOVERY_SETTINGS_DEV = a regular file standing in for the slot.
set -eu
MAGIC=J701F-RECOVERY-SETTINGS-1
die() { echo "settings: REFUSED: $*"; exit 1; }
dev=${J701F_RECOVERY_SETTINGS_DEV:-}
if [ -z "$dev" ]; then
    for d in /sys/class/block/mmcblk0p*; do
        grep -qx 'PARTNAME=RECOVERY' "$d/uevent" 2>/dev/null || continue
        [ "$(cat "$d/size")" = 77824 ] || die "RECOVERY has an unexpected size"
        dev=/dev/${d##*/}
    done
    [ -n "$dev" ] && [ -b "$dev" ] || die "no RECOVERY partition"
    blocks=77824
else
    [ -f "$dev" ] || die "test device is not a regular file"
    blocks=$(( $(wc -c < "$dev") / 512 ))
fi
at=$((blocks - 2048))
[ "$at" -gt 40960 ] || die "slot too small to keep settings clear of the image"
current() {  # the stored lines, or nothing if the block was never written
    dd if="$dev" bs=512 skip="$at" count=1 2>/dev/null | tr -d '\0' | { read -r first || true; [ "$first" = "$MAGIC" ] && cat || true; }
}
ok() { case "$1" in ''|*[!A-Za-z0-9_-]*) return 1 ;; esac; }
case "${1:-}" in
get)
    ok "${2:-}" || die "bad key"
    current | sed -n "s/^$2=//p" | head -1
    ;;
set)
    ok "${2:-}" && ok "${3:-}" || die "key and value may contain only letters, digits, - and _"
    { echo "$MAGIC"; current | grep -v "^$2=" || true; echo "$2=$3"; } > /tmp/settings.$$
    [ "$(wc -c < /tmp/settings.$$)" -le 512 ] || { rm -f /tmp/settings.$$; die "settings block is full"; }
    dd if=/dev/zero bs=512 count=1 2>/dev/null | cat /tmp/settings.$$ - | dd of="$dev" bs=512 seek="$at" count=1 conv=notrunc 2>/dev/null
    rm -f /tmp/settings.$$; sync
    [ "$(sh "$0" get "$2")" = "$3" ] || die "read-back differs"
    echo "settings: $2=$3"
    ;;
*) echo "usage: settings.sh get KEY | set KEY VALUE" >&2; exit 2 ;;
esac
