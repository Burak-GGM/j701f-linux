#!/usr/bin/env python3
"""Strict, dependency-free tooling for the inspected j7velte OrangeFox image.

Not a general mkbootimg replacement. No device I/O, mounts or privilege required.
"""
import argparse
import gzip
import hashlib
import io
import json
import lzma
import re
from pathlib import Path
import stat
import struct
import tarfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA256 = '5bbcb385a5b007a037713b169e69255534fbfb3527fa9ced63c61fe08b1eb68e'
APK_NAME = 'busybox-static-1.36.1-r31.apk'
APK_URL = 'https://dl-cdn.alpinelinux.org/alpine/v3.20/main/aarch64/' + APK_NAME
APK_SHA256 = '1d8e7a7fc2ed69bdb8eb7be9d962489c21a0f75b72d8a325437c8a09d4cfac70'
ORIGINAL = ROOT / 'original/OrangeFox-recovery.img'
APPLETS = 'sh ash mount mkdir mknod chmod cat uname sleep setsid getty stty dmesg ls readlink ps head hexdump grep sed awk find env echo printf test stat wc clear'.split()
EXTRA_SCRIPTS = ('bin/usb-shell', 'bin/usb-debug', 'bin/display-status', 'bin/boot-manager')
EXTRA_FILES = (*EXTRA_SCRIPTS, 'bin/fb-heartbeat', 'bin/ondevice-terminal', 'etc/usb-baseline.conf')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, page):
    return (value + page - 1) // page * page


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_bytes(data)
    temp.replace(path)


def json_write(path, value):
    write(path, (json.dumps(value, indent=2) + '\n').encode())


class Image:
    def __init__(self, data):
        require(len(data) >= 1632 and data[:8] == b'ANDROID!', 'Not an Android boot image')
        self.data = data
        self.fields = dict(zip(('kernel_size', 'kernel_addr', 'ramdisk_size', 'ramdisk_addr',
                                'second_size', 'second_addr', 'tags_addr', 'page_size',
                                'dt_size', 'os_version_raw'), struct.unpack_from('<10I', data, 8)))
        self.page = self.fields['page_size']
        require(self.page in (2048, 4096, 8192, 16384), 'Unsupported page size')
        require(self.fields['dt_size'] > 4, 'Requires legacy dt_size header; v1-v4 unsupported')
        self.header = data[:self.page]
        self.parts, self.offsets, self.padding = {}, {}, {}
        pos = self.page
        for name in ('kernel', 'ramdisk', 'second', 'dt'):
            size = self.fields[name + '_size']
            end = pos + size
            next_pos = pos + align(size, self.page)
            require(next_pos <= len(data), 'Truncated ' + name)
            self.parts[name] = data[pos:end]
            self.offsets[name] = pos
            self.padding[name] = data[end:next_pos]
            require(not any(self.padding[name]), 'Nonzero payload padding needs investigation')
            pos = next_pos
        self.trailer = data[pos:]
        require(self.trailer == b'SEANDROIDENFORCE', 'Unknown trailer/signature; refusing to rewrite')
        require(self.parts['dt'][:4] == b'DTBH', 'Expected Samsung DTBH table')
        require(self.parts['kernel'][56:60] == b'ARM\x64', 'Expected an ARM64 Image')
        require(self.header[576:596] == self.digest(self.parts), 'Boot image SHA-1 mismatch')

    @staticmethod
    def digest(parts):
        digest = hashlib.sha1()
        for name in ('kernel', 'ramdisk', 'second', 'dt'):
            digest.update(parts[name])
            digest.update(struct.pack('<I', len(parts[name])))
        return digest.digest()

    def repack(self, ramdisk):
        header = bytearray(self.header)
        parts = dict(self.parts, ramdisk=ramdisk)
        struct.pack_into('<I', header, 16, len(ramdisk))
        header[576:596] = self.digest(parts)
        out = bytes(header)
        for name in ('kernel', 'ramdisk', 'second', 'dt'):
            part = parts[name]
            out += part + bytes(align(len(part), self.page) - len(part))
        return out + self.trailer

    def metadata(self):
        fields = dict(self.fields)
        for key in fields:
            if key.endswith('_addr') or key == 'os_version_raw':
                fields[key] = f'0x{fields[key]:08x}'
        return dict(format='legacy Android + dt_size + Samsung DTBH', sha256=sha(self.data),
                    image_bytes=len(self.data), fields=fields,
                    name=self.header[48:64].split(b'\0')[0].decode('ascii'),
                    cmdline=self.header[64:576].split(b'\0')[0].decode('ascii'),
                    extra_cmdline=self.header[608:1632].split(b'\0')[0].decode('ascii'),
                    id_hex=self.header[576:608].hex(), trailer=self.trailer.decode(),
                    components={n: dict(offset=self.offsets[n], size=len(p), sha256=sha(p))
                                for n, p in self.parts.items()})


