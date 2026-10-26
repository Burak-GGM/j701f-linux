#!/bin/bash
# Written by Claude 2026-10-13 (roadmap 3.7). Backs up what makes this phone
# "the J701F port" rather than a plain Alpine install, from the RUNNING system,
# and rehearses the restore without touching the live files.
#
#   tools/phone-backup.sh            back up, verify, rehearse
#   tools/phone-backup.sh --no-rehearsal
#
# What goes in: /etc, /sbin (the project's start-up scripts live there),
# /usr/local, the user's .config and .local/share, and from ~/j701f the
# modules, the battery helper and the reboot-recovery helpers. Not the images
# under ~/j701f (they are in build/ on the computer) and not the rest of the
# home directory.
#
# Where it goes: the SD card (/media/sdcard/j701f-backups) when one is mounted,
# otherwise ~/j701f/backups. The archive contains secrets (Wi-Fi key, password
# hashes, SSH host keys): it stays on the phone's card and is NOT copied to the
# computer or into the repository.
#
# The archive is made, checked and unpacked by recovery/scripts/backup.sh - the
# same script the recovery's Backup page uses - so either can read the other's
# archives. The rehearsal unpacks into an empty directory on the phone and
# compares every file with the live one; it never writes over the system.
set -euo pipefail
cd "$(dirname "$0")/.."
H=burak-alpine@${J701F_PHONE_IP:-$(cat .phone-ip 2>/dev/null || echo j701f.local)}
O=(-o BatchMode=yes -o ConnectTimeout=6)
REHEARSE=1; [ "${1:-}" = --no-rehearsal ] && REHEARSE=0
ssh "${O[@]}" "$H" 'mkdir -p ~/j701f/backup'
scp "${O[@]}" -q recovery/scripts/backup.sh "$H:j701f/backup/backup.sh"
ssh "${O[@]}" "$H" REHEARSE=$REHEARSE sh -s <<'REMOTE'
set -eu
B=/home/burak-alpine/j701f/backup
if mountpoint -q /media/sdcard; then DEST=/media/sdcard/j701f-backups; else DEST=/home/burak-alpine/j701f/backups; fi
mkdir -p "$DEST"
out=$(sudo -n sh "$B/backup.sh" create / "$DEST" etc sbin usr/local \
        home/burak-alpine/.config home/burak-alpine/.local/share \
        home/burak-alpine/j701f/modules home/burak-alpine/j701f/battery \
        home/burak-alpine/j701f/boot-swap/reboot-recovery home/burak-alpine/j701f/boot-swap/reboot-recovery.sh)
echo "$out"
A=$(echo "$out" | sed -n 's/^backup: CREATED \([^ ]*\) .*/\1/p')
[ -n "$A" ]
sudo -n sh "$B/backup.sh" verify "$A"
[ "$REHEARSE" = 1 ] || exit 0
# Rehearsal: into an empty directory on the phone's own filesystem (the card's
# FAT cannot hold owners, modes or links), compared with the live files.
S=$B/rehearsal
[ ! -e "$S" ] || { echo "rehearsal directory $S exists from an earlier run: remove it first"; exit 1; }
mkdir "$S"
sudo -n sh "$B/backup.sh" restore "$A" "$S"
rc=0
sudo -n python3 - "$S" <<'PY' || rc=$?
import os, stat, sys
scratch = sys.argv[1]
same = changed = missing = other = 0
examples = []
for base, dirs, files in os.walk(scratch):
    for name in files + [d for d in dirs if os.path.islink(os.path.join(base, d))]:
        r = os.path.join(base, name); live = '/' + os.path.relpath(r, scratch)
        try:
            a, b = os.lstat(r), os.lstat(live)
        except FileNotFoundError:
            missing += 1; examples.append('gone since: ' + live); continue
        # BusyBox tar does not set the owner of a symbolic link (it becomes root's);
        # for links only the type and the target are compared.
        if stat.S_IFMT(a.st_mode) != stat.S_IFMT(b.st_mode) or (
                not stat.S_ISLNK(a.st_mode) and (a.st_mode, a.st_uid, a.st_gid) != (b.st_mode, b.st_uid, b.st_gid)):
            other += 1; examples.append('type/owner/mode: ' + live); continue
        if stat.S_ISLNK(a.st_mode):
            ok = os.readlink(r) == os.readlink(live)
        elif stat.S_ISREG(a.st_mode):
            ok = a.st_size == b.st_size and open(r, 'rb').read() == open(live, 'rb').read()
        else:
            ok = True
        if ok: same += 1
        else: changed += 1; examples.append('content changed since: ' + live)
print('rehearsal: %d files identical to the live system, %d changed since the backup, %d gone, %d with different type/owner/mode'
      % (same, changed, missing, other))
for e in examples[:12]: print('   ' + e)
sys.exit(1 if other else 0)
PY
sudo -n rm -rf /home/burak-alpine/j701f/backup/rehearsal
echo "rehearsal directory removed; archive kept: $A"
exit $rc
REMOTE
