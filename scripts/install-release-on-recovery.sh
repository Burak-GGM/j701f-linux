#!/bin/sh
# Install a J701F release from an SD card while the project's RAM recovery runs.
# This is deliberately DATA-only: BOOT and RECOVERY must already contain the
# compatible, working mainline kernel and rescue system.
set -eu
set -o pipefail

BB=/bin/busybox
UUID=4ce26b55-8a59-4fb7-aad4-919a5c2cefeb
SECTORS=23314432
BYTES=11936989184
DEV=/dev/mmcblk0p24
SOURCE=/mnt/sd/j701f-release
execute=no
erase=no
# Host tests (tests/test_install_release_on_recovery.py) prefix every absolute
# path with T_ROOT and use plain files for the block devices; nothing else changes.
P=
if [ "${J701F_INSTALLER_TEST:-}" = 1 ]; then
    P=${T_ROOT:?}; BB=${T_BB:?}
    SECTORS=${T_SECTORS:-$SECTORS}; BYTES=${T_BYTES:-$BYTES}; UUID=${T_UUID:-$UUID}
fi
DEV=$P$DEV
SOURCE=$P$SOURCE
is_block() { [ -b "$1" ] || { [ -n "$P" ] && [ -f "$1" ]; }; }
dev_bytes() {
    if [ -b "$1" ]; then "$BB" blockdev --getsize64 "$1"; else "$BB" stat -c %s "$1"; fi
}

say() { printf 'J701F INSTALL: %s\n' "$*"; }
die() { say "REFUSED: $*" >&2; exit 1; }
sha() { "$BB" sha256sum "$1" | "$BB" awk '{print $1}'; }
mounted_target() {
    # /proc/self/mountinfo uses the device's major:minor regardless of whether
    # it was mounted by /dev path, PARTUUID, label or another symlink.
    devnum=$($BB cat "$P/sys/class/block/mmcblk0p24/dev")
    "$BB" awk -v dev="$devnum" '$3==dev {found=1} END {exit !found}' "$P/proc/self/mountinfo"
}
read_hash() {
    [ -f "$1" ] || die "missing hash file $1"
    value=$($BB awk 'NR==1 {print $1}' "$1")
    case "$value" in *[!0-9a-f]*|'') die "invalid hash in $1";; esac
    [ "${#value}" -eq 64 ] || die "invalid hash length in $1"
    printf '%s\n' "$value"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --source) [ "$#" -ge 2 ] || die '--source needs a directory'; SOURCE=$2; shift 2 ;;
        --execute) execute=yes; shift ;;
        --erase-userdata) erase=yes; shift ;;
        *) die "unknown argument: $1" ;;
    esac
done