def baseline():
    data = ORIGINAL.read_bytes()
    require(sha(data) == BASELINE_SHA256, 'Baseline changed; inspect the new image before supporting it')
    return Image(data)


def cpio_entries(raw):
    """Read newc archives without extracting paths or creating device nodes."""
    pos = 0
    seen = set()
    while pos + 110 <= len(raw):
        header = raw[pos:pos+110]
        require(header[:6] == b'070701', 'Expected newc CPIO')
        v = [int(header[i:i+8], 16) for i in range(6, 110, 8)]
        size, namesize = v[6], v[11]
        require(namesize > 0 and pos+110+namesize <= len(raw), 'Truncated CPIO name')
        namebytes = raw[pos+110:pos+110+namesize]
        require(namebytes[-1] == 0, 'CPIO name is not terminated')
        name = namebytes[:-1].decode()
        start = align(pos+110+namesize, 4)
        require(start+size <= len(raw), 'Truncated CPIO payload')
        if name == 'TRAILER!!!':
            require(not any(raw[start+size:]), 'Unexpected data after CPIO trailer')
            return
        require(name not in seen and not name.startswith('/') and '..' not in name.split('/'),
                'Unsafe/duplicate CPIO path')
        seen.add(name)
        yield name, v, raw[start:start+size]
        pos = align(start+size, 4)
    raise ValueError('Missing CPIO trailer')


def elf_static(data):
    require(data[:6] == b'\x7fELF\x02\x01' and len(data) >= 64, 'BusyBox must be ELF64 little-endian')
    require(struct.unpack_from('<H', data, 18)[0] == 183, 'BusyBox must target AArch64, not host x86_64')
    require(struct.unpack_from('<H', data, 16)[0] == 2, 'Expected static ET_EXEC BusyBox')
    offset = struct.unpack_from('<Q', data, 32)[0]
    entsize, count = struct.unpack_from('<HH', data, 54)
    require(entsize >= 56 and count > 0 and offset + entsize*count <= len(data), 'Bad ELF program headers')
    for i in range(count):
        kind = struct.unpack_from('<I', data, offset+i*entsize)[0]
        require(kind not in (2, 3), 'BusyBox has PT_DYNAMIC/PT_INTERP; shared libraries are not allowed')


def unpack():
    source = ROOT / 'tools/orangefox/recovery.img'
    if not ORIGINAL.exists():
        if source.exists():
            data = source.read_bytes()
        else:
            with tarfile.open(ROOT / 'tools/OrangeFox-R11.1-Beta-j7velte.img.tar') as archive:
                members = archive.getmembers()
                require(len(members) == 1 and members[0].name == 'recovery.img' and members[0].isfile(),
                        'Source tar must contain only a regular recovery.img')
                data = archive.extractfile(members[0]).read()
        require(sha(data) == BASELINE_SHA256, 'Source is not the inspected OrangeFox image')
        write(ORIGINAL, data)
    image = baseline()
    require(image.repack(image.parts['ramdisk']) == image.data, 'Original round-trip failed')
    dest = ROOT / 'extracted'
    for name, data in image.parts.items():
        write(dest / dict(dt='dtb', ramdisk='ramdisk.cpio.lzma').get(name, name), data)
    write(dest / 'boot-metadata/header.bin', image.header)
    write(dest / 'boot-metadata/trailer.bin', image.trailer)
    json_write(dest / 'boot-metadata/metadata.json', image.metadata())
    kernel = image.parts['kernel']
    start = kernel.find(b'IKCFG_ST')
    require(start >= 0, 'Missing embedded kernel config')
    config = zlib.decompress(kernel[start+8:], 31)
    write(dest / 'boot-metadata/kernel.config', config)
    raw = lzma.decompress(image.parts['ramdisk'], format=lzma.FORMAT_ALONE)
    entries = list(cpio_entries(raw))
    json_write(dest / 'boot-metadata/original-ramdisk-inventory.json',
               [dict(path=n, mode=oct(v[1]), size=len(d), sha256=sha(d)) for n, v, d in entries])
    for n, v, d in entries:
        if stat.S_ISREG(v[1]) and (n.endswith('.rc') or n in ('etc/recovery.fstab', 'prop.default')):
            write(dest / 'reference' / n, d)
    write(ROOT / 'build/original-roundtrip.img', image.repack(image.parts['ramdisk']))
    make_tar(ROOT / 'build/OrangeFox-restore.tar', image.data)
    print('Inspected baseline; original round-trip is byte-for-byte identical.')


