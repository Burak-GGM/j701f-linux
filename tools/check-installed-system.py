#!/usr/bin/env python3
"""Inspect Alpine DATA over the recovery USB shell, read-only without journal replay."""
import importlib.util
import os
import json
from pathlib import Path
import secrets
import shlex
import termios

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def main():
    builder = module('builder', 'build-system.py')
    builder.verify_bundle()
    console = module('console', 'usb-console.py')
    ports = console.find_ports()
    if len(ports) != 1:
        raise ValueError('Expected one recovery USB shell; close other serial terminals')
    # Hashes are extracted from the validated host ext4 image during packaging.
    # This verifies startup files, not every byte or every installed package.
    expected = json.loads((builder.OUT / 'manifest.json').read_text())['startup_file_sha256']
    nonce = secrets.token_hex(8)
    node_dir = '/dev/j701f-readback-' + nonce
    root = '/tmp/j701f-readback-' + nonce
    cid = builder.live_boot_template()[1]['mmc_cid_sha256']
    script = f'''set -e
bb=/bin/busybox
node_dir={node_dir}
root={root}
mounted=no
cleanup() {{
    if [ "$mounted" = yes ]; then
        $bb umount "$root" || {{ printf 'READBACK_UNMOUNT_FAILED\\n'; return 1; }}
    fi
    $bb rmdir "$root" 2>/dev/null || true
    $bb rm -rf "$node_dir"
    printf 'READBACK_RAM_CLEANUP_OK\\n'
}}
trap cleanup EXIT
/bin/boot-manager inspect
actual=$($bb sha256sum /sys/class/block/mmcblk0/device/cid)
[ "${{actual%% *}}" = {cid} ] || {{ printf 'MMC_IDENTITY_DIFFERS\\n'; exit 1; }}
entry=
for candidate in /sys/class/block/*; do
    [ -f "$candidate/partition" ] || continue
    $bb grep -qx 'PARTNAME=USERDATA' "$candidate/uevent" || continue
    [ -z "$entry" ] || exit 1
    entry=$candidate
done
[ -n "$entry" ]
numbers=$(cat "$entry/dev")
$bb mkdir -m 700 "$node_dir" "$root"
$bb mknod "$node_dir/data" b "${{numbers%:*}}" "${{numbers#*:}}"
info=$($bb blkid "$node_dir/data" || true)
printf '%s\\n' "$info"
case "$info" in *'UUID="{builder.UUID}"'*) ;; *) printf 'DATA_UUID_MISMATCH\\n'; exit 1 ;; esac
case "$info" in *'TYPE="ext4"'*) ;; *) printf 'DATA_TYPE_MISMATCH\\n'; exit 1 ;; esac
$bb mount -t ext4 -o ro,noload,nosuid,nodev,noexec "$node_dir/data" "$root"
mounted=yes
/bin/boot-manager validate-root "$root"
'''
    for name, digest in expected.items():
        script += f'''actual=$($bb sha256sum "$root/"{shlex.quote(name)})
[ "${{actual%% *}}" = {digest} ] || {{ printf '%s\\n' {shlex.quote('STARTUP_FILE_MISMATCH: ' + name)}; exit 1; }}
printf '%s\\n' {shlex.quote('PASS: ' + name)}
'''
    script += '''cleanup
mounted=no
trap - EXIT
printf 'INSTALLED_ALPINE_STARTUP_FILES_VERIFIED\\n'
printf 'READBACK_RAM_CLEANUP_OK\\n'
'''
    fd = os.open(ports[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    saved = termios.tcgetattr(fd)
    try:
        console.serial_settings(fd)
        try:
            output = console.command_session(fd, script, 'INSTALLED_ALPINE_STARTUP_FILES_VERIFIED', timeout=60)
            if 'READBACK_RAM_CLEANUP_OK' not in output:
                raise ValueError('Read-back cleanup evidence is missing')
        except (ValueError, OSError) as error:
            (ROOT / 'build/phone-installed-system-check-failed.txt').write_text(str(error) + '\n')
            raise
        (ROOT / 'build/phone-installed-system-check.txt').write_text(output + '\n')
        print(output)
        print('Read-only DATA UUID/root/startup-file check passed; this is not full-partition read-back or a normal-boot test.')
    finally:
        try: termios.tcsetattr(fd, termios.TCSANOW, saved)
        except (OSError, termios.error): pass
        os.close(fd)


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, termios.error) as error:
        raise SystemExit(f'Installed system check: {error}')
