#!/bin/sh
# Restore a complete, split USERDATA backup from the external SD card in the
# project's RAM recovery. Only /dev/mmcblk0p24 is ever opened for writing.
set -eu
set -o pipefail

BB=/bin/busybox
DEV=/dev/mmcblk0p24
SECTORS=23314432
BYTES=11936989184
BACKUP_DIR=/mnt/sd/j701f-backups
backup_id=
execute=no
restore=no

say() { printf 'J701F RESTORE: %s\n' "$*"; }
die() { say "REFUSED: $*" >&2; exit 1; }
mounted_target() {
    devnum=$("$BB" cat /sys/class/block/mmcblk0p24/dev)
    "$BB" awk -v dev="$devnum" '$3==dev {found=1} END {exit !found}' /proc/self/mountinfo
}
hash_file() { "$BB" sha256sum "$1" | "$BB" awk '{print $1}'; }

while [ "$#" -gt 0 ]; do
    case "$1" in
        --backup-id)
            [ "$#" -ge 2 ] || die '--backup-id needs a value'
            backup_id=$2; shift 2 ;;
        --execute) execute=yes; shift ;;
        --restore-userdata) restore=yes; shift ;;
        *) die "unknown argument: $1" ;;
    esac
done

say 'This REPLACES ALL USERDATA and internal-storage files with the selected backup.'
say 'BOOT and RECOVERY are not written. An interruption can leave Linux unbootable.'
[ "$restore" = yes ] || die 'explicit --restore-userdata is required'
[ -x "$BB" ] || die 'recovery BusyBox is missing'
[ -d /run/recovery-state ] && [ -x /recovery/scripts/storage.sh ] || \
    die 'run this only from the project RAM recovery'
printf '%s\n' "$backup_id" | "$BB" grep -Eq '^preinstall-userdata-[0-9]{8}-[0-9]{6}$' || \
    die 'backup ID must be preinstall-userdata-YYYYMMDD-HHMMSS'

# Accept only the mounted physical SD card, never another eMMC partition or a
# caller-selected directory. Backup file names are then derived from one ID.
sddev=$("$BB" awk '$2=="/mnt/sd" && $3=="vfat" {print $1}' /proc/mounts)
case "$sddev" in /dev/mmcblk[0-9]*p[0-9]*|/dev/mmcblk[0-9]*) ;;
    *) die 'external FAT SD is not mounted at /mnt/sd' ;; esac
sdcard=${sddev#/dev/}
sdcard=${sdcard%p[0-9]*}
printf '%s\n' "$sdcard" | "$BB" grep -Eq '^mmcblk[0-9]+$' || die 'invalid SD block-device name'
[ "$("$BB" cat "/sys/class/block/$sdcard/device/type" 2>/dev/null)" = SD ] || \
    die '/mnt/sd is not a physical SD card'
[ -d "$BACKUP_DIR" ] || die 'backup directory is missing from the SD card'

# Reject wrong hardware, an unexpected partition table, and any mount of the
# target even when the mount used a label, UUID or bind path instead of DEV.
[ "$(uname -m)" = aarch64 ] || die 'recovery is not AArch64'
"$BB" tr '\000' '\n' < /proc/device-tree/compatible | \
    "$BB" grep -Fxq 'samsung,j7velte' || die 'device tree is not j7velte'
[ -b "$DEV" ] || die 'USERDATA block device is absent'
"$BB" grep -qx 'PARTNAME=USERDATA' /sys/class/block/mmcblk0p24/uevent || \
    die 'partition 24 is not USERDATA'
[ "$("$BB" cat /sys/class/block/mmcblk0p24/size)" = "$SECTORS" ] || \
    die 'unexpected USERDATA sector count'
[ "$("$BB" blockdev --getsize64 "$DEV")" = "$BYTES" ] || \
    die 'unexpected USERDATA byte size'
mounted_target && die 'USERDATA is mounted; unmount it before restoring'

prefix=$BACKUP_DIR/$backup_id
status=$prefix.restore.status
state=FAIL
paused_pids=
finish() {
    code=$?
    if [ "$code" -eq 0 ]; then state=PASS; fi
    printf '%s\n' "$state" > "$status.tmp" || :
    "$BB" mv "$status.tmp" "$status" || :
    "$BB" sync || :
    for pid in $paused_pids; do kill -CONT "$pid" 2>/dev/null || :; done
}
if [ "$execute" = yes ]; then
    [ ! -L "$status" ] && [ ! -L "$status.tmp" ] || die 'restore status is linked'
    # An older PASS must not survive a failed attempt's preflight.
    printf 'FAIL\n' > "$status.tmp" || die 'cannot write restore status to SD'
    "$BB" mv "$status.tmp" "$status" || die 'cannot save restore status on SD'
    trap finish EXIT
fi
checksum=$prefix.sha256
[ -f "$checksum" ] && [ ! -L "$checksum" ] || die 'full-partition SHA-256 file is missing or linked'
expected=$("$BB" awk 'NR==1 {print $1}' "$checksum")
case "$expected" in *[!0-9a-f]*|'') die 'invalid backup SHA-256' ;; esac
[ "${#expected}" -eq 64 ] || die 'invalid backup SHA-256 length'
[ "$("$BB" wc -l < "$checksum")" -eq 1 ] || die 'backup SHA-256 file must contain one line'

