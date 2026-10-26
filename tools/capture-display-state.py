#!/usr/bin/env python3
"""Temporarily load the read-only display probe, save its log, and unload it.

Requires a current phone lock, matching build metadata and pinned SSH key.
Does not load the panel driver or program display/clock/MMU registers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PHONE = os.environ.get('J701F_PHONE_IP') or (
    (ROOT / '.phone-ip').read_text().strip() if (ROOT / '.phone-ip').exists() else 'j701f.local')
ARTIFACT = ROOT / 'build/kernel/ea8061s-prototype'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def capture(worker, phone):
    lock = ROOT / 'build/coord/locks/phone'
    require((lock / 'owner').is_file() and (lock / 'owner').read_text().strip() == worker,
            'Acquire the phone lock for this worker with tools/coord.sh first')
    expiry = int((lock / 'time').read_text()) + 60 * int((lock / 'ttl').read_text())
    require(expiry - time.time() >= 120, 'Renew phone lock; less than two minutes remain')
    require(re.fullmatch(r'[0-9.]+', phone) is not None, 'Use the phone IPv4 address')

    module = ARTIFACT / 'j701f-display-info.ko'
    report = json.loads((ARTIFACT / 'report.json').read_text())
    expected = report['j701f-display-info']
    digest = hashlib.sha256(module.read_bytes()).hexdigest()
    source = ROOT / 'tools/kmod/ea8061s/j701f-display-info.c'
    require(report.get('built') and digest == expected['module_sha256'],
            'Read-only module does not match a successful build report')
    require(hashlib.sha256(source.read_bytes()).hexdigest() == expected['source_sha256'],
            'Read-only probe source changed since it was built')
    release = report['kernel_release']
    require(re.fullmatch(r'[A-Za-z0-9_.+-]+', release) is not None, 'Invalid kernel release')
    remote_path = '/tmp/j701f-display-info-' + worker + '-' + digest[:12] + '.ko'
    target = 'burak-alpine@' + phone
    options = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
               '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
               '-o', 'StrictHostKeyChecking=yes',
               '-o', 'UserKnownHostsFile=' + str(ROOT / 'build/phone-ssh-known-hosts')]
    subprocess.run(['scp', *options, '-q', str(module), target + ':' + remote_path],
                   check=True, timeout=45)
    script = f'''set -eu
loaded=0
cleanup() {{
    if [ "$loaded" = 1 ]; then sudo -n rmmod j701f_display_info; fi
    rm -f '{remote_path}'
}}
trap cleanup EXIT
test "$(uname -r)" = '{release}'
test "$(cat /sys/class/graphics/fb0/name)" = simpledrmdrmfb
test ! -d /sys/module/j701f_display_info
printf '%s  %s\\n' '{digest}' '{remote_path}' | sha256sum -c -
if sudo -n insmod '{remote_path}'; then
    loaded=1
else
    rc=$?
    sudo -n dmesg | awk '/j701f-display-info:/'
    exit "$rc"
fi
sudo -n dmesg | awk '/j701f-display-info:/'
sudo -n rmmod j701f_display_info
loaded=0
test ! -d /sys/module/j701f_display_info
printf '%s\\n' DISPLAY_READONLY_PROBE_UNLOADED
'''
    result = subprocess.run(['ssh', *options, target, 'sh -s'], input=script,
                            text=True, capture_output=True, timeout=60)
    (ARTIFACT / 'phone-display-state.txt').write_text(result.stdout + result.stderr)
    print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='')
    require(result.returncode == 0 and 'DISPLAY_READONLY_PROBE_UNLOADED' in result.stdout,
            'Capture/cleanup not confirmed; inspect saved log before releasing phone lock')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=('codex', 'claude'), default='codex')
    parser.add_argument('--phone', default=PHONE)
    args = parser.parse_args()
    try:
        capture(args.worker, args.phone)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        raise SystemExit('Display state capture: ' + str(exc))
