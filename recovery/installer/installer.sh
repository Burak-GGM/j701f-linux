#!/bin/sh
# Written by Claude 2026-10-27. Installs a J701F Alpine release into USERDATA
# from TWRP or OrangeFox (started by update-binary with the BusyBox shipped in
# the ZIP). Writes USERDATA only: BOOT, RECOVERY and every other partition are
# read at most. All commands go through "$BB" so the recovery's own tools do
# not matter.
#
#   $BB sh installer.sh OUTFD ZIPFILE
#
# Release contract (shared with scripts/install-release-on-recovery.sh):
# userdata.ext4.gz, userdata.ext4.gz.sha256, userdata.ext4.sha256, release.json;
# the raw image covers the whole partition and has a fixed filesystem UUID.
set -eu

OUTFD=${1:?outfd}
ZIP=${2:?zip}
BB=${BB:?BB must name the BusyBox binary}

UUID=4ce26b55-8a59-4fb7-aad4-919a5c2cefeb
SECTORS=23314432
BYTES=11936989184
BYNAME=/dev/block/platform/13540000.dwmmc0/by-name
PART=mmcblk0p24
SYS=/sys/class/block
SYSDEV=/sys/dev/block
PROC=/proc
INPUT=/dev/input
KEY_TIMEOUT=60
BOOT_MARK=bootcmd=j701f_ramboot
# Host tests replace the device paths and the expected geometry; nothing else.
if [ "${J701F_INSTALLER_TEST:-}" = 1 ]; then
    UUID=${T_UUID:-$UUID}; SECTORS=${T_SECTORS:-$SECTORS}; BYTES=${T_BYTES:-$BYTES}
    BYNAME=${T_BYNAME:-$BYNAME}; SYS=${T_SYS:-$SYS}; PROC=${T_PROC:-$PROC}; SYSDEV=${T_SYSDEV:-$SYSDEV}
    INPUT=${T_INPUT:-$INPUT}; KEY_TIMEOUT=${T_KEY_TIMEOUT:-$KEY_TIMEOUT}
fi

WORK=$($BB dirname "$0")
LOG=$WORK/install.log
ui() {
    printf 'ui_print %s\nui_print\n' "$*" >&"$OUTFD" 2>/dev/null || true
    printf '%s\n' "$*" >> "$LOG"
}
progress() { printf 'set_progress %s\n' "$1" >&"$OUTFD" 2>/dev/null || true; }
die() { ui "ABORTED: $*"; ui "Nothing was written." ; exit 1; }
sha() { $BB sha256sum "$1" | $BB awk '{print $1}'; }
read_hash() {
    [ -f "$1" ] || die "missing $($BB basename "$1")"
    v=$($BB awk 'NR==1 {print $1}' "$1")
    case "$v" in *[!0-9a-f]*|'') die "bad hash in $($BB basename "$1")" ;; esac
    [ "${#v}" -eq 64 ] || die "bad hash length in $($BB basename "$1")"
    printf '%s\n' "$v"
}

ui '================================'
ui ' J701F Linux release installer'
ui '================================'

# ---- 1. The phone ---------------------------------------------------------
bl=$($BB tr ' ' '\n' < "$PROC/cmdline" | $BB sed -n 's/^androidboot.bootloader=//p' | $BB head -n1)
case "$bl" in J701F*) ;; *) die "this is not an SM-J701F (bootloader '${bl:-unknown}')" ;; esac
device=''
for f in /prop.default /default.prop /system/build.prop; do
    [ -f "$f" ] || continue
    device=$($BB sed -n 's/^ro.product.device=//p' "$f" | $BB head -n1)
    [ -n "$device" ] && break
done
[ -z "$device" ] || [ "$device" = j7velte ] || die "recovery is built for '$device', not j7velte"
ui "Phone: SM-J701F, bootloader $bl"

# ---- 2. USERDATA, exactly the expected partition --------------------------
DEV=$BYNAME/USERDATA
[ -e "$DEV" ] || die "$DEV is missing"
real=$($BB readlink -f "$DEV")
[ "$($BB basename "$real")" = "$PART" ] || die "USERDATA is $real, expected $PART"
$BB grep -qx 'PARTNAME=USERDATA' "$SYS/$PART/uevent" || die "$PART is not named USERDATA"
[ "$($BB cat "$SYS/$PART/size")" = "$SECTORS" ] || die "USERDATA is not $SECTORS sectors"
if [ -b "$real" ]; then
    bytes=$($BB blockdev --getsize64 "$real")