# The backup command uses 1,000,000,000-byte split chunks. This exact 11+1
# sequence totals 11,936,989,184 bytes; no missing, additional, or linked part
# may silently turn a partial backup into a successful-looking restore.
set --
for suffix in aa ab ac ad ae af ag ah ai aj ak al; do
    set -- "$@" "$prefix.part.$suffix"
done
for part in "$prefix".part.*; do
    [ -e "$part" ] || die 'backup contains no chunks'
    case "${part##*.}" in aa|ab|ac|ad|ae|af|ag|ah|ai|aj|ak|al) ;;
        *) die "unexpected backup chunk: ${part##*/}" ;; esac
done
total=0
for part in "$@"; do
    [ -f "$part" ] && [ ! -L "$part" ] || die "missing or linked chunk: ${part##*/}"
    size=$("$BB" stat -c %s "$part") || die "cannot stat ${part##*/}"
    case "$part" in *.part.al) wanted=936989184 ;; *) wanted=1000000000 ;; esac
    [ "$size" = "$wanted" ] || die "wrong size for ${part##*/}: $size"
    total=$((total + size))
done
[ "$total" -eq "$BYTES" ] || die "backup length mismatch: $total"
say 'Reading all 12 backup chunks to verify the SHA-256 before writing.'
actual=$("$BB" cat "$@" | "$BB" sha256sum | "$BB" awk '{print $1}')
[ "$actual" = "$expected" ] || die "backup checksum mismatch: $actual"
say "Preflight passed: physical SD, J701F USERDATA, $total bytes, SHA-256 $actual"
if [ "$execute" != yes ]; then
    say 'DRY RUN ONLY. Add --execute --restore-userdata to write USERDATA.'
    exit 0
fi

for pid in $("$BB" pidof recovery-ui 2>/dev/null || :); do
    if kill -STOP "$pid" 2>/dev/null; then paused_pids="$paused_pids $pid"; fi
done
mounted_target && die 'USERDATA was remounted during preflight'
"$BB" blockdev --setrw "$DEV" || die 'could not make USERDATA writable'
mounted_target && die 'USERDATA was remounted before the write'
say 'Writing all backup chunks to USERDATA. Keep power and SD connected.'
"$BB" cat "$@" | "$BB" dd of="$DEV" bs=4194304 conv=fsync
"$BB" sync
mounted_target && die 'USERDATA was mounted during the write'
say 'Reading back the entire USERDATA partition for SHA-256 verification.'
# Read back from the eMMC, not from the page cache the write just filled.
"$BB" blockdev --flushbufs "$DEV" || die 'could not flush USERDATA buffers before read-back'
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || :
readback=$(hash_file "$DEV")
[ "$readback" = "$expected" ] || die "full USERDATA read-back mismatch: $readback"
say "RESTORED AND VERIFIED: USERDATA SHA-256 $readback"
