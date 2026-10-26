#!/usr/bin/env python3
"""Package a static USB/configfs diagnostic initramfs. No phone operations."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import stat
import struct
import subprocess

import recovery

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/j701f-diagnostic'
SOURCE = ROOT / 'kernel/diagnostic'
APPLETS = 'blkid umount cp switch_root ip sync tee printf tail sh mount mkdir cat uname sleep setsid getty ln dmesg ls grep hexdump ps stty chmod readlink head reboot'.split()


def build(out=OUT, helpers=(), extras=(), firmware=(), recovery_scripts=(), recovery_tools=()):
    out = out.resolve()
    recovery.require(out.is_relative_to(ROOT / "build/kernel"), "Output must be under build/kernel")
    binary = ROOT / 'ramdisk/bin/busybox'
    provenance = json.loads((ROOT / 'tools/busybox-provenance.json').read_text())
    bb = binary.read_bytes()
    recovery.require(recovery.sha(bb) == provenance['binary_sha256'], 'BusyBox provenance mismatch')
    recovery.require(bb[:5] == b'\x7fELF\x02' and struct.unpack_from('<H', bb, 18)[0] == 183,
                     'BusyBox is not AArch64')
    items = {}
    for directory in ('bin', 'sbin', 'dev', 'dev/pts', 'proc', 'sys', 'run', 'tmp', 'root', 'etc'):
        mode = 0o1777 if directory == 'tmp' else 0o700 if directory == 'root' else 0o755
        items[directory] = (stat.S_IFDIR | mode, b'', (0, 0))
    items['dev/console'] = (stat.S_IFCHR | 0o600, b'', (5, 1))
    items['dev/null'] = (stat.S_IFCHR | 0o666, b'', (1, 3))
    items['bin/busybox'] = (stat.S_IFREG | 0o755, bb, (0, 0))
    for applet in APPLETS:
        items['bin/' + applet] = (stat.S_IFLNK | 0o777, b'busybox', (0, 0))
    for name in ('init', 'usb-configfs', 'usb-shell', 'console-diagnostics', 'muic-usb-path', 'storage-report'):
        path = SOURCE / name
        subprocess.run(['sh', '-n', str(path)], check=True)
        items[name if name == 'init' else 'bin/' + name] = (stat.S_IFREG | 0o755, path.read_bytes(), (0, 0))
    for helper in helpers:
        data = helper.read_bytes()
        recovery.require(data[:5] == b'\x7fELF\x02' and struct.unpack_from('<H', data, 18)[0] == 183,
                         'Helper is not AArch64')
        items['bin/' + helper.name] = (stat.S_IFREG | 0o755, data, (0, 0))
    # Claude 2026-10-08: firmware a built-in driver needs before the real root exists.
    for source, name in firmware:
        for directory in ('lib', 'lib/firmware', 'lib/firmware/' + str(Path(name).parent)):
            items.setdefault(directory.rstrip('/.'), (stat.S_IFDIR | 0o755, b'', (0, 0)))
        items['lib/firmware/' + name] = (stat.S_IFREG | 0o644, source.read_bytes(), (0, 0))
    # Optional later-stage scripts: present only when the caller asks for them.
    for name in extras:
        path = SOURCE / name
        subprocess.run(['sh', '-n', str(path)], check=True)
        items['bin/' + name] = (stat.S_IFREG | 0o755, path.read_bytes(), (0, 0))
    # Claude 2026-10-10: helper scripts of the recovery UI (recovery/scripts/*.sh).
    for path in recovery_scripts:
        subprocess.run(['sh', '-n', str(path)], check=True)
        for directory in ('recovery', 'recovery/scripts'):
            items.setdefault(directory, (stat.S_IFDIR | 0o755, b'', (0, 0)))
        items['recovery/scripts/' + path.name] = (stat.S_IFREG | 0o755, path.read_bytes(), (0, 0))
    # Claude 2026-10-10: dynamically linked tools for the recovery (e2fsck with its
    # libraries and the musl loader, copied from the phone's Alpine). They live in
    # /recovery/lib; each program gets a /bin wrapper that starts it through the loader.
    for path in recovery_tools:
        data = path.read_bytes()
        recovery.require(data[:5] == b'\x7fELF\x02' and struct.unpack_from('<H', data, 18)[0] == 183,
                         'Recovery tool is not AArch64')
        for directory in ('recovery', 'recovery/lib'):
            items.setdefault(directory, (stat.S_IFDIR | 0o755, b'', (0, 0)))
        items['recovery/lib/' + path.name] = (stat.S_IFREG | 0o755, data, (0, 0))
        if '.so' not in path.name:
            wrapper = ('#!/bin/sh\nexec /recovery/lib/ld-musl-aarch64.so.1 --library-path /recovery/lib '
                       '/recovery/lib/%s "$@"\n' % path.name).encode()
            items['bin/' + path.name] = (stat.S_IFREG | 0o755, wrapper, (0, 0))
    ids = (ROOT / 'ramdisk/etc/usb-baseline.conf').read_bytes()
    recovery.require(b'USB_VENDOR=04e8' in ids and b'USB_PRODUCT=6860' in ids, 'USB baseline differs')
    items['etc/usb-baseline.conf'] = (stat.S_IFREG | 0o644, ids, (0, 0))
    raw = b''.join(recovery.cpio_record(name, data, mode, index + 1, dev)
                   for index, (name, (mode, data, dev)) in enumerate(items.items()))
    raw += recovery.cpio_record('TRAILER!!!')
    raw += bytes(recovery.align(len(raw), 512) - len(raw))
    compressed = gzip.compress(raw, mtime=0)
    out.mkdir(parents=True, exist_ok=True)
    recovery.write(out / 'initramfs.cpio.gz', compressed)
    recovered = {name: (values, data) for name, values, data in recovery.cpio_entries(raw)}
    recovery.require(recovered['init'][1] == (SOURCE / 'init').read_bytes(), 'CPIO round trip mismatch')
    recovery.json_write(out / 'initramfs-report.json', dict(
        status='packaged', phone_modified=False, hardware_boot_tested=False, flash_ready=False,
        bytes=len(compressed), sha256=recovery.sha(compressed), entries=len(recovered),
        busybox=provenance,
        inputs={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in [SOURCE / 'init', SOURCE / 'usb-configfs', SOURCE / 'usb-shell', SOURCE / 'console-diagnostics',
                          SOURCE / 'muic-usb-path', SOURCE / 'storage-report',
                          ROOT / 'ramdisk/etc/usb-baseline.conf', *helpers,
                          *[SOURCE / name for name in extras], *[f for f, _ in firmware], *recovery_scripts, *recovery_tools]},
        limits=['Shell syntax and CPIO round trip verified; not a mainline hardware boot.',
                'Existing vendor kernel has no configfs gadget interface for an ACM test.',
                'Unauthenticated USB root console for local development.']))
    print('PASS: diagnostic initramfs syntax/CPIO checks. No phone or partition changes.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--helper", type=Path, action='append', default=[],
                        help="Extra static AArch64 binary for /bin (under the repository)")
    parser.add_argument("--extra", action='append', default=[],
                        choices=['alpine-handoff', 'alpine-usb-debug', 'recovery-main'],
                        help="Optional kernel/diagnostic script for /bin (Alpine handoff stage)")
    parser.add_argument("--recovery-scripts", type=Path,
                        help='directory whose *.sh files are installed as /recovery/scripts/ (recovery image)')
    parser.add_argument("--recovery-tools", type=Path,
                        help='directory of AArch64 programs and libraries for /recovery/lib (recovery image)')
    parser.add_argument("--firmware", action='append', default=[], metavar='SRC:NAME',
                        help="File to install as /lib/firmware/NAME (e.g. brcm/brcmfmac43430-sdio.bin)")
    args = parser.parse_args()
    firmware = []
    for item in args.firmware:
        source, _, name = item.partition(':')
        recovery.require(name and not name.startswith('/') and '..' not in name, 'Bad firmware destination')
        firmware.append((Path(source).resolve(), name))
    build(args.output_dir, [h.resolve() for h in args.helper], args.extra, firmware,
          sorted(args.recovery_scripts.resolve().glob('*.sh')) if args.recovery_scripts else (),
          sorted(p for p in args.recovery_tools.resolve().iterdir() if p.is_file()) if args.recovery_tools else ())
