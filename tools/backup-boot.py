#!/usr/bin/env python3
"""Read the current 32 MiB BOOT partition over recovery USB; never write phone storage."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import termios

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = importlib.util.spec_from_file_location('console', ROOT / 'tools/usb-console.py')
    console = importlib.util.module_from_spec(spec); spec.loader.exec_module(console)
    ports = console.find_ports()
    if len(ports) != 1:
        raise ValueError('Expected one recovery USB shell; close other serial terminals')
    destination = ROOT / 'build/backups'
    destination.mkdir(exist_ok=True, parents=True)
    if (destination / 'boot-original.img').exists():
        raise ValueError('BOOT backup already exists; preserve it instead of silently overwriting')
    temporary = destination / 'boot-original.img.part'
    remote = '/dev/j701f-boot-backup-' + secrets.token_hex(10)
    fd = os.open(ports[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    saved = termios.tcgetattr(fd)
    try:
        console.serial_settings(fd)
        output = console.command_session(fd, f'''set -e
b=/sys/class/block/mmcblk0p10
/bin/busybox grep -qx 'PARTNAME=BOOT' "$b/uevent"
test "$(cat "$b/size")" = 65536
test "$(cat "$b/dev")" = 259:2
test "$(cat /sys/class/block/mmcblk0/device/type)" = MMC
/bin/busybox mkdir -m 700 {remote}
/bin/busybox mknod {remote}/boot b 259 2
printf 'BOOT_SHA256='
/bin/busybox sha256sum {remote}/boot
printf 'MMC_CID_SHA256='
/bin/busybox sha256sum /sys/class/block/mmcblk0/device/cid
printf 'BACKUP_READY\\n'
''', 'BACKUP_READY')
        digest = output.split('BOOT_SHA256=', 1)[1].split()[0]
        cid = output.split('MMC_CID_SHA256=', 1)[1].split()[0]
        with temporary.open('wb') as archive:
            for index in range(512):
                script = f'''set -e
/bin/busybox dd if={remote}/boot of={remote}/chunk bs=65536 skip={index} count=1 2>/dev/null
test "$(/bin/busybox wc -c < {remote}/chunk)" = 65536
printf 'BOOT_CHUNK_BEGIN\\n'
/bin/busybox base64 {remote}/chunk
printf 'BOOT_CHUNK_END\\n'
'''
                response = console.command_session(fd, script, 'BOOT_CHUNK_END')
                encoded = response.split('BOOT_CHUNK_BEGIN\n', 1)[1].split('BOOT_CHUNK_END', 1)[0]
                chunk = base64.b64decode(encoded, validate=False)
                if len(chunk) != 65536:
                    raise ValueError('Incomplete BOOT backup chunk')
                archive.write(chunk)
                if index % 64 == 0 or index == 511:
                    print(f'BOOT backup: {(index+1)*65536}/{32*1024*1024} bytes', flush=True)
        actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError('BOOT backup differs from the phone checksum')
        temporary.replace(destination / 'boot-original.img')
        (destination / 'boot-original.json').write_text(json.dumps(dict(
            partition='BOOT', bytes=32*1024*1024, sha256=digest, mmc_cid_sha256=cid,
            source='live recovery USB read; device identity and size checked',
            userdata_backed_up=False), indent=2) + '\n')
        print('Verified live BOOT backup:', destination / 'boot-original.img')
    finally:
        try:
            console.command_session(fd, f'/bin/busybox rm -rf {remote}\nprintf "BACKUP_RAM_CLEANED\\n"', 'BACKUP_RAM_CLEANED', timeout=10)
        finally:
            try: termios.tcsetattr(fd, termios.TCSANOW, saved)
            except (OSError, termios.error): pass
            os.close(fd)


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, KeyboardInterrupt) as error:
        raise SystemExit(f'BOOT backup: {error}')
