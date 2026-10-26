#!/usr/bin/env python3
"""Observe the authorized RECOVERY diagnostic trial over its exact USB serial ID."""
import argparse
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/recovery-trial'


def ports():
    found = []
    for tty in Path('/sys/class/tty').glob('ttyACM*'):
        device = (tty / 'device').resolve()
        for parent in (device, *device.parents):
            serial = parent / 'serial'
            if serial.is_file():
                identity = serial.read_text().strip()
                if identity in ('j701f-diagnostic', 'J701F-LINUX-CONSOLE'):
                    found.append(('/dev/' + tty.name, identity))
                break
    return found


def usb_read(port, usb, script, marker):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    saved = termios.tcgetattr(fd)
    try:
        usb.serial_settings(fd)
        return usb.command_session(fd, script, marker, timeout=20)
    finally:
        try: termios.tcsetattr(fd, termios.TCSANOW, saved)
        except (OSError, termios.error): pass
        os.close(fd)


def pin_discovered_address(original, discovered):
    """Reuse the trusted phone public key for an address learned over its USB shell."""
    import ipaddress
    ipaddress.IPv4Address(discovered)
    known = ROOT / 'build/phone-ssh-known-hosts'
    lines = known.read_text().splitlines()
    keys = [line.split()[1:] for line in lines if line.split() and line.split()[0] == original]
    if not keys:
        raise ValueError('Original pinned phone host key missing')
    existing = [line.split()[1:] for line in lines if line.split() and line.split()[0] == discovered]
    if any(key not in keys for key in existing):
        raise ValueError('Discovered address already has a different pinned key')
    additions = [discovered + ' ' + ' '.join(key) for key in keys if key not in existing]
    if additions:
        known.write_text('\n'.join(lines + additions) + '\n')


def download_port(topology):
    if not topology or not re.fullmatch(r'[0-9]+-[0-9]+(?:\.[0-9]+)*', topology):
        return None
    device = Path('/sys/bus/usb/devices') / topology
    try:
        if ((device / 'idVendor').read_text().strip() != '04e8' or
                (device / 'idProduct').read_text().strip() != '685d'):
            return None
        bus = int((device / 'busnum').read_text())
        number = int((device / 'devnum').read_text())
        return f'/dev/bus/usb/{bus:03d}/{number:03d}'
    except (OSError, ValueError):
        return None


