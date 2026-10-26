#!/bin/bash
# Install the local toolbox after the phone is back on its saved home Wi-Fi.
# Does not activate an AP, alter BOOT/RECOVERY, or play sound.
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(cat build/coord/locks/phone/owner 2>/dev/null)" = codex ] || {
    echo 'Take the phone coordination lock as codex first.' >&2; exit 1;
}
H=burak-alpine@${J701F_PHONE_IP:-$(cat .phone-ip 2>/dev/null || echo j701f.local)}
O=(-o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=yes
   -o UserKnownHostsFile=build/phone-ssh-known-hosts)
on() { ssh "${O[@]}" "$H" "$@"; }
[ "$(on "awk '\$2==\"/\"{print substr(\$4,1,2)}' /proc/mounts")" = rw ] || {
    echo 'Installed system is not reachable and writable.' >&2; exit 1;
}
on 'sudo -n apk add py3-pyside6 nmap tcpdump dosfstools'
on 'mkdir -p ~/j701f/security-toolbox ~/.local/share/applications'
scp "${O[@]}" system/security-toolbox/{app.py,backend.py,hid-send.py,usb-profile.sh,ap-mode.sh,ap-restore.sh} "$H:j701f/security-toolbox/"
scp "${O[@]}" system/security-toolbox/network-toolbox.desktop "$H:.local/share/applications/"
on 'cd ~/j701f/security-toolbox && python3 -m py_compile app.py backend.py hid-send.py && sh -n usb-profile.sh ap-mode.sh ap-restore.sh && QT_QPA_PLATFORM=offscreen python3 -c "from PySide6.QtWidgets import QApplication; import app; q=QApplication([]); w=app.Toolbox(); print(w.windowTitle()); w.close()"'
for file in app.py backend.py hid-send.py usb-profile.sh ap-mode.sh ap-restore.sh; do
    local_sha=$(sha256sum "system/security-toolbox/$file" | cut -d' ' -f1)
    phone_sha=$(on "sha256sum ~/j701f/security-toolbox/$file | cut -d' ' -f1")
    [ "$local_sha" = "$phone_sha" ] || { echo "Hash mismatch: $file" >&2; exit 1; }
done
bash tools/phone-health.sh
echo 'Toolbox installed and checked. HID and BLE still require a verified kernel update.'