say 'This replaces ALL USERDATA, including Android/internal-storage files.'
say 'A failed flash can brick normal boot until recovery/Download Mode repair.'
say 'BOOT and RECOVERY are not written. Existing compatible BOOT is required.'
say 'An interruption can leave Linux unbootable; the recovery remains available.'
[ "$erase" = yes ] || die 'explicit --erase-userdata is required'
[ -x "$BB" ] || die 'recovery BusyBox is missing'
[ -d "$SOURCE" ] || die "release directory not found: $SOURCE"
SOURCE=$("$BB" readlink -f "$SOURCE") || die 'cannot resolve release directory'
case "$SOURCE" in "$P"/mnt/sd/*) ;; *) die 'release must be staged on external SD under /mnt/sd' ;; esac
sddev=$($BB awk -v m="$P/mnt/sd" '$2==m {print $1}' "$P/proc/mounts")
case "$sddev" in /dev/mmcblk[0-9]*p[0-9]*|/dev/mmcblk[0-9]*) ;; *) die '/mnt/sd is not an MMC device mount' ;; esac
sdcard=${sddev#/dev/}
sdcard=${sdcard%p[0-9]*}
"$BB" grep -Eq '^mmcblk[0-9]+$' <<EOF || die 'invalid SD block-device name'
$sdcard
EOF
[ "$($BB cat "$P/sys/class/block/$sdcard/device/type" 2>/dev/null)" = SD ] || die 'release source is not on external SD'

payload=$SOURCE/userdata.ext4.gz
compressed_hash=$SOURCE/userdata.ext4.gz.sha256
raw_hash=$SOURCE/userdata.ext4.sha256
[ -f "$payload" ] || die 'userdata.ext4.gz is missing'
want_compressed=$(read_hash "$compressed_hash")
want_raw=$(read_hash "$raw_hash")

# Never accept a stale file or a caller-controlled partition path. The actual
# hardware geometry and device-tree identity must agree with this single model.
is_block "$DEV" || die "USERDATA device $DEV is absent"
[ -r "$P/sys/class/block/mmcblk0p24/uevent" ] || die 'no USERDATA sysfs metadata'
"$BB" grep -qx 'PARTNAME=USERDATA' "$P/sys/class/block/mmcblk0p24/uevent" || die 'partition 24 is not USERDATA'
actual_sectors=$($BB cat "$P/sys/class/block/mmcblk0p24/size")
[ "$actual_sectors" = "$SECTORS" ] || die "unexpected USERDATA sectors: $actual_sectors"
actual_bytes=$(dev_bytes "$DEV")
[ "$actual_bytes" = "$BYTES" ] || die "unexpected USERDATA byte size: $actual_bytes"
"$BB" grep -q 'samsung,j7velte' "$P/proc/device-tree/compatible" || die 'device tree is not j7velte'
[ "$("$BB" uname -m)" = aarch64 ] || die 'recovery is not AArch64'
is_block "$P/dev/mmcblk0p10" || die 'BOOT device is missing'
"$BB" grep -qx 'PARTNAME=BOOT' "$P/sys/class/block/mmcblk0p10/uevent" || die 'partition 10 is not BOOT'
"$BB" strings "$P/dev/mmcblk0p10" | "$BB" grep -x 'bootcmd=j701f_ramboot' >/dev/null || \
    die 'BOOT does not contain the compatible J701F mainline handoff'
mounted_target && die 'USERDATA is mounted; unmount it before installation'

say "Verifying compressed payload $("$BB" basename "$payload")"
[ "$(sha "$payload")" = "$want_compressed" ] || die 'compressed payload checksum mismatch'
say 'Verifying the complete decompressed image before touching USERDATA.'
actual_raw=$("$BB" gunzip -c "$payload" | "$BB" sha256sum | "$BB" awk '{print $1}')
[ "$actual_raw" = "$want_raw" ] || die 'decompressed image checksum mismatch'
say "Preflight passed: $actual_bytes-byte USERDATA, complete gzip, hashes present."
if [ "$execute" != yes ]; then
    say 'DRY RUN ONLY. Add --execute --erase-userdata to write USERDATA.'
    exit 0
fi

status=$SOURCE/install.status
"$BB" rm -f "$status"
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
trap finish EXIT
for pid in $($BB pidof recovery-ui 2>/dev/null || :); do
    if kill -STOP "$pid" 2>/dev/null; then paused_pids="$paused_pids $pid"; fi
done
mounted_target && die 'USERDATA was remounted during preflight'
say 'Writing USERDATA from external SD. Keep power and SD connected.'
if [ -b "$DEV" ]; then "$BB" blockdev --setrw "$DEV" || die 'could not switch USERDATA to writable'; fi
mounted_target && die 'USERDATA was remounted before the write'
"$BB" gunzip -c "$payload" | "$BB" dd of="$DEV" bs=4194304 conv=fsync
"$BB" sync
mounted_target && die 'USERDATA was mounted during the write'
if [ -b "$DEV" ]; then "$BB" blockdev --flushbufs "$DEV" || die 'could not flush USERDATA buffers before read-back'; fi
echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || :
say 'Reading back the entire USERDATA partition for SHA-256 verification.'
got_raw=$(sha "$DEV")
[ "$got_raw" = "$want_raw" ] || die "full USERDATA read-back mismatch: $got_raw"
actual_uuid=$("$BB" blkid "$DEV" | "$BB" sed -n 's/.* UUID="\([^"]*\)".*/\1/p')
[ "$actual_uuid" = "$UUID" ] || die "installed filesystem UUID mismatch: $actual_uuid"
say "WRITTEN AND VERIFIED: USERDATA SHA-256 $got_raw"
