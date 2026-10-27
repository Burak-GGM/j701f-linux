#!/bin/sh
# Run a long DATA backup or installation independently of the USB serial login.
# The host starts this with BusyBox setsid and polls the .exit file on the SD.
set -eu
set -o pipefail

BB=/bin/busybox
SD=/mnt/sd/j701f-release
LOCK=/run/recovery-state/release-job.lock
mode=${1:-}
backup_id=${2:-}
case "$mode" in install|backup) ;; *) echo 'Expected install or backup' >&2; exit 2 ;; esac
[ -d /run/recovery-state ] && [ -x /recovery/scripts/storage.sh ] || exit 2
[ -d "$SD" ] || exit 2
[ ! -L "$SD" ] || exit 2
result=$SD/job-$mode.exit
[ ! -L "$result" ] && [ ! -L "$result.tmp" ] || exit 2
"$BB" mkdir "$LOCK" || { echo 'Another release job is active' >&2; exit 2; }
finish() {
    code=$?
    printf '%s\n' "$code" > "$result.tmp" || :
    "$BB" mv "$result.tmp" "$result" || :
    "$BB" sync || :
    "$BB" rmdir "$LOCK" || :
}
trap finish EXIT
"$BB" rm -f "$result"

if [ "$mode" = install ]; then
    sh "$SD/install-release-on-recovery.sh" --source "$SD" --execute --erase-userdata
    exit 0
fi

printf '%s\n' "$backup_id" | "$BB" grep -Eq '^preinstall-userdata-[0-9]{8}-[0-9]{6}$' || exit 2
sddev=$("$BB" awk '$2=="/mnt/sd" && $3=="vfat" {print $1}' /proc/mounts)
case "$sddev" in /dev/mmcblk[0-9]*p[0-9]*|/dev/mmcblk[0-9]*) ;;
    *) echo 'Physical FAT SD is not mounted at /mnt/sd' >&2; exit 2 ;; esac
sdcard=${sddev#/dev/}
sdcard=${sdcard%p[0-9]*}
printf '%s\n' "$sdcard" | "$BB" grep -Eq '^mmcblk[0-9]+$' || exit 2
[ "$("$BB" cat "/sys/class/block/$sdcard/device/type")" = SD ] || exit 2
free_kib=$("$BB" df -k /mnt/sd | "$BB" awk 'NR==2 {print $4}')
printf '%s\n' "$free_kib" | "$BB" grep -Eq '^[0-9]+$' || exit 2
[ "$free_kib" -ge 11919360 ] || {
    echo 'External SD lacks room for the complete USERDATA backup and reserve' >&2; exit 2;
}
prefix=/mnt/sd/j701f-backups/$backup_id
"$BB" mkdir -p /mnt/sd/j701f-backups
[ ! -e "$prefix.sha256" ] && [ ! -e "$prefix.part.aa" ] || {
    echo 'Backup name already exists' >&2; exit 2;
}
# The installer dry run immediately before this job proves model, geometry,
# external SD identity and an unmounted USERDATA. Check the mutable mount fact
# again before reading and use the same exact-size partition.
devnum=$("$BB" cat /sys/class/block/mmcblk0p24/dev)
"$BB" awk -v dev="$devnum" '$3==dev {found=1} END {exit !found}' /proc/self/mountinfo && {
    echo 'USERDATA was remounted; refusing backup' >&2; exit 2;
}
[ "$("$BB" cat /sys/class/block/mmcblk0p24/size)" = 23314432 ] || exit 2
[ "$("$BB" blockdev --getsize64 /dev/mmcblk0p24)" = 11936989184 ] || exit 2
echo 'Reading USERDATA for the pre-installation backup hash.'
"$BB" sha256sum /dev/mmcblk0p24 | "$BB" awk '{print $1}' > "$prefix.sha256"
echo 'Copying USERDATA to twelve 1 GB SD chunks.'
"$BB" split -b 1000000000 /dev/mmcblk0p24 "$prefix.part."
"$BB" sync
# Independent restore preflight catches a missing/short chunk or changed DATA.
sh "$SD/restore-userdata-on-recovery.sh" --backup-id "$backup_id" --restore-userdata
echo "BACKUP_VERIFIED $backup_id"