def observe(phone, reboot, out=OUT):
    out = out.resolve()
    if not out.is_relative_to(ROOT / 'build/kernel'):
        raise ValueError('Trial output must be under build/kernel')
    import ipaddress
    ipaddress.IPv4Address(phone)
    manifest = json.loads((out / 'manifest.json').read_text())
    if 'MAINLINE_RECOVERY_FULL_READBACK_VERIFIED' not in (out / 'phone-flash.txt').read_text():
        raise ValueError('RECOVERY flashing read-back evidence missing')
    spec = importlib.util.spec_from_file_location('usb', ROOT / 'tools/usb-console.py')
    usb = importlib.util.module_from_spec(spec); spec.loader.exec_module(usb)
    options = ['-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-i', str(Path.home() / '.ssh/id_ed25519'),
               '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(ROOT / 'build/phone-ssh-known-hosts'),
               '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=1']
    host = 'burak-alpine@' + phone
    if reboot:
        policy = json.loads((ROOT / 'kernel/hardware-trial-policy.json').read_text())
        if not (policy.get('manual_recovery_available') is True or
                policy.get('independent_recovery_verified') is True or
                (policy.get('unattended_failure_accepted') is True and
                 policy.get('accepted_attempt_consumed') is False and
                 manifest['candidate_sha256'] == policy.get('accepted_unattended_candidate_sha256'))):
            raise ValueError('Hardware trial held: no verified recovery path while the user is away')
        if manifest.get('diagnostic_currently_installed') is False:
            raise ValueError('Diagnostic is no longer installed; preserve the restored rescue')
        phone_trial_dir = manifest.get('phone_trial_dir', '/home/burak-alpine/j701f-kernel-trial')
        if not re.fullmatch(r'/home/burak-alpine/j701f-kernel-trial(?:-[a-z0-9-]+)?', phone_trial_dir):
            raise ValueError('Unexpected phone staging path')
        script = '''set -eu
cd /home/burak-alpine/j701f-kernel-trial
cc -O2 -Wall -Wextra -Werror reboot-recovery.c -o reboot-recovery
./reboot-recovery
x=$(sudo -n sha256sum /dev/mmcblk0p11); [ "${x%% *}" = RECOVERY_SHA ]
x=$(sudo -n sha256sum /dev/mmcblk0p10); [ "${x%% *}" = BOOT_SHA ]
printf 'J701F_RECOVERY_PREFLIGHT_VERIFIED\\n'
'''.replace('RECOVERY_SHA', manifest['after_partition_sha256']).replace('BOOT_SHA', manifest['boot_sha256']).replace('/home/burak-alpine/j701f-kernel-trial', phone_trial_dir)
        policy['accepted_attempt_consumed'] = True
        (ROOT / 'kernel/hardware-trial-policy.json').write_text(json.dumps(policy, indent=2)+'\n')
        request = subprocess.run(['ssh', *options, host, 'sh -s'], input=script, text=True,
                                 capture_output=True, timeout=90)
        (out / 'reboot-request.txt').write_text(request.stdout + request.stderr)
        if 'J701F_RECOVERY_PREFLIGHT_VERIFIED' not in request.stdout or request.returncode != 0:
            raise ValueError('Recovery preflight failed: ' + request.stdout + request.stderr)
        command = 'sudo -n ' + phone_trial_dir + '/reboot-recovery --execute'
        try:
            request = subprocess.run(['ssh', *options, host, command], text=True,
                                     capture_output=True, timeout=25)
            stdout, stderr, returncode = request.stdout, request.stderr, request.returncode
        except subprocess.TimeoutExpired as error:
            stdout = (error.stdout or b'').decode() if isinstance(error.stdout, bytes) else (error.stdout or '')
            stderr = (error.stderr or b'').decode() if isinstance(error.stderr, bytes) else (error.stderr or '')
            returncode = None
        with (out / 'reboot-request.txt').open('a') as log:
            log.write(stdout + stderr)
        if 'J701F_REQUESTING_RECOVERY_BOOT' not in stdout or returncode not in (0, 255, None):
            raise ValueError('Recovery reboot was not acknowledged: ' + stdout + stderr)
        print('Recovery restart acknowledged; observing USB.', flush=True)
    start = time.monotonic()
    events = []; previous = None; captured = False; attempted = False; boot_return = False
    normal_checked = -10; discovered_phone = None
    download = None
    while time.monotonic() - start < 180:
        download = download_port(manifest.get('usb_topology'))
        if download:
            print('PHONE_RETURNED_DOWNLOAD_MODE', download, flush=True)
            break
        current = ports()
        if current != previous:
            event = dict(elapsed_s=round(time.monotonic()-start, 2), ports=current)
            events.append(event); print(event, flush=True); previous = current
        targets = [port for port, identity in current if identity == 'j701f-diagnostic']
        if len(targets) == 1 and not attempted:
            attempted = True
            fd = os.open(targets[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            saved = termios.tcgetattr(fd)
            try:
                usb.serial_settings(fd)
                output = usb.command_session(fd, '''set -e
test "$(uname -r)" = 6.15.0-BURAK-PANFROST-01
uname -a
cat /run/stage-ready
cat /sys/devices/system/cpu/online
head -n 8 /proc/meminfo
cat /proc/mounts
cat /run/usb.log
dmesg | head -n 600
printf 'MAINLINE_DIAGNOSTIC_CAPTURE_COMPLETE\n'
''', 'MAINLINE_DIAGNOSTIC_CAPTURE_COMPLETE', timeout=25)
                (out / 'mainline-usb-boot.txt').write_text(output+'\n')
                captured = True
                print('MAINLINE_USB_DIAGNOSTIC_CAPTURED', flush=True)
            except (OSError, ValueError, termios.error) as error:
                (out / 'mainline-usb-error.txt').write_text(str(error)+'\n')
                print('USB capture error:', str(error), flush=True)
            finally:
                try: termios.tcsetattr(fd, termios.TCSANOW, saved)
                except (OSError, termios.error): pass
                os.close(fd)
        normal_ports = [port for port, identity in current if identity == 'J701F-LINUX-CONSOLE']
        if time.monotonic()-start > 35 and len(normal_ports) == 1 and time.monotonic()-start-normal_checked > 10:
            normal_checked = time.monotonic()-start
            try:
                state = usb_read(normal_ports[0], usb, '''
if [ "$(cat /etc/j701f-system-version 2>/dev/null)" = BURAK_ALPINE_0_1 ]; then
    printf 'NORMAL_ALPINE_KERNEL=%s\\n' "$(uname -r)"
    /bin/busybox ip -4 -o addr show dev wlan0 | /bin/busybox awk '{split($4,a,"/");print "NORMAL_ALPINE_IP="a[1]}'
else
    printf 'J701F_RETURNED_RESCUE_ONLY\\n'
fi
printf 'J701F_NORMAL_STATE_CAPTURE_COMPLETE\\n'
''', 'J701F_NORMAL_STATE_CAPTURE_COMPLETE')
                (out / 'normal-usb-state.txt').write_text(state+'\n')
                match = re.search(r'^NORMAL_ALPINE_IP=([0-9.]+)$', state, re.MULTILINE)
                if 'NORMAL_ALPINE_KERNEL=3.18.140-SIMPLE-KERNEL_V1.0' in state and match:
                    discovered_phone = match.group(1)
                    pin_discovered_address(phone, discovered_phone)
                    host = 'burak-alpine@' + discovered_phone
            except (OSError, ValueError, termios.error) as error:
                (out / 'normal-usb-error.txt').write_text(str(error)+'\n')
            if not discovered_phone:
                time.sleep(1)
                continue
            result = subprocess.run(['ssh', *options, host, 'uname -r; cat /sys/devices/system/cpu/online'],
                                    text=True, capture_output=True, timeout=15)
            if result.returncode == 0:
                (out / 'normal-boot-return.txt').write_text(result.stdout+result.stderr)
                boot_return = True; print('NORMAL_ALPINE_SSH_RETURNED', flush=True); break
        time.sleep(1)
    (out / 'boot-observation.json').write_text(json.dumps(dict(
        recovery_reboot_requested=reboot, usb_events=events, mainline_usb_boot_verified=captured,
        normal_alpine_ssh_returned=boot_return, observation_seconds=round(time.monotonic()-start,2),
        discovered_phone_ipv4=discovered_phone,
        download_mode_device=download,
        gpu_acceleration_verified=False), indent=2)+'\n')
    print('Observation complete. mainline_usb_boot_verified=', captured, 'normal_alpine_ssh_returned=', boot_return)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phone', required=True)
    parser.add_argument('--reboot', action='store_true', help='Request the explicitly authorized recovery boot once')
    parser.add_argument('--trial-dir', type=Path, default=OUT)
    args = parser.parse_args()
    observe(args.phone, args.reboot, args.trial_dir)