def install_busybox():
    package = ROOT / 'tools/downloads' / APK_NAME
    require(sha(package.read_bytes()) == APK_SHA256, 'BusyBox APK SHA-256 mismatch')
    # APK v2 has concatenated gzip/tar streams. tarfile ignore_zeros traverses all.
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(package.read_bytes())), mode='r:', ignore_zeros=True) as archive:
        members = [m for m in archive.getmembers() if m.name == 'bin/busybox.static']
        require(len(members) == 1 and members[0].isfile(), 'Missing/ambiguous BusyBox APK payload')
        data = archive.extractfile(members[0]).read()
    elf_static(data)
    path = ROOT / 'ramdisk/bin/busybox'
    write(path, data)
    path.chmod(0o755)
    json_write(ROOT / 'tools/busybox-provenance.json', dict(url=APK_URL, apk_sha256=APK_SHA256,
               binary_sha256=sha(data), architecture='aarch64', linking='static',
               note='Pinned HTTPS download; APK signature not independently verified. GPL-2.0-only.'))
    print('Installed static AArch64 BusyBox:', sha(data))


def cpio_record(name, data=b'', mode=stat.S_IFREG | 0o644, ino=1, rdev=(0, 0)):
    name = name.encode() + b'\0'
    values = (ino, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0, len(data), 0, 0, *rdev, len(name), 0)
    header = b'070701' + ''.join(f'{v:08x}' for v in values).encode()
    out = header + name
    out += bytes(align(len(out), 4)-len(out))
    out += data
    return out + bytes(align(len(out), 4)-len(out))


def usb_baseline():
    """Derive USB IDs from the known-good ramdisk, never a guessed descriptor."""
    raw = lzma.decompress(baseline().parts['ramdisk'])
    files = {n: d for n, _, d in cpio_entries(raw)}
    text = files['init.recovery.usb.rc'].decode()
    result = '# Extracted from the pinned OrangeFox init.recovery.usb.rc\n'
    for field, variable in (('idVendor', 'USB_VENDOR'), ('idProduct', 'USB_PRODUCT')):
        values = set(re.findall(r'/sys/class/android_usb/android0/' + field + r'\s+([0-9a-fA-F]{4})\b', text))
        require(len(values) == 1, 'Missing/ambiguous USB ' + field)
        result += f'{variable}={values.pop()}\n'
    return result.encode()


