#!/bin/sh
# Written by Claude 2026-10-10. Read-only system summary for the recovery UI
# (roadmap R.3). Prints "label|value" lines; never writes anything. Every probe
# is optional so that the same script runs on the computer for UI tests.
p() { [ -n "$2" ] && printf '%s|%s\n' "$1" "$2"; }

p "Running kernel" "$(uname -r)"
p "Built" "$(uname -v | sed 's/^#[0-9]* //')"

boot=$(ls /dev/disk/by-partlabel/BOOT /dev/block/by-name/BOOT 2>/dev/null | head -1)
[ -z "$boot" ] && for d in /sys/class/block/mmcblk0p*; do
    grep -qx 'PARTNAME=BOOT' "$d/uevent" 2>/dev/null && boot=/dev/${d##*/}
done
[ -n "$boot" ] && boot=$(readlink -f "$boot")
if [ -r "$boot" ] && [ -r "/sys/class/block/${boot##*/}/size" ]; then
    p "BOOT slot" "$boot, $(( $(cat /sys/class/block/${boot##*/}/size) / 2048 )) MiB"
    p "BOOT SHA-256" "$(sha256sum "$boot" | cut -c1-16)..."
else
    p "BOOT slot" "not readable here"
fi
# Name of the image, as recorded by the tool that wrote it.
for f in /mnt/root/var/lib/j701f-recovery/boot-slot.txt /var/lib/j701f-recovery/boot-slot.txt; do
    [ -r "$f" ] && { p "Installed image" "$(head -1 "$f")"; break; }
done

for b in /sys/class/power_supply/*; do
    [ -r "$b/capacity" ] && p "Battery" "$(cat "$b/capacity") %, $(cat "$b/status" 2>/dev/null)"
done
p "Memory" "$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{printf "%d of %d MiB free", a/1024, t/1024}' /proc/meminfo)"
root=$(df -h / 2>/dev/null | awk 'NR==2{print $4 " free of " $2}')
p "Root filesystem" "$root"
ls /sys/fs/pstore/*ramoops* >/dev/null 2>&1 && p "Last crash log" "present in /sys/fs/pstore" || p "Last crash log" "none"
