#!/usr/bin/env python3
"""Stage and install a DATA-only J701F release through the project's recovery.

The phone must already run the project's mainline BOOT and RAM recovery. For a
first installation from Android, use the recovery ZIP/manual SD instructions.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
FILES = ('userdata.ext4.gz', 'userdata.ext4.gz.sha256',
         'userdata.ext4.sha256', 'release.json')
STAGE = '/home/burak-alpine/j701f/release-stage'
SD = '/media/sdcard/j701f-release'
RECOVERY_SD = '/mnt/sd/j701f-release'
SERIAL_MODULE = ROOT / 'tools/usb-console.py'


def run(args, *, timeout=30, capture=False):
    result = subprocess.run(args, cwd=ROOT, check=True, timeout=timeout,
                            text=True, stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def preflight(directory):
    for name in FILES:
        if not (directory / name).is_file():
            raise ValueError(f'Missing release file: {directory / name}')
    payload = directory / FILES[0]
    if payload.stat().st_size >= 4_294_967_296:
        raise ValueError('Compressed image exceeds the FAT32 single-file limit')
    expected = (directory / FILES[1]).read_text().split()[0]
    if not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('Invalid compressed payload hash file')
    if digest(payload) != expected:
        raise ValueError('Compressed payload SHA-256 does not match')
    raw_expected = (directory / FILES[2]).read_text().split()[0]
    if not re.fullmatch(r'[0-9a-f]{64}', raw_expected):
        raise ValueError('Invalid raw payload hash file')
    release = json.loads((directory / 'release.json').read_text())
    if release.get('device') != 'SM-J701F / samsung,j7velte' or release.get('partition') != 'USERDATA':
        raise ValueError('Release metadata targets another device or partition')
    if release.get('sectors') != 23314432:
        raise ValueError('Release does not target the J701F USERDATA geometry')
    if release.get('bytes') != 11936989184:
        raise ValueError('Release byte length does not match USERDATA')
    if release.get('filesystem_uuid') != '4ce26b55-8a59-4fb7-aad4-919a5c2cefeb':
        raise ValueError('Release UUID does not match the installed BOOT handoff')
    if release.get('sd_payload', {}).get('sha256') != expected:
        raise ValueError('Release metadata disagrees with the compressed payload hash')
    if release.get('raw_image', {}).get('sha256') != raw_expected:
        raise ValueError('Release metadata disagrees with the raw partition hash')
    return expected


def serial_api():
    spec = importlib.util.spec_from_file_location('j701f_usb_console', SERIAL_MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def serial_command(api, script, required, timeout=30, *, retry=True,
                   retry_missing_marker=False, max_wait=180):
    end = time.monotonic() + (max_wait if retry else 30)
    while time.monotonic() < end:
        ports = api.find_ports()
        if len(ports) == 1:
            try:
                fd = os.open(ports[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                saved = termios.tcgetattr(fd)
                try:
                    api.serial_settings(fd)
                    return api.command_session(fd, script, required, timeout)
                finally:
                    try:
                        termios.tcsetattr(fd, termios.TCSANOW, saved)
                    except (OSError, termios.error):
                        pass
                    os.close(fd)
            except (OSError, termios.error, TimeoutError):
                if not retry:
                    raise
            except ValueError:
                if not retry_missing_marker:
                    raise
        if not retry:
            break
        time.sleep(2)
    raise TimeoutError('No working J701F USB serial shell after recovery reboot')


def recovery_job(api, mode, *, backup_id='', max_seconds=7200):
    """Start a detached recovery job; USB disconnects cannot cancel its write."""
    if mode not in ('backup', 'install'):
        raise ValueError('Unknown recovery job')
    if backup_id and not re.fullmatch(r'preinstall-userdata-[0-9]{8}-[0-9]{6}', backup_id):
        raise ValueError('Invalid backup ID')
    result = f'{RECOVERY_SD}/job-{mode}.exit'
    log = f'{RECOVERY_SD}/job-{mode}.log'
    launched = serial_command(api, f'''
test ! -d /run/recovery-state/release-job.lock || exit 1
/bin/busybox rm -f {result}
/bin/busybox setsid /bin/sh {RECOVERY_SD}/recovery-install-job.sh {mode} {backup_id} </dev/null >{log} 2>&1 &
printf 'JOB_STARTED_{mode}\\n'
''', f'JOB_STARTED_{mode}', 20, retry=False)
    print(launched)
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        try:
            status = serial_command(api, f'''
if test -f {result}; then printf 'JOB_EXIT_{mode} '; cat {result};
else printf 'JOB_RUNNING_{mode}\\n'; fi
''', f'JOB_', 20, max_wait=180)
        except (OSError, TimeoutError):
            # The job has its own session and writes progress to SD. Reconnect
            # to inspect it; never send a second destructive command here.
            time.sleep(10)
            continue
        match = re.search(rf'JOB_EXIT_{mode} ([0-9]+)', status)
        if match:
            tail = serial_command(api, f'tail -n 20 {log}\n', '', 30,
                                  retry=False)
            print(tail)
            if match.group(1) != '0':
                raise ValueError(f'Recovery {mode} job failed with exit {match.group(1)}')
            return
        time.sleep(10)
    raise TimeoutError(f'Recovery {mode} is still running or unobservable; '
                       f'check {result} and {log} on the SD before any retry')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release', type=Path, default=ROOT / 'build/release')
    parser.add_argument('--phone-ip', help='IPv4 address of the running J701F Linux system')
    parser.add_argument('--known-hosts', type=Path,
                        default=ROOT / 'build/phone-ssh-known-hosts')
    parser.add_argument('--mtp-sd', type=Path,
                        help='mounted MTP view of the phone\'s external SD card; speeds up payload staging')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--erase-userdata', action='store_true')
    parser.add_argument('--reboot', action='store_true')
    parser.add_argument('--backup-userdata', action='store_true',
                        help='save and verify a complete split USERDATA backup on the SD before erasing')
    args = parser.parse_args()
    source = args.release.resolve()
    expected = preflight(source)
    print('Target: Samsung SM-J701F / j7velte, USERDATA only (11.12 GiB).')
    print('All DATA and internal-storage contents will be destroyed.')
    print('A failed write can brick normal boot until recovery/Download Mode repair.')
    print('BOOT and RECOVERY are kept; a failed write needs rescue recovery.')
    print(f'Payload: {source / FILES[0]} ({(source / FILES[0]).stat().st_size} bytes)')
    if not (args.execute and args.erase_userdata):
        print('Dry run: pass --execute --erase-userdata to perform the installation.')
        return

    phone_ip = args.phone_ip or os.environ.get('J701F_PHONE_IP')
    if not phone_ip and (ROOT / '.phone-ip').exists():
        phone_ip = (ROOT / '.phone-ip').read_text().strip()
    if not phone_ip:
        raise ValueError('Supply --phone-ip or J701F_PHONE_IP for the running phone')
    ipaddress.IPv4Address(phone_ip)
    known_hosts = args.known_hosts.resolve()
    if not known_hosts.is_file():
        raise ValueError(f'Pinned SSH known-hosts file is missing: {known_hosts}')

    ssh_opts = ['-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
                '-o', 'StrictHostKeyChecking=yes', '-o',
                f'UserKnownHostsFile={known_hosts}']
    host = f'burak-alpine@{phone_ip}'
    def ssh(command, *, timeout=30, capture=False):
        return run(['ssh', *ssh_opts, host, command], timeout=timeout, capture=capture)

    running = ssh("uname -m; uname -r; awk '$2==\"/\" {print $1, $3, $4}' /proc/mounts",
                  capture=True)
    if 'aarch64' not in running or '7.1.' not in running or '/dev/mmcblk0p24 ext4 rw' not in running:
        raise ValueError(f'Phone is not running the expected mainline DATA system:\n{running}')
    capacity = int(ssh('cat /sys/class/power_supply/s2mu005-fuel-gauge/capacity',
                       capture=True))
    charging = ssh('cat /sys/class/power_supply/s2mu005-charger/online',
                   capture=True)
    if capacity < 50 and charging != '1':
        raise ValueError(f'Battery is only {capacity}% and no charger is online')
    print('Phone mainline system verified. Staging release on external SD.')
    sd_source = ssh("awk '$2==\"/media/sdcard\" && $3==\"vfat\" {print $1}' /proc/mounts",
                    capture=True)
    match = re.fullmatch(r'/dev/(mmcblk[0-9]+)p[0-9]+', sd_source)
    if not match:
        raise ValueError(f'External FAT SD is not mounted at /media/sdcard: {sd_source!r}')
    sd_type = ssh(f'cat /sys/class/block/{match.group(1)}/device/type', capture=True)
    if sd_type != 'SD':
        raise ValueError('Mounted storage is not an external SD card')
    sd_free_kib = int(ssh("df -k /media/sdcard | awk 'NR==2 {print $4}'", capture=True))
    required_bytes = (source / FILES[0]).stat().st_size + 256 * 1024 * 1024
    if args.backup_userdata:
        required_bytes += 11936989184
    required_kib = (required_bytes + 1023) // 1024
    if sd_free_kib < required_kib:
        raise ValueError(f'External SD has insufficient free space ({sd_free_kib} KiB)')
    ssh('test -x /home/burak-alpine/j701f/boot-swap/reboot-recovery && '
        'test -f /home/burak-alpine/j701f/boot-swap/reboot-recovery.sh')
    remote_reboot_wrapper = ssh('sha256sum /home/burak-alpine/j701f/boot-swap/reboot-recovery.sh '
                                '| cut -d" " -f1', capture=True)
    if remote_reboot_wrapper != digest(ROOT / 'system/reboot-recovery.sh'):
        raise ValueError('Phone recovery-reboot wrapper differs from this repository')
    extra = {
        'install-release-on-recovery.sh': ROOT / 'scripts/install-release-on-recovery.sh',
        'restore-userdata-on-recovery.sh': ROOT / 'scripts/restore-userdata-on-recovery.sh',
        'recovery-install-job.sh': ROOT / 'scripts/recovery-install-job.sh',
    }
    names = (*FILES, *extra)
    mtp_mount = None
    if args.mtp_sd:
        mtp_sd = args.mtp_sd.resolve()
        if not mtp_sd.is_dir() or not os.path.ismount(mtp_sd.parent):
            raise ValueError(f'--mtp-sd is not inside a mounted MTP filesystem: {mtp_sd}')
        mtp_mount = mtp_sd.parent
        mtp_release = mtp_sd / 'j701f-release'
        mtp_release.mkdir(exist_ok=True)
        for name in names:
            path = source / name if name in FILES else extra[name]
            print(f'Copying {name} to the external SD through USB MTP.')
            shutil.copyfile(path, mtp_release / name)
    else:
        ssh(f'mkdir -p {STAGE}')
        for name in FILES:
            run(['scp', *ssh_opts, '-q', str(source / name), f'{host}:{STAGE}/{name}'],
                timeout=1800)
        for name, path in extra.items():
            run(['scp', *ssh_opts, '-q', str(path), f'{host}:{STAGE}/{name}'], timeout=60)
        copies = ' && '.join(f'sudo -n cp {STAGE}/{name} {SD}/{name}' for name in names)
        ssh(f'sudo -n mkdir -p {SD} && {copies} && sync', timeout=1800)
    # Validate through the phone's physical SD mount, independent of which
    # transport (MTP or SSH) copied the files.
    hash_output = ssh('sudo -n sha256sum ' + ' '.join(f'{SD}/{name}' for name in names),
                      timeout=1800, capture=True)
    remote_hashes = {Path(path).name: value for value, path in
                     (line.split(maxsplit=1) for line in hash_output.splitlines())}
    for name in names:
        local_path = source / name if name in FILES else extra[name]
        wanted = expected if name == 'userdata.ext4.gz' else digest(local_path)
        if remote_hashes.get(name) != wanted:
            raise ValueError(f'SD copy of {name} has a checksum mismatch; refusing reboot')
    if mtp_mount:
        unmount = shutil.which('fusermount') or shutil.which('fusermount3')
        if unmount:
            run([unmount, '-u', str(mtp_mount)], timeout=30)
            print('Host MTP mount released before the phone changes USB mode.')
    print('Every SD release file verified. Rebooting into RAM recovery.')
    ssh("sudo -n sh -c '(sleep 1; sh /home/burak-alpine/j701f/boot-swap/reboot-recovery.sh --execute) >/dev/null 2>&1 &'", timeout=15)
    api = serial_api()
    ready = serial_command(api, '''
test -d /run/recovery-state && test -x /recovery/scripts/storage.sh || exit 1
: > /run/recovery-state/stay
sh /recovery/scripts/storage.sh mount-sd
printf 'RECOVERY_READY\\n'
''', 'RECOVERY_READY', 25, retry_missing_marker=True)
    print(ready)
    # recovery-main starts a one-shot Wi-Fi/MTP worker eight seconds after
    # entry. Wait for MTP startup to begin and both helper scripts to finish;
    # otherwise that worker could remount the old DATA after our unmount.
    time.sleep(120)
    settled = serial_command(api, '''
n=0
while :; do
    busy=no
    for p in /proc/[0-9]*/cmdline; do
        cmd=$(/bin/busybox tr '\\000' ' ' < "$p" 2>/dev/null || :)
        case "$cmd" in
            *'/recovery/scripts/wifi.sh up'*|*'/recovery/scripts/mtp.sh up'*) busy=yes ;;
        esac
    done
    if test -f /run/recovery-mtp.log && test "$busy" = no; then break; fi
    n=$((n + 1)); test "$n" -lt 90 || exit 1
    sleep 2
done
printf 'RECOVERY_STARTUP_SETTLED\\n'
''', 'RECOVERY_STARTUP_SETTLED', 210, retry_missing_marker=True,
                             max_wait=300)
    print(settled)
    print('Closing recovery Wi-Fi/MTP and unmounting old DATA before installation.')
    prepared = serial_command(api, '''
sh /recovery/scripts/mtp.sh down >/dev/null 2>&1 || :
sh /recovery/scripts/wifi.sh down >/dev/null 2>&1 || :
if grep -q ' /mnt/root ' /proc/mounts; then umount /mnt/root || exit 1; fi
sh /mnt/sd/j701f-release/install-release-on-recovery.sh --source /mnt/sd/j701f-release --erase-userdata
''', 'DRY RUN ONLY', 900)
    print(prepared)
    if args.backup_userdata:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        backup_id = f'preinstall-userdata-{stamp}'
        print('Saving a complete USERDATA backup as 1 GB SD chunks before the wipe.')
        recovery_job(api, 'backup', backup_id=backup_id)
    print('Writing and reading back USERDATA; USB must stay connected.')
    recovery_job(api, 'install')
    status = serial_command(api, f'cat {RECOVERY_SD}/install.status\n', 'PASS', 20,
                            retry=False)
    print(f'Recovery install status: {status}')
    if args.reboot:
        try:
            serial_command(api, ": > /run/recovery-state/reboot\nprintf 'REBOOT_REQUESTED\\n'\n",
                           'REBOOT_REQUESTED', 20)
        except (OSError, TimeoutError):
            pass  # The recovery intentionally disconnects USB while rebooting.
        print('Recovery requested normal system reboot; checking USB shell.')
        booted = serial_command(api, '''
test "$(cat /etc/j701f-system-version 2>/dev/null)" = BURAK_ALPINE_0_1 || exit 1
uname -r | grep -q '^7\\.1\\.' || exit 1
awk '$2=="/" && $1=="/dev/mmcblk0p24" && $3=="ext4" {found=1} END {exit !found}' /proc/mounts || exit 1
printf 'BOOTED_RELEASE\\n'
''', 'BOOTED_RELEASE', 20, retry_missing_marker=True, max_wait=900)
        print(booted)
        print('Installed Alpine root booted from USERDATA.')
    else:
        print('Release installed. Recovery is held open for inspection.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, TimeoutError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'System install stopped: {exc}')