elif [ "${J701F_INSTALLER_TEST:-}" = 1 ]; then
    bytes=$($BB stat -c %s "$real")
else
    die "$real is not a block device"
fi
[ "$bytes" = "$BYTES" ] || die "USERDATA is $bytes bytes, expected $BYTES"
UD=$($BB cat "$SYS/$PART/dev")
case "$UD" in *:*) ;; *) die "no major:minor for $PART" ;; esac
ui "USERDATA: $real ($UD), $BYTES bytes"

# ---- 3. BOOT must already hold the J701F Linux loader ---------------------
[ -e "$BYNAME/BOOT" ] || die 'BOOT partition not found'
if ! $BB head -c 33554432 "$BYNAME/BOOT" | $BB grep -a -q "$BOOT_MARK"; then
    die 'BOOT does not hold the J701F Linux loader. Install the BOOT image first; this ZIP never writes BOOT.'
fi
ui 'BOOT: J701F Linux loader present (left unchanged)'

# ---- 4. The release: inside the ZIP, or j701f-release/ beside it ----------
# Every mount of USERDATA by major:minor, so bind mounts and other names for
# it are found too; deepest first (so /sdcard binds go before /data).
userdata_mounts() {
    $BB awk -v d="$UD" '$3 == d {print length($5), $5}' "$PROC/self/mountinfo" | $BB sort -rn | $BB cut -d' ' -f2-
}
# Accept a file only if its real path lies on a filesystem whose block device
# is a physical SD card: whatever else (USERDATA, a bind of it, an emulated or
# FUSE view of internal storage, tmpfs) is refused. Prints the real path.
on_sd() {
    p=$($BB readlink -f "$1") && [ -e "$p" ] || return 1
    d=$($BB stat -c %d "$p") || return 1
    mm=$(( (d >> 8) & 0xfff )):$(( (d & 0xff) | ((d >> 12) & 0xfff00) ))
    [ "$mm" != "$UD" ] || return 1
    node=$($BB readlink -f "$SYSDEV/$mm") && [ -d "$node" ] || return 1
    disk=$node
    [ -f "$node/partition" ] && disk=$($BB dirname "$node")
    [ "$($BB cat "$disk/device/type" 2>/dev/null)" = SD ] || return 1
    printf '%s\n' "$p"
}
ZIP=$(on_sd "$ZIP") || die 'the ZIP is not on the SD card (internal storage is erased by this install). Copy it to the SD card.'

embedded=no
if $BB unzip -l "$ZIP" 2>/dev/null | $BB grep -q ' userdata.ext4.gz$'; then
    embedded=yes
    SRC=$WORK/release
    $BB mkdir -p "$SRC"
    for f in userdata.ext4.gz.sha256 userdata.ext4.sha256; do
        $BB unzip -p "$ZIP" "$f" > "$SRC/$f" || die "cannot read $f from the ZIP"
    done
    $BB unzip -p "$ZIP" release.json > "$SRC/release.json" 2>/dev/null || $BB rm -f "$SRC/release.json"
    payload() { $BB unzip -p "$ZIP" userdata.ext4.gz; }
    ui 'Release: inside the ZIP'
else
    SRC=$($BB dirname "$ZIP")/j701f-release
    [ -d "$SRC" ] || die "no release found: put j701f-release/ next to the ZIP ($SRC)"
    [ -f "$SRC/userdata.ext4.gz" ] || die 'userdata.ext4.gz is missing'
    for f in userdata.ext4.gz userdata.ext4.gz.sha256 userdata.ext4.sha256 release.json; do
        [ ! -e "$SRC/$f" ] || on_sd "$SRC/$f" >/dev/null || die "$f is not on the SD card (a link to internal storage?)"
    done
    PAYLOAD=$(on_sd "$SRC/userdata.ext4.gz")
    payload() { $BB cat "$PAYLOAD"; }
    ui "Release: $SRC"
fi
want_gz=$(read_hash "$SRC/userdata.ext4.gz.sha256")
want_raw=$(read_hash "$SRC/userdata.ext4.sha256")
# release.json (tools/build-release.py) must describe this partition. Only
# fixed values are compared, so no JSON parser is needed.
JSON=$SRC/release.json
[ -f "$JSON" ] || die 'release.json is missing'
json_has() { $BB tr -d ' \n\t' < "$JSON" | $BB grep -q "\"$1\":$2"; }
json_has sectors "$SECTORS" || die "release.json is not for a $SECTORS-sector USERDATA"
json_has bytes "$BYTES" || die "release.json is not for a $BYTES-byte USERDATA"
json_has filesystem_uuid "\"$UUID\"" || die 'release.json names another filesystem UUID'
$BB grep -q 'j7velte' "$JSON" || die 'release.json is not for the j7velte'
version=$($BB tr -d '\n' < "$JSON" | $BB sed -n 's/.*"root_version" *: *"\([^"]*\)".*/\1/p')
ui "Version: ${version:-unknown}"

