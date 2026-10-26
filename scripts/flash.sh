#!/usr/bin/env bash
# Recovery-only device-write entry point. Default is a printed plan, never a flash.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
execute=0
restore=0
device=''
while (( $# )); do
    case "$1" in
        --execute) execute=1; shift ;;
        --restore) restore=1; shift ;;
        --device)
            [[ $# -ge 2 ]] || { echo '--device needs an Odin-listed path' >&2; exit 2; }
            device=$2; shift 2 ;;
        *) echo 'Usage: scripts/flash.sh [--restore] [--device /dev/bus/usb/BBB/DDD] [--execute]' >&2; exit 2 ;;
    esac
done
archive="$PWD/build/recovery.tar"
verify_args=()
if (( restore )); then
    archive="$PWD/build/OrangeFox-restore.tar"
    verify_args+=(--restore)
fi
python3 tools/recovery.py verify-tar "$archive" "${verify_args[@]}"
if (( ! restore )); then python3 tools/recovery.py verify; fi
printf '\nPartition touched: RECOVERY only, selected by the sole tar member recovery.img.\n'
printf 'This replaces the installed recovery. It does not repair the Android bootloop.\n'
printf 'No BOOT, SYSTEM, DATA, PIT, BL/sboot, EFS, TrustZone, modem, or RPMB write is requested.\n'
printf 'No erase, repartition, BL/CP/CSC archive, or reboot option is passed.\n'
printf 'Archive SHA-256: '
sha256sum "$archive"
cmd=("$PWD/tools/odin4" -a "$archive")
[[ -z "$device" ]] || cmd+=(-d "$device")
printf 'Command: '; printf '%q ' "${cmd[@]}"; printf '\n'
if (( ! execute )); then
    echo 'PLAN ONLY. For a deliberate flash, add --execute and --device with the path from tools/odin4 -l.'
    exit 0
fi
[[ -x tools/odin4 ]] || { echo 'Missing tools/odin4 executable' >&2; exit 1; }
[[ "$device" =~ ^/dev/bus/usb/[0-9]{3}/[0-9]{3}$ ]] || { echo 'Refusing: explicit Odin USB path required' >&2; exit 1; }
echo 'Confirm the physical phone is SM-J701F in Download Mode and RECOVERY is the intended target.'
echo 'Download Mode should remain available when only RECOVERY is changed; this is not a hardware guarantee.'
printf 'Type exactly FLASH RECOVERY to overwrite RECOVERY: '
read -r answer
[[ "$answer" == 'FLASH RECOVERY' ]] || { echo 'Cancelled'; exit 1; }
# Validate again immediately before Odin reads the archive.
python3 tools/recovery.py verify-tar "$archive" "${verify_args[@]}"
echo 'Writing RECOVERY only via the validated single-member AP archive.'
exec "${cmd[@]}"
