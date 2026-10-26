#!/bin/bash
# Written by Claude 2026-10-09. Remote screenshot of the phone's Plasma session:
# wake the output, unlock the logind session, optionally open the action drawer
# with an injected swipe, capture through KWin and convert to PNG on the host.
# Usage: tools/phone-screenshot.sh OUT.png [drawer] [phone-ip]
set -euo pipefail
cd "$(dirname "$0")/.."
OUT=${1:?out.png}; MODE=${2:-home}; PHONE=${3:-${J701F_PHONE_IP:-$(cat .phone-ip 2>/dev/null || echo j701f.local)}}
O=(-o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=build/phone-ssh-known-hosts)
scp "${O[@]}" -q tools/inject-swipe.py burak-alpine@"$PHONE":/tmp/
ssh "${O[@]}" burak-alpine@"$PHONE" "MODE=$MODE sh -s" <<'REMOTE'
P=$(pidof plasmashell)
export $(sudo -n cat /proc/$P/environ | tr '\0' '\n' | grep -E '^(DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR|WAYLAND_DISPLAY)=')
kscreen-doctor --dpms on >/dev/null 2>&1
S=$(loginctl list-sessions --no-legend | awk '$4=="seat0"{print $1; exit}'); sudo -n loginctl unlock-session "$S"; sleep 2
qdbus6 org.kde.plasmashell /Mobile org.kde.plasmashell.closeActionDrawer >/dev/null 2>&1
if [ "$MODE" = drawer ]; then sudo -n python3 /tmp/inject-swipe.py /dev/input/event0 360 6 360 900 40 0.2; sleep 2; fi
# Claude 2026-10-10: keep the reported "width height stride format"; the logical size
# follows the display scale (720x1280 at 100 %, 450x800 at 160 %).
~/.local/bin/kwin-screenshot /tmp/shot.raw >/tmp/shot.dims
if [ "$MODE" = drawer ]; then qdbus6 org.kde.plasmashell /Mobile org.kde.plasmashell.closeActionDrawer >/dev/null 2>&1; fi
REMOTE
mkdir -p build/screenshots
scp "${O[@]}" -q burak-alpine@"$PHONE":/tmp/shot.raw build/screenshots/shot.raw
DIMS=$(ssh "${O[@]}" burak-alpine@"$PHONE" cat /tmp/shot.dims | awk '{print $1, $2, $3}')
python3 tools/raw-to-png.py build/screenshots/shot.raw "$OUT" $DIMS
echo "$OUT"
