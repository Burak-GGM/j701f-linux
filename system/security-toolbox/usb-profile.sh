#!/bin/sh
# Manage only optional functions of the existing J701F USB gadget.
# The serial console and MTP links are never removed.
set -eu
G=/sys/kernel/config/usb_gadget/j701f_diagnostic
C=$G/configs/c.1
F=$G/functions
mode=${1:-status}
[ -d "$C" ] || { echo 'J701F USB gadget missing' >&2; exit 1; }
status() {
    printf 'UDC: %s\n' "$(cat "$G/UDC")"
    for n in acm.usb0 ffs.mtp ncm.usb0 hid.usb0 mass_storage.usb0; do
        if [ -L "$C/$n" ]; then printf '%s: on\n' "$n"; else printf '%s: off\n' "$n"; fi
    done
}
[ "$mode" = status ] && { status; exit 0; }
case "$mode" in network-on|network-off|hid-on|hid-off|storage-on|storage-off) ;; *) echo 'unknown profile action' >&2; exit 2;; esac
[ "$(id -u)" = 0 ] || { echo 'root required' >&2; exit 1; }
[ -L "$C/acm.usb0" ] && [ -L "$C/ffs.mtp" ] || { echo 'serial/MTP baseline missing' >&2; exit 1; }
[ -e /dev/ffs-mtp/ep1 ] || { echo 'MTP is not ready' >&2; exit 1; }
mkdir /run/j701f-usb-profile.lock || { echo 'another USB profile operation is running' >&2; exit 1; }
trap 'rmdir /run/j701f-usb-profile.lock' EXIT
udc=$(cat "$G/UDC")
[ -n "$udc" ] || { echo 'gadget is not bound; refusing to change it' >&2; exit 1; }
old_ncm=off; [ -L "$C/ncm.usb0" ] && old_ncm=on
old_hid=off; [ -L "$C/hid.usb0" ] && old_hid=on
old_storage=off; [ -L "$C/mass_storage.usb0" ] && old_storage=on
# Prepare HID before unbinding; unsupported kernels fail without interrupting USB.
if [ "$mode" = hid-on ] && [ ! -d "$F/hid.usb0" ]; then
    mkdir "$F/hid.usb0" || { echo 'HID gadget function unavailable in this kernel' >&2; exit 1; }
    if ! {
        printf 1 > "$F/hid.usb0/protocol" &&
        printf 1 > "$F/hid.usb0/subclass" &&
        printf 8 > "$F/hid.usb0/report_length" &&
        python3 -c 'import sys;sys.stdout.buffer.write(bytes.fromhex("05010906a101050719e029e71500250175019508810295017508810195057501050819012905910295017503910195067508150025650507190029658100c0"))' > "$F/hid.usb0/report_desc"
    }; then
        rmdir "$F/hid.usb0" 2>/dev/null || true
        echo 'Could not configure HID keyboard function' >&2
        exit 1
    fi
fi
# Use a separate image, never a live block partition or mounted filesystem.
if [ "$mode" = storage-on ] && [ ! -d "$F/mass_storage.usb0" ]; then
    mkdir "$F/mass_storage.usb0" || { echo 'Mass-storage gadget function unavailable' >&2; exit 1; }
fi
if [ "$mode" = storage-on ]; then
    SHARE=/home/burak-alpine/j701f/usb-share
    IMAGE=$SHARE/toolbox.img
    mkdir -p "$SHARE"
    chmod 700 "$SHARE"
    if [ ! -e "$IMAGE" ]; then
        command -v mkfs.vfat >/dev/null || { echo 'dosfstools is required' >&2; exit 1; }
        truncate -s 64M "$IMAGE"
        mkfs.vfat -F 32 -n J701F_TOOLS "$IMAGE" >/dev/null || { rm -f "$IMAGE"; exit 1; }
    fi
    [ -f "$IMAGE" ] && [ ! -L "$IMAGE" ] || { echo 'Unsafe share image path' >&2; exit 1; }
    chown burak-alpine:burak-alpine "$SHARE" "$IMAGE"
    chmod 600 "$IMAGE"
    printf 1 > "$F/mass_storage.usb0/lun.0/ro"
    printf 1 > "$F/mass_storage.usb0/lun.0/removable"
    printf '%s' "$IMAGE" > "$F/mass_storage.usb0/lun.0/file"
fi
restore() {
    # Always release the lock, even when one rollback step fails.
    set +e
    printf '\n' > "$G/UDC"
    [ ! -L "$C/ncm.usb0" ] || rm "$C/ncm.usb0"
    [ ! -L "$C/hid.usb0" ] || rm "$C/hid.usb0"
    [ ! -L "$C/mass_storage.usb0" ] || rm "$C/mass_storage.usb0"
    [ "$old_ncm" != on ] || ln -s "$F/ncm.usb0" "$C/ncm.usb0"
    [ "$old_hid" != on ] || ln -s "$F/hid.usb0" "$C/hid.usb0"
    [ "$old_storage" != on ] || ln -s "$F/mass_storage.usb0" "$C/mass_storage.usb0"
    printf '%s' "$udc" > "$G/UDC"
    rmdir /run/j701f-usb-profile.lock
}
trap 'restore' EXIT
printf '\n' > "$G/UDC"
case "$mode" in
    network-on) [ -L "$C/ncm.usb0" ] || ln -s "$F/ncm.usb0" "$C/ncm.usb0" ;;
    network-off) [ ! -L "$C/ncm.usb0" ] || rm "$C/ncm.usb0" ;;
    hid-on) [ -L "$C/hid.usb0" ] || ln -s "$F/hid.usb0" "$C/hid.usb0" ;;
    hid-off) [ ! -L "$C/hid.usb0" ] || rm "$C/hid.usb0" ;;
    storage-on) [ -L "$C/mass_storage.usb0" ] || ln -s "$F/mass_storage.usb0" "$C/mass_storage.usb0" ;;
    storage-off)
        [ ! -L "$C/mass_storage.usb0" ] || rm "$C/mass_storage.usb0"
        [ ! -d "$F/mass_storage.usb0" ] || printf '\n' > "$F/mass_storage.usb0/lun.0/file" ;;
esac
printf '%s' "$udc" > "$G/UDC"
trap 'rmdir /run/j701f-usb-profile.lock' EXIT
status