def build_initramfs():
    image = baseline()
    bb = (ROOT / 'ramdisk/bin/busybox').read_bytes()
    elf_static(bb)
    provenance = json.loads((ROOT / 'tools/busybox-provenance.json').read_text())
    require(sha(bb) == provenance['binary_sha256'], 'BusyBox differs from pinned package')
    init = (ROOT / 'ramdisk/init').read_bytes()
    require(init.startswith(b'#!/bin/sh\n'), '/init needs the /bin/sh shebang and LF line endings')
    write(ROOT / 'ramdisk/etc/usb-baseline.conf', usb_baseline())
    records = []
    def add(name, data=b'', mode=stat.S_IFREG | 0o644, rdev=(0, 0)):
        records.append(cpio_record(name, data, mode, len(records)+1, rdev))
    for name in ('bin', 'dev', 'dev/pts', 'etc', 'proc', 'sys', 'tmp'):
        add(name, mode=stat.S_IFDIR | (0o1777 if name == 'tmp' else 0o755))
    add('init', init, stat.S_IFREG | 0o755)
    add('bin/busybox', bb, stat.S_IFREG | 0o755)
    for name in EXTRA_FILES:
        data = (ROOT / 'ramdisk' / name).read_bytes()
        add(name, data, stat.S_IFREG | (0o755 if name.startswith('bin/') else 0o644))
    for name in APPLETS:
        add('bin/' + name, b'busybox', stat.S_IFLNK | 0o777)
    # Linux standard major/minor numbers, NOT device partition numbers.
    for name, dev, mode in (('console', (5, 1), 0o600), ('null', (1, 3), 0o666),
                            ('kmsg', (1, 11), 0o600), ('tty', (5, 0), 0o666)):
        add('dev/' + name, mode=stat.S_IFCHR | mode, rdev=dev)
    add('TRAILER!!!', mode=0)
    raw = b''.join(records)
    raw += bytes(align(len(raw), 512)-len(raw))
    validate_ramdisk(raw)
    write(ROOT / 'build/ramdisk.cpio', raw)
    write(ROOT / 'build/ramdisk.cpio.gz', gzip.compress(raw, compresslevel=9, mtime=0))
    # Keep the original LZMA-alone properties (lc/lp/pb and dictionary size).
    props, dictionary = struct.unpack_from('<BI', image.parts['ramdisk'])
    lc, rest = props % 9, props // 9
    lp, pb = rest % 5, rest // 5
    filters = [dict(id=lzma.FILTER_LZMA1, dict_size=dictionary, lc=lc, lp=lp, pb=pb)]
    compressed = lzma.compress(raw, format=lzma.FORMAT_ALONE, filters=filters)
    require(compressed[:13] == image.parts['ramdisk'][:13], 'LZMA properties changed')
    write(ROOT / 'build/ramdisk.cpio.lzma', compressed)
    print(f'Built root-owned deterministic initramfs: {len(raw)} bytes, LZMA {len(compressed)} bytes.')


def validate_ramdisk(raw):
    entries = {n: (v, d) for n, v, d in cpio_entries(raw)}
    required = {'bin', 'dev', 'dev/pts', 'etc', 'proc', 'sys', 'tmp', 'init', 'bin/busybox',
                'dev/console', 'dev/null', 'dev/kmsg', 'dev/tty'} | {'bin/' + x for x in APPLETS} | set(EXTRA_FILES)
    require(set(entries) == required, 'Unexpected/missing initramfs entries')
    for n, (v, d) in entries.items():
        require(v[2:4] == [0, 0], 'Initramfs entry is not owned by root: ' + n)
    elf_static(entries['bin/busybox'][1])
    elf_static(entries['bin/fb-heartbeat'][1])
    elf_static(entries['bin/ondevice-terminal'][1])
    for name in EXTRA_SCRIPTS:
        v, data = entries[name]
        require(v[1] == stat.S_IFREG | 0o755 and data.startswith(b'#!/bin/sh\n'),
                'Invalid diagnostic script: ' + name)
    require(entries['bin/fb-heartbeat'][0][1] == stat.S_IFREG | 0o755, 'Display helper is not executable')
    require(entries['bin/ondevice-terminal'][0][1] == stat.S_IFREG | 0o755, 'Terminal helper is not executable')
    require(entries['etc/usb-baseline.conf'][1] == usb_baseline(), 'USB IDs differ from OrangeFox')
    require(entries['init'][1].startswith(b'#!/bin/sh\n') and entries['init'][0][1] == stat.S_IFREG | 0o755,
            '/init must be an executable shell script')
    for applet in APPLETS:
        v, d = entries['bin/' + applet]
        require(stat.S_ISLNK(v[1]) and d == b'busybox', 'Invalid BusyBox applet link')
    for name, numbers in (('console', [5, 1]), ('null', [1, 3]), ('kmsg', [1, 11]), ('tty', [5, 0])):
        v, _ = entries['dev/' + name]
        require(stat.S_ISCHR(v[1]) and v[9:11] == numbers, 'Invalid early device node')


def tar_bytes(data):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        info = tarfile.TarInfo('recovery.img')
        info.size, info.mode, info.mtime = len(data), 0o644, 0
        info.uid = info.gid = 0
        archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def make_tar(path, data):
    write(path, tar_bytes(data))


def verify_image(data, restore=False):
    old = baseline()
    new = Image(data)
    require(len(data) <= len(old.data), 'Image exceeds known-good image length (not a measured partition size)')
    if restore:
        require(data == old.data, 'Restore image is not the exact OrangeFox baseline')
        return new
    expected_header = bytearray(old.header)
    expected_header[16:20] = new.header[16:20]
    expected_header[576:596] = new.header[576:596]
    require(new.header == expected_header, 'Header bytes changed outside ramdisk size and SHA-1')
    for name in ('kernel', 'second', 'dt'):
        require(new.parts[name] == old.parts[name], name + ' changed')
    require(new.trailer == old.trailer, 'Trailer changed')
    require(new.parts['ramdisk'][:13] == old.parts['ramdisk'][:13], 'Ramdisk compression changed')
    validate_ramdisk(lzma.decompress(new.parts['ramdisk'], format=lzma.FORMAT_ALONE))
    return new


