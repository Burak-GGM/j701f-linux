#!/usr/bin/env python3
"""Check the diagnostic binary/scripts in phone RAM without running /init or USB setup."""
import argparse
import gzip
import io
import ipaddress
import json
from pathlib import Path
import secrets
import stat
import subprocess
import tarfile
import tempfile

import recovery
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/j701f-diagnostic'


def validate(phone):
    ipaddress.IPv4Address(phone)
    spec = importlib.util.spec_from_file_location('diagnostic_initramfs', ROOT / 'tools/build-mainline-initramfs.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    package_report = json.loads((OUT / 'initramfs-report.json').read_text())
    package = (OUT / 'initramfs.cpio.gz').read_bytes()
    recovery.require(recovery.sha(package) == package_report['sha256'], 'Initramfs checksum differs')
    options = ['-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-i', str(Path.home() / '.ssh/id_ed25519'),
               '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(ROOT / 'build/phone-ssh-known-hosts'),
               '-o', 'ConnectTimeout=5']
    host = 'burak-alpine@' + phone
    remote = '/tmp/j701f-diag-verify-' + secrets.token_hex(6)
    with tempfile.TemporaryDirectory(prefix='j701f-diag-validation-') as work:
        payload = Path(work) / 'userspace.tar.gz'
        with tarfile.open(payload, 'w:gz') as tar:
            for name, values, data in recovery.cpio_entries(gzip.decompress(package)):
                if stat.S_ISCHR(values[1]):
                    continue
                entry = tarfile.TarInfo(name); entry.mode = stat.S_IMODE(values[1])
                if stat.S_ISDIR(values[1]): entry.type = tarfile.DIRTYPE
                elif stat.S_ISLNK(values[1]): entry.type = tarfile.SYMTYPE; entry.linkname = data.decode()
                else: entry.size = len(data)
                tar.addfile(entry, io.BytesIO(data) if entry.isfile() else None)
        subprocess.run(['scp', *options, str(payload), host + ':' + remote + '.tar.gz'], check=True, timeout=30)
        script = '''set -eu
trial=$1
cleanup() { rm -rf "$trial"; rm -f "$trial.tar.gz"; }
trap cleanup EXIT
mkdir "$trial"
tar -xzf "$trial.tar.gz" -C "$trial"
actual=$("$trial/bin/busybox" sha256sum "$trial/bin/busybox")
[ "${actual%% *}" = BINARY_SHA256 ]
"$trial/bin/busybox" --list > "$trial/applets"
for applet in APPLET_LIST; do
    grep -qx "$applet" "$trial/applets" || { echo "Missing applet: $applet"; exit 1; }
done
for script in init bin/usb-configfs bin/usb-shell; do
    "$trial/bin/busybox" sh -n "$trial/$script"
done
"$trial/bin/busybox" uname -a
printf 'DIAGNOSTIC_STATIC_BUSYBOX_AND_SHELL_SYNTAX_PASS\\n'
cleanup
trap - EXIT
[ ! -e "$trial" ] && [ ! -e "$trial.tar.gz" ]
printf 'DIAGNOSTIC_RAM_CLEANUP_OK\\n'
'''.replace('BINARY_SHA256', package_report['busybox']['binary_sha256']).replace('APPLET_LIST', ' '.join(module.APPLETS))
        result = subprocess.run(['ssh', *options, host, 'sh -s -- ' + remote],
                                input=script, text=True, capture_output=True, timeout=90)
        (OUT / 'phone-userspace-validation.txt').write_text(result.stdout + result.stderr)
        result.check_returncode()
        recovery.require('DIAGNOSTIC_RAM_CLEANUP_OK' in result.stdout, 'RAM cleanup was not confirmed')
        recovery.json_write(OUT / 'userspace-validation-report.json', dict(
            status='passed', initramfs_sha256=package_report['sha256'],
            static_busybox_executed=True, required_applets_verified=True,
            shell_syntax_verified=True, temporary_ram_files_cleaned=True,
            mainline_kernel_boot_tested=False, usb_configfs_tested=False,
            phone_persistent_files_modified=False, partitions_modified=False))
        print(result.stdout, end='')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phone', required=True, help='Reachable IPv4 address with the project-pinned SSH key')
    validate(parser.parse_args().phone)
