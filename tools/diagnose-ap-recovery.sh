#!/bin/bash
# Read-only AP failure evidence after the phone rejoins home Wi-Fi.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/assessment
H=burak-alpine@${J701F_PHONE_IP:-$(cat .phone-ip 2>/dev/null || echo j701f.local)}
O=(-o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=yes
   -o UserKnownHostsFile=build/phone-ssh-known-hosts)
ssh "${O[@]}" "$H" sh -s <<'REMOTE' > build/assessment/ap-after-recovery.txt
printf '=== ACTIVE NETWORK ===\n'
nmcli -t -f NAME,UUID,DEVICE connection show --active
ip -brief -4 addr show dev wlan0
printf '\n=== AP STATE ===\n'
if [ -e /run/j701f-lab-ap/return-uuid ]; then echo 'AP return marker present'; else echo 'AP return marker absent'; fi
printf '\n=== TRIAL RESULT WITHOUT GENERATED PASSWORD ===\n'
for f in ~/j701f/security-toolbox/ap-trial.log ~/j701f/security-toolbox/ap-trial2.log; do
    [ ! -r "$f" ] || sed -E '/[Pp]assword:/d' "$f"
done
printf '\n=== RESTORE LOG ===\n'
sudo -n tail -70 /run/j701f-lab-ap-restore.log 2>/dev/null || true
printf '\n=== WIFI DRIVER LOG ===\n'
sudo -n dmesg | grep -Ei 'brcmf|wlan0|cfg80211' | tail -55
REMOTE
printf 'Saved redacted diagnostic: %s\n' "$PWD/build/assessment/ap-after-recovery.txt"