ui 'Checking the release (SHA-256 and gzip)...'
progress 0.05
[ "$(payload | $BB sha256sum | $BB awk '{print $1}')" = "$want_gz" ] || die 'userdata.ext4.gz checksum mismatch'
progress 0.15
payload | $BB gunzip -t || die 'userdata.ext4.gz is damaged'
progress 0.25
ui 'Release verified.'

# ---- 5. Confirmation with the volume keys ---------------------------------
ui ' '
ui '!!! THIS ERASES ALL OF USERDATA !!!'
ui 'Android apps, data and internal storage'
ui '(photos, downloads) are deleted for good.'
ui 'BOOT, RECOVERY and EFS are not touched.'
ui ' '
ui "Volume UP   = erase and install"
ui "Volume DOWN = cancel ($KEY_TIMEOUT s: cancel)"

KEYF=$WORK/key
$BB rm -f "$KEYF"
watch_keys() {  # one 64-bit struct input_event (24 bytes) at a time
    while :; do
        rec=$($BB dd if="$1" bs=24 count=1 2>/dev/null | $BB od -An -tu2 -j16 -N8) || return 0
        [ -n "$rec" ] || return 0
        set -- "$1" $rec
        if [ "$2" = 1 ] && [ "$4" = 1 ]; then
            case "$3" in
                115) echo up > "$KEYF.tmp" && $BB mv "$KEYF.tmp" "$KEYF"; return 0 ;;
                114) echo down > "$KEYF.tmp" && $BB mv "$KEYF.tmp" "$KEYF"; return 0 ;;
            esac
        fi
    done
}
pids=''
for ev in "$INPUT"/event*; do
    [ -e "$ev" ] || continue
    watch_keys "$ev" & pids="$pids $!"
done
[ -n "$pids" ] || die 'no input devices to read the volume keys from'
t=0
while [ ! -f "$KEYF" ] && [ "$t" -lt "$KEY_TIMEOUT" ]; do $BB sleep 1; t=$((t + 1)); done
for p in $pids; do kill "$p" 2>/dev/null || true; done
answer=$($BB cat "$KEYF" 2>/dev/null || true)
[ "$answer" = up ] || die 'cancelled (no Volume UP)'
ui 'Confirmed.'

# ---- 6. Unmount USERDATA ---------------------------------------------------
for m in $(userdata_mounts); do
    $BB umount "$m" 2>/dev/null || die "cannot unmount $m (switch off MTP, then Mount > untick Data)"
done
[ -z "$(userdata_mounts)" ] || die 'USERDATA is still mounted'

# ---- 7. Write, read back, check --------------------------------------------
STATUS=$SRC/install.status
[ "$embedded" = yes ] && STATUS=$($BB dirname "$ZIP")/j701f-install.status
finish() {
    code=$?
    [ "$code" -eq 0 ] && s=PASS || s=FAIL
    { printf '%s\n' "$s"; $BB cat "$LOG"; } > "$STATUS.tmp" 2>/dev/null && $BB mv "$STATUS.tmp" "$STATUS" || true
    $BB sync
}
trap finish EXIT
die() {
    ui "FAILED: $*"
    ui 'USERDATA is incomplete: Linux will not start. BOOT and RECOVERY are unchanged; run the installer again.'
    exit 1
}
ui 'Writing USERDATA. Keep the phone powered and the SD card in.'
progress 0.30
[ -b "$real" ] && { $BB blockdev --setrw "$real" || die 'cannot make USERDATA writable'; }
payload | $BB gunzip -c | $BB dd of="$real" bs=4194304 conv=fsync 2>/dev/null || die 'write error'
$BB sync
progress 0.65
ui 'Reading back all of USERDATA...'
[ "$(sha "$real")" = "$want_raw" ] || die 'read-back SHA-256 does not match'
progress 0.95
got_uuid=$($BB blkid "$real" | $BB sed -n 's/.* UUID="\([^"]*\)".*/\1/p')
[ "$got_uuid" = "$UUID" ] || die "filesystem UUID is '$got_uuid', expected $UUID"
progress 1.0
ui ' '
ui "DONE: USERDATA written and verified ($want_raw)."
ui 'Reboot to system to start Linux.'
