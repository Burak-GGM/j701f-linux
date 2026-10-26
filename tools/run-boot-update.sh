#!/bin/bash
# Written by Claude 2026-10-08. Host driver for a prepared BOOT update
# (tools/prepare-boot-update.py) in the swapped layout:
#   1. ask mainline Alpine (USB ACM shell) to reboot into 3.18 in RECOVERY,
#   2. find the phone on Wi-Fi with the pinned SSH host key,
#   3. stage and run the guarded update.sh, record the new BOOT hash,
#   4. reboot normally into the new mainline image.
# Usage: tools/run-boot-update.sh <name>   (expects build/kernel/boot-update-<name>)
set -euo pipefail
cd "$(dirname "$0")/.."
NAME=${1:?name}
# Claude 2026-10-10: since the graphical recovery was installed, RECOVERY no longer
# holds the vendor 3.18 system this script reboots into. Use
# tools/run-recovery-update.sh; this one works again only after
# tools/restore-vendor-recovery.sh has put 3.18 back.
if grep -q '"contents": "graphical' build/kernel/recovery-slot.json 2>/dev/null; then
    echo 'RECOVERY holds the graphical recovery: use tools/run-recovery-update.sh'; exit 1
fi
D=build/kernel/boot-update-$NAME
T=/home/burak-alpine/j701f/boot-update/$NAME
K=build/phone-ssh-known-hosts
NET=$(sed 's/\.[0-9]*$//' .phone-ip 2>/dev/null || echo 192.168.1)   # first three octets of the home network
O=(-o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$K)
KEY=$(awk -v net="$NET" '$1==net".146"{print $2" "$3; exit}' $K)
serial_ip() {  # wlan0 address as reported over the USB serial shell, if that shell answers
    [ -c /dev/ttyACM0 ] || return 0
    timeout 30 python3 - <<'PY' 2>/dev/null || true
import importlib.util, os, re, termios
spec=importlib.util.spec_from_file_location('usb','tools/usb-console.py'); usb=importlib.util.module_from_spec(spec); spec.loader.exec_module(usb)
fd=os.open('/dev/ttyACM0', os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK); saved=termios.tcgetattr(fd)
try:
    usb.serial_settings(fd)
    out=usb.command_session(fd, "ip -4 -o addr show wlan0; printf 'J701F_%s\\n' IPDONE\n", 'J701F_IPDONE', timeout=12)
    m=re.search(r'inet (192\.168\.\d+\.\d+)/', out or '')
    if m: print(m.group(1))
finally:
    try: termios.tcsetattr(fd, termios.TCSANOW, saved)
    except Exception: pass
    os.close(fd)
PY
}
find_phone() {  # prints the Wi-Fi address of the phone running 3.18, verified by host key
    for _ in $(seq 40); do
        # The 3.18 side gets a different DHCP lease now and then: J701F_PHONE_IP
        # (for example read over the USB serial shell) is tried before the scan. Seen so far:
        # .146, .77, .50, .79, .85 - so the scan covers .20-.230, the usual range first.
        for ip in ${J701F_PHONE_IP:-} $(serial_ip) $(seq -f $NET.%g 140 230) $(seq -f $NET.%g 20 139); do
            ping -c1 -W1 "$ip" >/dev/null 2>&1 || continue
            grep -q "^$ip " $K || echo "$ip $KEY" >> $K
            if [ "$(ssh "${O[@]}" burak-alpine@"$ip" uname -r 2>/dev/null)" = 3.18.140-SIMPLE-KERNEL_V1.0 ]; then
                echo "$ip"; return 0
            fi
            # Not the phone (or wrong key): drop the speculative pin again.
            sed -i "/^$ip /d" $K
        done
        sleep 3
    done
    return 1
}
if [ -c /dev/ttyACM0 ]; then
    python3 - <<'PY' || true
import importlib.util, os, termios
spec=importlib.util.spec_from_file_location('usb','tools/usb-console.py'); usb=importlib.util.module_from_spec(spec); spec.loader.exec_module(usb)
fd=os.open('/dev/ttyACM0', os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK); saved=termios.tcgetattr(fd)
try:
    usb.serial_settings(fd)
    try: usb.command_session(fd, "[ \"$(uname -r)\" = 3.18.140-SIMPLE-KERNEL_V1.0 ] || { rm -f /var/lib/j701f-gpufreq.pending /var/lib/j701f-audio.pending; sync; /home/burak-alpine/j701f/boot-swap/reboot-recovery --execute; }\n", 'NEVER', timeout=8)
    except Exception: pass
finally:
    try: termios.tcsetattr(fd, termios.TCSANOW, saved)
    except Exception: pass
    os.close(fd)
PY
    sleep 25
fi
PHONE=$(find_phone) || { echo 'Phone on 3.18 not found on Wi-Fi'; exit 1; }
echo "3.18 phone at $PHONE"
ssh "${O[@]}" burak-alpine@"$PHONE" "umask 077; mkdir -p $T"
scp "${O[@]}" -q "$D/boot-mainline.img" "$D/update.sh" "$D/restore-3.18-to-boot.sh" burak-alpine@"$PHONE":"$T"/
ssh "${O[@]}" burak-alpine@"$PHONE" "sudo -n sh $T/update.sh" 2>&1 | tee "$D/phone-update.txt"
grep -q MAINLINE_BOOT_UPDATE_FULL_READBACK_VERIFIED "$D/phone-update.txt"
python3 - "$NAME" <<'PY'
import json,pathlib,sys
d=pathlib.Path('build/kernel/boot-update-'+sys.argv[1]); m=json.loads((d/'manifest.json').read_text())
m.update(status='written-full-readback-verified', written=True); (d/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
p=pathlib.Path('build/kernel/boot-slot.json'); s=json.loads(p.read_text())
s.update(boot_partition_sha256=m['after_boot_partition_sha256'], boot_partition_image=str(d/'boot-partition-after.img'), boot_candidate=sys.argv[1])
p.write_text(json.dumps(s,indent=2)+'\n')
PY
ssh "${O[@]}" -o ServerAliveInterval=5 -o ServerAliveCountMax=1 burak-alpine@"$PHONE" "sync; sudo -n reboot" 2>/dev/null || true
echo 'BOOT updated; phone rebooting into mainline.'
