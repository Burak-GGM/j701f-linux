#!/usr/bin/env python3
"""Prepare or apply a verified BOOT-header-only zswap trial; never write DATA."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import re
import termios
import recovery

ROOT = recovery.ROOT
OUT = ROOT / 'build/boot-cpu-trial'
CAPACITY = 32 * 1024 * 1024
CMDLINE = b'zswap.enabled=0'


def patch_boot(backup, working_image, capacity=CAPACITY):
    recovery.require(len(backup) == capacity, 'BOOT backup capacity mismatch')
    recovery.require(backup[:len(working_image)] == working_image,
                     'Live BOOT differs from the known working image')
    image = recovery.Image(working_image)
    recovery.require(image.page == 2048, 'Unexpected BOOT page size')
    recovery.require(not any(image.header[64:576]) and not any(image.header[608:1632]),
                     'Existing command line needs explicit review')
    changed = bytearray(backup)
    changed[64:576] = CMDLINE + bytes(512 - len(CMDLINE))
    changed = bytes(changed)
    trial = recovery.Image(changed[:len(working_image)])
    recovery.require(trial.parts == image.parts, 'BOOT payload changed')
    recovery.require(changed[:64] == backup[:64] and changed[576:] == backup[576:],
                     'Bytes outside primary command line changed')
    return changed


def prepare():
    backup_path = ROOT / 'build/backups/boot-before-cpu-trial.img'
    backup = backup_path.read_bytes()
    report = (ROOT / 'build/phone-cpu-boot-backup.txt').read_text()
    live = re.search(r'LIVE_BOOT_SHA256=([0-9a-f]{64})', report).group(1)
    saved = re.search(r'BACKUP_BOOT_SHA256=([0-9a-f]{64})', report).group(1)
    recovery.require(recovery.sha(backup) == live == saved, 'Live BOOT backup checksum mismatch')
    working = (ROOT / 'build/system/boot.img').read_bytes()
    info = json.loads((ROOT / 'build/system/manifest.json').read_text())
    recovery.require(recovery.sha(working) == info['files']['boot.img']['sha256'],
                     'Working image checksum mismatch')
    trial = patch_boot(backup, working)
    OUT.mkdir(parents=True, exist_ok=True)
    recovery.write(OUT / 'boot.img', trial[:len(working)])
    recovery.write(OUT / 'header.bin', trial[:2048])
    builder_spec = importlib.util.spec_from_file_location('cpu_builder', ROOT / 'tools/build-system.py')
    builder = importlib.util.module_from_spec(builder_spec); builder_spec.loader.exec_module(builder)
    builder.tar_output(OUT / 'boot.tar', [('boot.img', OUT / 'boot.img')])
    builder.tar_output(OUT / 'BOOT-working-restore.tar', [('boot.img', backup_path)])
    manifest = dict(target='BOOT', changed_bytes='primary cmdline field only',
                    cmdline=CMDLINE.decode(), mmc_cid_sha256=info['mmc_cid_sha256'],
                    before_partition_sha256=live, after_partition_sha256=recovery.sha(trial),
                    header_sha256=recovery.sha(trial[:2048]),
                    image_sha256=recovery.sha(trial[:len(working)]),
                    recovery_and_data_unchanged=True)
    recovery.json_write(OUT / 'manifest.json', manifest)
    print('PASS: live 32 MiB BOOT backup; existing working image; kernel, DTBH, ramdisk and all non-cmdline bytes preserved.', flush=True)
    return manifest


def apply(manifest):
    spec = importlib.util.spec_from_file_location('cpu_usb', ROOT / 'tools/usb-console.py')
    usb = importlib.util.module_from_spec(spec); spec.loader.exec_module(usb)
    ports = usb.find_ports()
    recovery.require(len(ports) == 1, 'Expected one phone USB shell')
    payload = base64.encodebytes((OUT / 'header.bin').read_bytes()).decode()
    script = f'''set -e
test "$(cat /etc/j701f-system-version)" = BURAK_ALPINE_0_1
b=/sys/class/block/mmcblk0p10
grep -qx 'PARTNAME=BOOT' "$b/uevent"
test "$(cat "$b/size")" = 65536
test "$(cat "$b/dev")" = 259:2
test "$(cat /sys/class/block/mmcblk0/device/type)" = MMC
test "$(cat /sys/class/block/mmcblk0/removable)" = 0
x=$(sha256sum /sys/class/block/mmcblk0/device/cid)
test "${{x%% *}}" = {manifest['mmc_cid_sha256']}
node=/dev/j701f-cpu-trial/boot
test -b "$node"
test "$(stat -c '%t:%T' "$node")" = 103:2
backup=/var/lib/j701f/boot-cpu-trial/boot-before.img
x=$(sha256sum "$backup"); test "${{x%% *}}" = {manifest['before_partition_sha256']}
x=$(sha256sum "$node"); test "${{x%% *}}" = {manifest['before_partition_sha256']}
umask 077
base64 -d > /tmp/j701f-cpu-header.bin <<'CPU_HEADER'
{payload}CPU_HEADER
test "$(wc -c < /tmp/j701f-cpu-header.bin)" = 2048
x=$(sha256sum /tmp/j701f-cpu-header.bin); test "${{x%% *}}" = {manifest['header_sha256']}
restore_before() {{
    dd if="$backup" of="$node" bs=2048 count=1 conv=notrunc 2>/dev/null
    sync
    x=$(sha256sum "$node")
    if [ "${{x%% *}}" = {manifest['before_partition_sha256']} ]; then
        printf 'CPU_TRIAL_ROLLBACK_VERIFIED\\n'
    else
        printf 'CPU_TRIAL_ROLLBACK_FAILED_USE_SAVED_ODIN_RESTORE\\n'
    fi
}}
trap restore_before EXIT
dd if=/tmp/j701f-cpu-header.bin of="$node" bs=2048 count=1 conv=notrunc 2>/dev/null
sync
x=$(sha256sum "$node"); test "${{x%% *}}" = {manifest['after_partition_sha256']}
trap - EXIT
rm -f /tmp/j701f-cpu-header.bin
printf 'CPU_TRIAL_BOOT_READBACK_VERIFIED\\n'
'''
    fd = os.open(ports[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    saved = termios.tcgetattr(fd)
    try:
        usb.serial_settings(fd)
        output = usb.command_session(fd, script, 'CPU_TRIAL_BOOT_READBACK_VERIFIED', timeout=45)
        (OUT / 'phone-write-check.txt').write_text(output + '\n')
        print(output)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, saved); os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Apply the verified 2048-byte header over USB')
    args = parser.parse_args()
    manifest = prepare()
    if args.execute:
        apply(manifest)
    else:
        print('Prepared separately in build/boot-cpu-trial. No phone writes. No reboot.')


if __name__ == '__main__':
    main()
