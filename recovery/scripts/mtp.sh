#!/bin/sh
# Written by Claude 2026-10-10 (roadmap 2, C.3). The computer sees the phone's
# storage over USB (MTP) while the recovery runs: the installed system's home
# directory read-only, the SD card read-write. Same program as on the
# installed system (uMTP-Responder), carried in /recovery/lib.
#
#   mtp.sh up | down | status
set -u
here=$(dirname "$0")
G=/sys/kernel/config/usb_gadget/j701f_diagnostic
C=/run/umtprd.conf
say() { echo "mtp: $*"; }
die() { say "REFUSED: $*"; exit 1; }
mounted() { grep -q " $1 " /proc/mounts; }
running() { [ -r /run/umtprd.pid ] && kill -0 "$(cat /run/umtprd.pid)" 2>/dev/null; }

down() {
    running && kill "$(cat /run/umtprd.pid)" 2>/dev/null
    rm -f /run/umtprd.pid
    [ -e "$G/configs/c.1/ffs.mtp" ] || return 0
    udc=$(cat "$G/UDC"); [ -n "$udc" ] || udc=$(ls /sys/class/udc | head -1)
    echo "" > "$G/UDC" 2>/dev/null
    mounted /dev/ffs-mtp && umount /dev/ffs-mtp
    rm -f "$G/configs/c.1/ffs.mtp"; rmdir "$G/functions/ffs.mtp" 2>/dev/null
    echo "$udc" > "$G/UDC"
}

case "${1:-}" in
up)
    running && { say "UP already"; exit 0; }
    [ -d "$G" ] || die "no USB gadget"
    command -v umtprd >/dev/null 2>&1 || die "umtprd is not in this image"
    {
        echo 'loop_on_disconnect 1'
        sh "$here/storage.sh" mount-root >/dev/null 2>&1 && [ -d /mnt/root/home/burak-alpine ] &&
            echo 'storage "/mnt/root/home/burak-alpine" "System (read-only)" "ro"'
        sh "$here/storage.sh" mount-sd >/dev/null 2>&1 && echo 'storage "/mnt/sd" "SD card" "rw"'
        cat <<'CONF'
manufacturer "Samsung"
product "SM-J701F Recovery"
serial "j701f-recovery"
firmware_version "recovery"
interface "MTP"
usb_vendor_id  0x04E8
usb_product_id 0x6860
usb_class 0x6
usb_subclass 0x1
usb_protocol 0x1
usb_dev_version 0x3008
usb_functionfs_mode 0x1
usb_dev_path   "/dev/ffs-mtp/ep0"
usb_epin_path  "/dev/ffs-mtp/ep1"
usb_epout_path "/dev/ffs-mtp/ep2"
usb_epint_path "/dev/ffs-mtp/ep3"
usb_max_packet_size 0x200
CONF
    } > "$C"
    grep -q '^storage' "$C" || die "neither the system nor an SD card could be mounted"
    udc=$(cat "$G/UDC"); [ -n "$udc" ] || udc=$(ls /sys/class/udc | head -1)
    echo "" > "$G/UDC" 2>/dev/null
    mkdir -p "$G/functions/ffs.mtp" /dev/ffs-mtp
    ln -s "$G/functions/ffs.mtp" "$G/configs/c.1/ffs.mtp"
    mounted /dev/ffs-mtp || mount -t functionfs mtp /dev/ffs-mtp
    umtprd -conf "$C" > /run/umtprd.log 2>&1 &
    echo $! > /run/umtprd.pid
    n=0; while [ ! -e /dev/ffs-mtp/ep1 ] && [ $n -lt 20 ]; do sleep 1; n=$((n + 1)); done
    if echo "$udc" > "$G/UDC"; then say "UP: $(grep -c '^storage' "$C") storage(s)"
    else down; die "the USB gadget did not accept the MTP function"; fi
    ;;
down) down; say "DOWN" ;;
status) running && say "UP" || say "DOWN" ;;
*) echo "usage: mtp.sh up | down | status" >&2; exit 2 ;;
esac
