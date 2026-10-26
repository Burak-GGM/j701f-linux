#!/bin/sh
# Written by Claude 2026-10-10. Storage actions for the recovery UI (roadmap
# R.6 and R.7). The installed system is only ever mounted read-only, without
# replaying its journal; the only place written to is the SD card.
#
#   storage.sh mount-root     mount the installed system read-only at $ROOT
#   storage.sh mount-sd       mount the SD card at $SD
#   storage.sh backup         settings and user data -> $SD/j701f-backups
#   storage.sh verify         check the newest archive there
#   storage.sh copy FILE      copy one file -> $SD/j701f-files (never overwrites)
#   storage.sh check          read-only filesystem check of the installed system
#   storage.sh log            end of the kernel log, and what pstore kept
#
# Tests set J701F_RECOVERY_ROOT / J701F_RECOVERY_SD to ordinary directories;
# a directory given that way is used as it is and nothing is mounted.
set -u
here=$(dirname "$0")
ROOT=${J701F_RECOVERY_ROOT:-}
SD=${J701F_RECOVERY_SD:-}
say() { echo "storage: $*"; }
die() { say "REFUSED: $*"; exit 1; }

part() {            # block device of the partition with this name
    for d in /sys/class/block/mmcblk0p*; do
        grep -qx "PARTNAME=$1" "$d/uevent" 2>/dev/null && { echo "/dev/${d##*/}"; return 0; }
    done
    return 1
}
mounted() { grep -q " $1 " /proc/mounts; }

mount_root() {
    [ -n "$ROOT" ] && { [ -d "$ROOT" ] || die "no such directory: $ROOT"; return 0; }
    ROOT=/mnt/root
    mounted "$ROOT" && return 0
    dev=$(part USERDATA) || die "USERDATA partition not found"
    mkdir -p "$ROOT"
    # The partition itself is switched to read-only first: on a writable device
    # ext4 cleans up orphaned inodes even for a read-only mount (seen in the
    # kernel log of the installed recovery, 2026-10-10: "1 orphan inode deleted").
    # recovery-main switches it back before the system is started.
    blockdev --setro "$dev" 2>/dev/null || die "could not make $dev read-only"
    # noload: do not replay the journal either, so not one block of the system changes
    mount -t ext4 -o ro,noload "$dev" "$ROOT" || { blockdev --setrw "$dev"; die "could not mount $dev read-only"; }
}
mount_sd() {
    [ -n "$SD" ] && { [ -d "$SD" ] || die "no such directory: $SD"; return 0; }
    SD=/mnt/sd
    mounted "$SD" && return 0
    dev=
    # the card is whichever MMC device says it is an SD card (mmcblk2 on the
    # mainline kernel, mmcblk1 on the vendor one); first partition, or the whole card
    for c in /sys/class/block/mmcblk[0-9]; do
        [ "$(cat "$c/device/type" 2>/dev/null)" = SD ] || continue
        for d in "/dev/${c##*/}p1" "/dev/${c##*/}"; do [ -b "$d" ] && { dev=$d; break 2; }; done
    done
    [ -n "$dev" ] || die "no SD card found"
    mkdir -p "$SD"
    mount "$dev" "$SD" || die "could not mount the SD card ($dev)"
}

case "${1:-}" in
mount-root) mount_root; say "MOUNTED read-only at $ROOT" ;;
mount-sd)   mount_sd; say "MOUNTED at $SD" ;;
backup)
    mount_root; mount_sd
    mkdir -p "$SD/j701f-backups" || die "could not create $SD/j701f-backups"
    sh "$here/backup.sh" create "$ROOT" "$SD/j701f-backups"
    ;;
verify)
    mount_sd
    newest=$(ls -1 "$SD"/j701f-backups/j701f-backup-*.tar.gz 2>/dev/null | tail -1)
    [ -n "$newest" ] || die "no backup found in $SD/j701f-backups"
    sh "$here/backup.sh" verify "$newest"
    ;;
copy)
    f=${2:-}
    [ -f "$f" ] || die "not a file: $f"
    mount_sd
    mkdir -p "$SD/j701f-files" || die "could not create $SD/j701f-files"
    t="$SD/j701f-files/$(basename "$f")"
    [ -e "$t" ] && die "already there: $t"
    cp "$f" "$t.part" && mv "$t.part" "$t" && sync || die "copy failed"
    say "COPIED to $t"
    ;;
check)
    command -v e2fsck >/dev/null 2>&1 || die "e2fsck is not in this image"
    dev=${J701F_RECOVERY_CHECK_DEV:-$(part USERDATA)} || die "USERDATA partition not found"
    [ -n "${J701F_RECOVERY_CHECK_DEV:-}" ] || ! mounted /mnt/root || umount /mnt/root || die "the system is mounted and busy"
    # -n: open read-only and answer "no" to every question; nothing is repaired
    e2fsck -n -f "$dev" 2>&1 | tail -12
    say "CHECK finished (read-only, nothing was changed)"
    ;;
log)
    dmesg 2>/dev/null | tail -40
    for f in /sys/fs/pstore/*; do [ -f "$f" ] && { say "pstore: ${f##*/}"; tail -15 "$f"; }; done
    say "LOG end"
    ;;
*) echo "usage: storage.sh mount-root | mount-sd | backup | verify | copy FILE | check | log" >&2; exit 2 ;;
esac
