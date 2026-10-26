#!/bin/bash
# Written by Claude 2026-10-10. BOOT update through the project's own recovery
# (roadmap stage R), for the layout BOOT = mainline system, RECOVERY = graphical
# recovery. Replaces tools/run-boot-update.sh once the vendor 3.18 image is no
# longer in RECOVERY; until then that script is the one to use.
#
#   1. stage the image on the running system (the recovery mounts it read-only),
#   2. reboot into the recovery,
#   3. log in to the recovery over Wi-Fi (same address and host key),
#   4. let the recovery's flash-boot.sh write BOOT: it checks the image hash,
#      keeps the previous contents for a rollback, writes and reads back,
#   5. ask the recovery to reboot, wait for the system, compare the BOOT hash.
#
# Usage: tools/run-recovery-update.sh <name>   (expects build/kernel/boot-update-<name>,
# as written by tools/prepare-boot-update.py; only boot-mainline.img is used)
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=${1:?name}
D=build/kernel/boot-update-$NAME
IMG=$D/boot-mainline.img
T=/home/burak-alpine/j701f/boot-update/$NAME
H=burak-alpine@${J701F_PHONE_IP:-$(cat .phone-ip 2>/dev/null || echo j701f.local)}
O=(-o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=build/phone-ssh-known-hosts -o ServerAliveInterval=5 -o ServerAliveCountMax=3)
[ -f "$IMG" ] || { echo "no $IMG"; exit 1; }
SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
on() { ssh "${O[@]}" "$H" "$@"; }
root_mode() { on "awk '\$2==\"/\"{print substr(\$4,1,2)}' /proc/mounts" 2>/dev/null || true; }
wait_for() {  # rw = installed system, ro = recovery
    for _ in $(seq 60); do [ "$(root_mode)" = "$1" ] && return 0; sleep 5; done
    echo "phone did not come up as '$1'"; return 1
}

[ "$(root_mode)" = rw ] || { echo 'the installed system is not running (or not reachable)'; exit 1; }
on "umask 077; mkdir -p $T"
scp "${O[@]}" -q "$IMG" "$H:$T/boot-mainline.img"
[ "$(on "sha256sum $T/boot-mainline.img | cut -d' ' -f1")" = "$SHA" ] || { echo 'staged image differs'; exit 1; }
# reboot-recovery.sh (system/reboot-recovery.sh) removes the start-up guards'
# stamps, stops the desktop and remounts read-only before the restart.
scp "${O[@]}" -q "$(dirname "$0")/../system/reboot-recovery.sh" "$H:j701f/boot-swap/reboot-recovery.sh"
on "sync; sudo -n sh -c '(sleep 1; sh /home/burak-alpine/j701f/boot-swap/reboot-recovery.sh --execute) >/dev/null 2>&1 &'"
sleep 20
wait_for ro
# stay: do not boot the system by itself while this script is working
on "sudo -n sh -c ': > /run/recovery-state/stay; J701F_RECOVERY_STATE=/run/recovery-state sh /run/recovery/scripts/flash-boot.sh write $T/boot-mainline.img $SHA'" | tee "$D/recovery-update.txt"
grep -q 'WRITTEN AND VERIFIED' "$D/recovery-update.txt" || { echo 'the recovery did not confirm the write; it is still running, BOOT holds what it reports above'; exit 1; }
FULL=$(on "sudo -n sha256sum /dev/mmcblk0p10 | cut -d' ' -f1")
python3 - "$NAME" "$FULL" <<'PY'
import json,pathlib,sys
p=pathlib.Path('build/kernel/boot-slot.json'); s=json.loads(p.read_text())
s.update(boot_partition_sha256=sys.argv[2], boot_candidate=sys.argv[1], boot_partition_image=None, written_by='recovery')
p.write_text(json.dumps(s,indent=2)+'\n')
PY
on "sudo -n sh -c ': > /run/recovery-state/reboot'" || true
sleep 15
wait_for rw
[ "$(on "sudo -n sha256sum /dev/mmcblk0p10 | cut -d' ' -f1")" = "$FULL" ] || { echo 'BOOT hash changed after the reboot?'; exit 1; }
echo "BOOT updated through the recovery: $NAME, partition SHA-256 $FULL; system is up."