def verify_tar(path, restore=False):
    # Never extract arbitrary archive paths. Exactly one regular recovery.img.
    with tarfile.open(path, mode='r:') as archive:
        members = archive.getmembers()
        require(len(members) == 1 and members[0].name == 'recovery.img' and members[0].isfile(),
                'Archive must contain ONLY a regular recovery.img')
        data = archive.extractfile(members[0]).read()
    require(Path(path).read_bytes() == tar_bytes(data),
            'Archive is not the canonical recovery-only USTAR (extra headers/trailing data)')
    verify_image(data, restore)
    return data


def repack():
    old = baseline()
    ramdisk = (ROOT / 'build/ramdisk.cpio.lzma').read_bytes()
    data = old.repack(ramdisk)
    new = verify_image(data)
    write(ROOT / 'build/recovery.img', data)
    make_tar(ROOT / 'build/recovery.tar', data)
    json_write(ROOT / 'build/build-report.json', dict(original=old.metadata(), built=new.metadata(),
               original_roundtrip_identical=old.repack(old.parts['ramdisk']) == old.data,
               preserved=['kernel', 'DTBH/DTBs', 'second', 'header except ramdisk_size and SHA-1', 'trailer'],
               hardware_boot_tested=False,
               usb_access='legacy ACM serial console confirmed on previous image; this image not yet flashed',
               visual_indicator='touchscreen framebuffer terminal confirmed in RAM; this image not yet flashed'))
    print(f'Built recovery.img ({len(data)} bytes) and recovery.tar; kernel/DTB/header verified.')


def verify():
    old = baseline()
    require(old.repack(old.parts['ramdisk']) == old.data, 'Round-trip mismatch')
    data = verify_tar(ROOT / 'build/recovery.tar')
    require(data == (ROOT / 'build/recovery.img').read_bytes(), 'Tar payload differs from recovery.img')
    verify_tar(ROOT / 'build/OrangeFox-restore.tar', restore=True)
    new = verify_image(data)
    require(new.parts['ramdisk'] == (ROOT / 'build/ramdisk.cpio.lzma').read_bytes(), 'Stale repacked image')
    raw = lzma.decompress(new.parts['ramdisk'])
    require(raw == gzip.decompress((ROOT / 'build/ramdisk.cpio.gz').read_bytes()), 'Compression outputs differ')
    entries = {n: d for n, _, d in cpio_entries(raw)}
    for name in ('init', 'bin/busybox', *EXTRA_FILES):
        require(entries[name] == (ROOT / 'ramdisk' / name).read_bytes(), 'Stale ramdisk: ' + name)
    paths = ['original/OrangeFox-recovery.img', 'ramdisk/bin/busybox', 'ramdisk/bin/fb-heartbeat', 'ramdisk/bin/ondevice-terminal', 'build/ramdisk.cpio.lzma',
             'build/ramdisk.cpio.gz', 'build/recovery.img', 'build/recovery.tar', 'build/OrangeFox-restore.tar']
    write(ROOT / 'build/SHA256SUMS', ''.join(f'{sha((ROOT/p).read_bytes())}  {p}\n' for p in paths).encode())
    print('PASS: original round-trip; preserved boot parameters; static AArch64 ELF; initramfs; recovery-only tar; restore tar.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['unpack', 'install-busybox', 'initramfs', 'repack', 'verify', 'verify-tar'])
    parser.add_argument('archive', nargs='?')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()
    if args.action == 'verify-tar':
        require(args.archive is not None, 'Archive path required')
        verify_tar(args.archive, args.restore)
        print('Verified recovery-only archive:', args.archive)
    else:
        {'unpack': unpack, 'install-busybox': install_busybox, 'initramfs': build_initramfs,
         'repack': repack, 'verify': verify}[args.action]()


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, EOFError, tarfile.TarError, lzma.LZMAError, zlib.error) as exc:
        raise SystemExit(f'ERROR: {exc}')
