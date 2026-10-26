#!/bin/bash
# Written by Claude 2026-10-10. Puts the vendor 3.18 fallback back into the
# RECOVERY slot, exactly as it was before the graphical recovery was installed
# (whole 38 MiB slot, kept on the phone and in build/backups/). Runs from the
# installed system over SSH; writes RECOVERY only, with read-back.
# Not run so far.
set -euo pipefail
cd "$(dirname "$0")/.."
H=burak-alpine@${J701F_PHONE_IP:-$(cat .phone-ip 2>/dev/null || echo j701f.local)}
O=(-o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=build/phone-ssh-known-hosts)
SHA=364f68347b0d362fc7d731812e1fc706c2679a26ecd7cf9b1f1fb3a7af538c86
F=/home/burak-alpine/j701f/recovery-install/recovery-slot-before.img
[ "$(sha256sum build/backups/recovery-slot-3.18-before-rec4.img | cut -d' ' -f1)" = "$SHA" ]
ssh "${O[@]}" "$H" "[ -f $F ]" || scp "${O[@]}" -q build/backups/recovery-slot-3.18-before-rec4.img "$H:$F"
ssh "${O[@]}" "$H" "sudo -n sh -c '
set -eu
grep -qx PARTNAME=RECOVERY /sys/class/block/mmcblk0p11/uevent
[ \"\$(cat /sys/class/block/mmcblk0p11/size)\" = 77824 ]
[ \"\$(sha256sum $F | cut -d\" \" -f1)\" = $SHA ]
dd if=$F of=/dev/mmcblk0p11 bs=1048576 2>/dev/null; sync; echo 3 > /proc/sys/vm/drop_caches
[ \"\$(sha256sum /dev/mmcblk0p11 | cut -d\" \" -f1)\" = $SHA ] && echo VENDOR_RECOVERY_RESTORED_READBACK_VERIFIED
'" | tee /dev/stderr | grep -q VENDOR_RECOVERY_RESTORED_READBACK_VERIFIED
python3 - <<'PY'
import json,pathlib
p=pathlib.Path('build/kernel/recovery-slot.json'); s=json.loads(p.read_text()); s.update(contents='vendor 3.18 fallback (restored)'); p.write_text(json.dumps(s,indent=2)+'\n')
PY
