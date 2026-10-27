#!/usr/bin/env python3
"""Build the TWRP/OrangeFox ZIP that installs a J701F release into USERDATA.

Written by Claude 2026-10-27. The ZIP holds update-binary, installer.sh and the
project's pinned static AArch64 BusyBox. With --embed the release files go into
the ZIP as well (the payload must stay below 4 GiB: recovery unzip tools have no
ZIP64); without it, the release is read from j701f-release/ next to the ZIP.

  tools/build-recovery-zip.py OUT.zip [--embed RELEASE_DIR]
"""
import argparse
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'recovery/installer'
BUSYBOX = ROOT / 'ramdisk/bin/busybox'
BUSYBOX_SHA256 = 'ebd2865edcab0b590c7d0edb70d3e782cbfb541e518a390ced3a3e186509bc7f'
RELEASE_FILES = ('userdata.ext4.gz', 'userdata.ext4.gz.sha256', 'userdata.ext4.sha256', 'release.json')
STAMP = (2026, 1, 1, 0, 0, 0)


def add(z, name, data, mode, compress=zipfile.ZIP_DEFLATED):
    info = zipfile.ZipInfo(name, STAMP)
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = compress
    z.writestr(info, data)


def add_file(z, name, path, mode):
    info = zipfile.ZipInfo(name, STAMP)
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = zipfile.ZIP_STORED
    info.file_size = path.stat().st_size
    with path.open('rb') as src, z.open(info, 'w', force_zip64=False) as dst:
        while chunk := src.read(1 << 20):
            dst.write(chunk)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('output', type=Path)
    parser.add_argument('--embed', type=Path, metavar='RELEASE_DIR')
    args = parser.parse_args()

    busybox = BUSYBOX.read_bytes()
    if hashlib.sha256(busybox).hexdigest() != BUSYBOX_SHA256:
        sys.exit(f'{BUSYBOX} is not the pinned BusyBox; run make busybox')
    if args.embed:
        missing = [f for f in RELEASE_FILES if not (args.embed / f).is_file()]
        if missing:
            sys.exit('release is missing ' + ', '.join(missing))
        if (args.embed / 'userdata.ext4.gz').stat().st_size >= 0xFFFFFFFF:
            sys.exit('payload is 4 GiB or larger: ship it as j701f-release/ next to the ZIP instead')

    tmp = args.output.with_name(args.output.name + '.tmp')
    with zipfile.ZipFile(tmp, 'w', allowZip64=False) as z:
        add(z, 'META-INF/com/google/android/update-binary', (SRC / 'update-binary').read_bytes(), 0o755)
        add(z, 'META-INF/com/google/android/updater-script', (SRC / 'updater-script').read_bytes(), 0o644)
        add(z, 'j701f/installer.sh', (SRC / 'installer.sh').read_bytes(), 0o755)
        add(z, 'j701f/busybox', busybox, 0o755)
        if args.embed:
            for name in RELEASE_FILES[1:]:
                add(z, name, (args.embed / name).read_bytes(), 0o644)
            add_file(z, 'userdata.ext4.gz', args.embed / 'userdata.ext4.gz', 0o644)
    tmp.replace(args.output)
    h = hashlib.sha256()
    with args.output.open('rb') as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    digest = h.hexdigest()
    args.output.with_name(args.output.name + '.sha256').write_text(f'{digest}  {args.output.name}\n')
    print(f'{args.output} ({args.output.stat().st_size} bytes) sha256 {digest}')


if __name__ == '__main__':
    main()
