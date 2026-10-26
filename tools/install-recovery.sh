#!/bin/bash
# Written by Claude 2026-10-10. Writes a recovery image into the RECOVERY slot
# from the running installed system, over SSH (the recovery cannot rewrite the
# slot it is running from... it could, from RAM, but the installed system is
# the simpler place). Guards: partition name and size, image hash and header.
# The slot's previous contents are kept on the phone as recovery-previous.img
# and written back if the read-back differs.
# Usage: tools/install-recovery.sh <name>   (uses build/kernel/boot-update-<name>/boot-mainline.img)
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=${1:?name}
IMG=build/kernel/boot-update-$NAME/boot-mainline.img
H=burak-alpine@${J701F_PHONE_IP:-$(cat .phone-ip 2>/dev/null || echo j701f.local)}
O=(-o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=build/phone-ssh-known-hosts)
D=/home/burak-alpine/j701f/recovery-install
SHA=$(sha256sum "$IMG" | cut -d' ' -f1); N=$(stat -c %s "$IMG")
[ "$(ssh "${O[@]}" "$H" "awk '\$2==\"/\"{print substr(\$4,1,2)}' /proc/mounts")" = rw ] || { echo 'the installed system is not running'; exit 1; }
ssh "${O[@]}" "$H" "umask 077; mkdir -p $D"
scp "${O[@]}" -q "$IMG" "$H:$D/recovery-$NAME.img"
ssh "${O[@]}" "$H" "sudo -n sh -c '
set -eu
R=/dev/mmcblk0p11
grep -qx PARTNAME=RECOVERY /sys/class/block/mmcblk0p11/uevent
[ \"\$(cat /sys/class/block/mmcblk0p11/size)\" = 77824 ]
[ \"\$(sha256sum $D/recovery-$NAME.img | cut -d\" \" -f1)\" = $SHA ]
[ \"\$(head -c 8 $D/recovery-$NAME.img)\" = ANDROID! ]
dd if=\$R of=$D/recovery-previous.img bs=1048576 2>/dev/null; sync
a=\$(sha256sum \$R | cut -d\" \" -f1); [ \"\$(sha256sum $D/recovery-previous.img | cut -d\" \" -f1)\" = \"\$a\" ]
dd if=$D/recovery-$NAME.img of=\$R bs=1048576 conv=notrunc 2>/dev/null; sync; echo 3 > /proc/sys/vm/drop_caches
if [ \"\$(head -c $N \$R | sha256sum | cut -d\" \" -f1)\" = $SHA ]; then echo RECOVERY_WRITTEN_READBACK_VERIFIED \$(sha256sum \$R | cut -d\" \" -f1)
else dd if=$D/recovery-previous.img of=\$R bs=1048576 2>/dev/null; sync; echo READBACK_DIFFERS_PREVIOUS_WRITTEN_BACK; exit 1; fi
chown burak-alpine $D/*; chmod 600 $D/*
'" | tee build/kernel/boot-update-$NAME/recovery-install.txt
FULL=$(sed -n 's/^RECOVERY_WRITTEN_READBACK_VERIFIED //p' build/kernel/boot-update-$NAME/recovery-install.txt)
[ -n "$FULL" ]
python3 - "$NAME" "$SHA" "$FULL" <<'PY'
import json,pathlib,sys,datetime
p=pathlib.Path('build/kernel/recovery-slot.json'); s=json.loads(p.read_text()) if p.exists() else {}
s.update(contents='graphical recovery '+sys.argv[1], installed=str(datetime.date.today()), image='build/kernel/boot-update-%s/boot-mainline.img'%sys.argv[1], image_sha256=sys.argv[2], recovery_partition_sha256=sys.argv[3])
p.write_text(json.dumps(s,indent=2)+'\n')
PY
echo "recovery $NAME installed in RECOVERY"
