#!/bin/sh
# Written by Claude 2026-10-10. Kernel image writer for the recovery
# (roadmap R.4). Only ever writes the BOOT slot.
#
#   flash-boot.sh info
#   flash-boot.sh write IMAGE [SHA256]    verify, keep the old contents, write, read back
#   flash-boot.sh rollback                write the kept contents back
#
# Environment (tests only): J701F_RECOVERY_TARGET = a regular file standing in
# for the slot; J701F_RECOVERY_STATE = directory for the kept image.
# Exit status 0 only when the final read-back matched.
set -eu
STATE=${J701F_RECOVERY_STATE:-/var/lib/j701f-recovery}
PREV=$STATE/boot-previous.img
NOTE=$STATE/boot-slot.txt
BOOT_SECTORS=65536
say() { echo "flash-boot: $*"; }
die() { say "REFUSED: $*"; exit 1; }
sha() { sha256sum "$1" | cut -d' ' -f1; }
sha_head() { head -c "$2" "$1" | sha256sum | cut -d' ' -f1; }

find_target() {
    if [ -n "${J701F_RECOVERY_TARGET:-}" ]; then
        [ -f "$J701F_RECOVERY_TARGET" ] || die "test target is not a regular file"
        TARGET=$J701F_RECOVERY_TARGET
        TARGET_BYTES=$(wc -c < "$TARGET")
        return
    fi
    TARGET=
    for d in /sys/class/block/mmcblk0p*; do
        grep -qx 'PARTNAME=BOOT' "$d/uevent" 2>/dev/null || continue
        [ -z "$TARGET" ] || die "more than one partition is named BOOT"
        TARGET=/dev/${d##*/}
        [ "$(cat "$d/size")" = "$BOOT_SECTORS" ] || die "BOOT is not $BOOT_SECTORS sectors"
    done
    [ -n "$TARGET" ] && [ -b "$TARGET" ] || die "no BOOT partition found"
    [ "$(cat /sys/class/block/mmcblk0/removable)" = 0 ] || die "mmcblk0 is removable"
    TARGET_BYTES=$((BOOT_SECTORS * 512))
}

check_image() {
    [ -f "$1" ] || die "no such image file: $1"
    IMAGE_BYTES=$(wc -c < "$1")
    [ "$IMAGE_BYTES" -ge 4096 ] || die "image is too small to be a boot image"
    [ "$IMAGE_BYTES" -le "$TARGET_BYTES" ] || die "image ($IMAGE_BYTES bytes) is larger than the slot ($TARGET_BYTES)"
    [ "$(head -c 8 "$1")" = 'ANDROID!' ] || die "image does not start with the Android boot header"
    IMAGE_SHA=$(sha "$1")
    [ -z "${2:-}" ] || [ "$2" = "$IMAGE_SHA" ] || die "image SHA-256 is $IMAGE_SHA, expected $2"
}

put() { dd if="$1" of="$TARGET" bs=1048576 conv=notrunc 2>/dev/null; sync; }

cmd=${1:-}
case "$cmd" in
info)
    find_target
    say "slot $TARGET, $TARGET_BYTES bytes, SHA-256 $(sha "$TARGET")"
    [ -f "$NOTE" ] && say "recorded: $(cat "$NOTE")" || say "recorded: nothing"
    [ -f "$PREV" ] && say "previous image kept: $(sha "$PREV")" || say "previous image kept: none"
    ;;
write)
    find_target
    check_image "${2:-}" "${3:-}"
    mkdir -p "$STATE"
    # Keep what is there now; refuse to go on unless the copy is exact.
    dd if="$TARGET" of="$PREV.new" bs=1048576 2>/dev/null || { rm -f "$PREV.new"; die "no room in $STATE to keep the current contents; nothing was written"; }
    [ "$(sha_head "$PREV.new" "$TARGET_BYTES")" = "$(sha_head "$TARGET" "$TARGET_BYTES")" ] || { rm -f "$PREV.new"; die "could not keep an exact copy of the current contents"; }
    put "$2"
    if [ "$(sha_head "$TARGET" "$IMAGE_BYTES")" != "$IMAGE_SHA" ]; then
        say "read-back differs; writing the previous contents back"
        put "$PREV.new"
        [ "$(sha_head "$TARGET" "$TARGET_BYTES")" = "$(sha_head "$PREV.new" "$TARGET_BYTES")" ] && say "previous contents restored" || say "RESTORE ALSO FAILED"
        rm -f "$PREV.new"
        exit 1
    fi
    mv "$PREV.new" "$PREV"
    echo "$(basename "$2") sha256=$IMAGE_SHA written=$(date -u +%Y-%m-%dT%H:%MZ)" > "$NOTE"
    sync
    say "WRITTEN AND VERIFIED: $(basename "$2")"
    ;;
rollback)
    find_target
    [ -f "$PREV" ] || die "no previous image is kept"
    [ "$(wc -c < "$PREV")" = "$TARGET_BYTES" ] || die "kept image has the wrong size"
    put "$PREV"
    [ "$(sha_head "$TARGET" "$TARGET_BYTES")" = "$(sha "$PREV")" ] || { say "ROLLBACK READ-BACK DIFFERS"; exit 1; }
    echo "rolled back to the previous image sha256=$(sha "$PREV") at $(date -u +%Y-%m-%dT%H:%MZ)" > "$NOTE"
    sync
    say "ROLLED BACK AND VERIFIED"
    ;;
*)
    echo "usage: flash-boot.sh info | write IMAGE [SHA256] | rollback" >&2
    exit 2
    ;;
esac
