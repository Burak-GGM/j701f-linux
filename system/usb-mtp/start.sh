#!/bin/sh
# Written by Claude 2026-10-10 (roadmap 2, C; owner's permission of 2026-10-10).
# Installed as /usr/local/sbin/j701f-usb-mtp, started from /etc/local.d.
# Adds an MTP function to the USB gadget that the initramfs set up (serial
# shell + network), served by uMTP-Responder. The gadget is taken off the bus
# for about two seconds while the function is added, so the computer sees the
# phone disconnect and come back once per boot.
export PATH=/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
G=/sys/kernel/config/usb_gadget/j701f_diagnostic
exec >> /run/j701f-usb-mtp.log 2>&1
echo "== $(date -u) =="
[ -d "$G" ] && [ -x /usr/local/bin/umtprd ] || { echo "no gadget or no umtprd"; exit 0; }
[ -e "$G/configs/c.1/ffs.mtp" ] && { echo "already set up"; exit 0; }
udc=$(cat "$G/UDC")
[ -n "$udc" ] || udc=$(ls /sys/class/udc | head -1)
echo "" > "$G/UDC" 2>/dev/null
# The USB network function (ncm.usb0, set up by the initramfs) was the way in
# before Wi-Fi worked. It makes every computer the phone is plugged into show a
# new wired connection and nothing uses it any more (owner's question,
# 2026-10-13): taken out of the configuration here, while the gadget is off
# the bus anyway. The serial shell stays. To keep the network: touch
# /etc/j701f-usb-net.
if [ ! -e /etc/j701f-usb-net ] && [ -L "$G/configs/c.1/ncm.usb0" ]; then
    rm "$G/configs/c.1/ncm.usb0" && echo "USB network function removed from the gadget"
fi
mkdir -p "$G/functions/ffs.mtp" /dev/ffs-mtp
ln -s "$G/functions/ffs.mtp" "$G/configs/c.1/ffs.mtp"
grep -q ' /dev/ffs-mtp ' /proc/mounts || mount -t functionfs mtp /dev/ffs-mtp
start-stop-daemon --start --background --make-pidfile --pidfile /run/umtprd.pid \
    --stdout /run/umtprd.log --stderr /run/umtprd.log --exec /usr/local/bin/umtprd
# umtprd must have written its descriptors to ep0 before the gadget can bind
n=0
while [ ! -e /dev/ffs-mtp/ep1 ] && [ $n -lt 20 ]; do sleep 0.5; n=$((n + 1)); done
echo "$udc" > "$G/UDC" && echo "gadget bound to $udc with MTP" || {
    echo "bind with MTP failed; removing the function again"
    kill "$(cat /run/umtprd.pid)" 2>/dev/null; umount /dev/ffs-mtp
    rm -f "$G/configs/c.1/ffs.mtp"; rmdir "$G/functions/ffs.mtp"
    echo "$udc" > "$G/UDC"
}
# The SD card (mounted by /etc/fstab at /media/sdcard, when one is in the slot)
# becomes a second storage. Added at run time so that without a card the
# computer does not see an empty "SD card" that is really the root filesystem.
if mountpoint -q /media/sdcard; then
    sleep 1
    umtprd '-cmd:addstorage:/media/sdcard SD-card rw' && echo "SD card added as second storage"
fi
exit 0
