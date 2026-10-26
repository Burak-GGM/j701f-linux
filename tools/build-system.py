#!/usr/bin/env python3
"""Build experimental BOOT + USERDATA files without contacting or writing the phone."""
import argparse
import hashlib
import importlib.util
import io
import json
import lzma
import os
import re
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tarfile
import tempfile
import uuid

import recovery

ROOT = recovery.ROOT
OUT = ROOT / 'build/system'
VERSION = 'BURAK_ALPINE_0_1'
UUID = '4ce26b55-8a59-4fb7-aad4-919a5c2cefeb'
DATA_BYTES = 23314432 * 512
FEATURES = 'has_journal,ext_attr,resize_inode,dir_index,filetype,extent,sparse_super,large_file,huge_file,uninit_bg,dir_nlink,extra_isize'
STARTUP_FILES = ('etc/j701f-root', 'etc/j701f-system-version', 'etc/alpine-release',
                 'etc/inittab', 'etc/usb-baseline.conf', 'sbin/j701f-start', 'bin/busybox',
                 'bin/display-status', 'bin/usb-debug', 'bin/usb-shell',
                 'bin/ondevice-terminal', 'bin/fb-heartbeat', 'sbin/apk',
                 'lib/ld-musl-aarch64.so.1')


def run(*args):
    subprocess.run([str(a) for a in args], check=True)


def alpine_module():
    spec = importlib.util.spec_from_file_location('alpine', ROOT / 'tools/alpine-ram-test.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def put(path, data, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    path.chmod(0o755 if executable else 0o644)


def populate():
    """Called under fakeroot so archive ownership propagates into mkfs -d."""
    source = alpine_module().prepare()[0]
    root = OUT / 'rootfs'
    if root.exists(): shutil.rmtree(root)
    root.mkdir()
    with tarfile.open(source) as archive:
        # prepare() has verified the signature, exact hash and safe extraction paths.
        archive.extractall(root, filter='fully_trusted')
        # A restricted chown can make tarfile stop before its chmod step. Apply
        # signed archive modes explicitly; never follow an archive symlink here.
        for entry in archive.getmembers():
            if not entry.issym() and not entry.islnk():
                (root / entry.name).chmod(entry.mode & 0o7777)
    for script in ('display-status', 'usb-debug'):
        content = (ROOT / 'ramdisk/bin' / script).read_text().replace('export PATH=/bin', 'export PATH=/usr/sbin:/usr/bin:/sbin:/bin')
        put(root / 'bin' / script, content, True)
    for binary in ('ondevice-terminal', 'fb-heartbeat'):
        put(root / 'bin' / binary, (ROOT / 'ramdisk/bin' / binary).read_bytes(), True)
    put(root / 'bin/usb-shell', (ROOT / 'system/usb-shell').read_bytes(), True)
    put(root / 'sbin/j701f-start', (ROOT / 'system/start').read_bytes(), True)
    put(root / 'sbin/j701f-wifi', (ROOT / 'system/wifi').read_bytes(), True)
    put(root / 'sbin/j701f-wifi-dhcp', (ROOT / 'system/wifi-dhcp').read_bytes(), True)
    put(root / 'sbin/j701f-sshd', (ROOT / 'system/sshd').read_bytes(), True)
    put(root / 'etc/inittab', (ROOT / 'system/inittab').read_bytes())
    put(root / 'etc/usb-baseline.conf', (ROOT / 'ramdisk/etc/usb-baseline.conf').read_bytes())
    put(root / 'etc/j701f-root', 'J701F_ALPINE_ROOT_V1\n')
    put(root / 'etc/j701f-system-version', VERSION + '\n')
    put(root / 'etc/hostname', 'burak-linux\n')
    put(root / 'etc/fstab', '# Root and virtual filesystems are mounted by the J701F BOOT loader.\n')
    for directory in ('dev', 'dev/pts', 'proc', 'sys', 'run', 'tmp', 'root'):
        (root / directory).mkdir(exist_ok=True)
    (root / 'tmp').chmod(0o1777)
    (root / 'root').chmod(0o700)
    # fakeroot maps host-user-owned staging files to root for mke2fs's stat calls.
    # Do not issue real chown calls (some restricted host runtimes reject them).
    image = OUT / 'userdata.ext4'
    with image.open('wb') as file: file.truncate(DATA_BYTES)
    run('mkfs.ext4', '-F', '-b', '4096', '-I', '256', '-L', 'BURAK_LINUX', '-U', UUID,
        '-m', '1', '-O', 'none,' + FEATURES,
        '-E', 'lazy_itable_init=0,lazy_journal_init=0,root_owner=0:0', '-d', root, image)


def boot_ramdisk(ram_test=False):
    raw = (ROOT / 'build/ramdisk.cpio').read_bytes()
    entries = {name: (values[1], data, tuple(values[9:11])) for name, values, data in recovery.cpio_entries(raw)}
    entries['init-rescue'] = entries['init']
    entries['init'] = (stat.S_IFREG | 0o755, (ROOT / 'system/boot-init').read_bytes(), (0, 0))
    entries['newroot'] = (stat.S_IFDIR | 0o755, b'', (0, 0))
    entries['etc/j701f-loader.conf'] = (stat.S_IFREG | 0o644,
        f"ROOT_UUID='{UUID}'\nSYSTEM_VERSION='{VERSION}'\n".encode(), (0, 0))
    if ram_test: entries['etc/j701f-ram-test'] = (stat.S_IFREG | 0o644, b'RAM_ONLY\n', (0, 0))
    output = b''.join(recovery.cpio_record(name, data, mode, index + 1, numbers)
                      for index, (name, (mode, data, numbers)) in enumerate(sorted(entries.items())))
    output += recovery.cpio_record('TRAILER!!!', b'', 0, len(entries) + 1)
    return output + bytes(recovery.align(len(output), 512) - len(output))


def live_boot_template():
    path = ROOT / 'build/backups/boot-original.img'
    metadata = json.loads(path.with_suffix('.json').read_text())
    data = path.read_bytes()
    recovery.require(len(data) == 32 * 1024 * 1024 and recovery.sha(data) == metadata['sha256'], 'BOOT backup integrity failed')
    fields = struct.unpack_from('<10I', data, 8)
    page = fields[7]
    recovery.require(page == 2048, 'Unexpected BOOT page size')
    length = page + sum(recovery.align(fields[index], page) for index in (0, 2, 4, 8)) + 16
    # The exact original partition (including stock signing footer) stays backed up.
    # Custom output uses the unsigned development trailer, as the working recovery does.
    image = recovery.Image(data[:length])
    reference = recovery.baseline()
    for field in ('kernel_addr', 'ramdisk_addr', 'second_addr', 'tags_addr', 'page_size'):
        recovery.require(image.fields[field] == reference.fields[field], 'BOOT load address differs: ' + field)
    recovery.require(image.fields['second_size'] == 0, 'Unexpected BOOT second stage')
    return image, metadata


def make_boot():
    original, metadata = live_boot_template()
    reference = recovery.baseline()
    raw = boot_ramdisk()
    recovery.write(OUT / 'boot-ramdisk.cpio', raw)
    compressed = lzma.compress(raw, format=lzma.FORMAT_ALONE)
    header = bytearray(original.header)
    parts = dict(kernel=reference.parts['kernel'], ramdisk=compressed,
                 second=reference.parts['second'], dt=reference.parts['dt'])
    for name, offset in (('kernel', 8), ('ramdisk', 16), ('second', 24), ('dt', 40)):
        struct.pack_into('<I', header, offset, len(parts[name]))
    header[576:596] = recovery.Image.digest(parts)
    output = bytes(header)
    for part in parts.values(): output += part + bytes(recovery.align(len(part), original.page) - len(part))
    output += b'SEANDROIDENFORCE'
    recovery.require(len(output) <= 32 * 1024 * 1024, 'BOOT image exceeds measured capacity')
    built = recovery.Image(output)
    for name in ('kernel', 'second', 'dt'):
        recovery.require(built.parts[name] == reference.parts[name], 'Recovery payload changed: ' + name)
    recovery.write(OUT / 'boot.img', output)
    return metadata


def tar_output(destination, files):
    with tarfile.open(destination, 'w', format=tarfile.USTAR_FORMAT) as archive:
        for name, path in files:
            info = tarfile.TarInfo(name)
            info.mode = 0o644; info.size = path.stat().st_size
            with path.open('rb') as source: archive.addfile(info, source)


def ext4_free_ranges(report, blocks):
    """Read dumpe2fs's allocated/free map, including BLOCK_UNINIT groups.

    Never infer disposable blocks from their byte contents: initialized zero
    inode tables and journal blocks must still be sent as RAW to the device.
    """
    match = re.search(r'^Free blocks:\s+(\d+)\s*$', report, re.M)
    recovery.require(match is not None, 'Missing ext4 free block total')
    groups = list(re.finditer(r'^Group (\d+): \(Blocks (\d+)-(\d+)\)', report, re.M))
    recovery.require(bool(groups), 'Missing ext4 allocation groups')
    free = []
    next_block = 0
    for index, group in enumerate(groups):
        number, first, last = map(int, group.groups())
        recovery.require(number == index and first == next_block and first <= last < blocks,
                         'Invalid ext4 group bounds')
        segment = report[group.end():groups[index + 1].start() if index + 1 < len(groups) else len(report)]
        listed = re.search(r'^  Free blocks:(.*)$', segment, re.M)
        count = re.search(r'^  (\d+) free blocks,', segment, re.M)
        recovery.require(listed is not None and count is not None, 'Missing group free map')
        group_total = 0
        previous = first - 1
        for token in listed.group(1).strip().split(','):
            token = token.strip()
            if not token: continue
            recovery.require(re.fullmatch(r'\d+(?:-\d+)?', token) is not None, 'Invalid free block range')
            fields = list(map(int, token.split('-')))
            begin, finish = fields[0], fields[-1]
            recovery.require(first <= begin <= finish <= last and begin > previous,
                             'Overlapping/out-of-bounds free blocks')
            free.append((begin, finish + 1))
            group_total += finish - begin + 1
            previous = finish
        recovery.require(group_total == int(count.group(1)), 'Group free block count differs')
        next_block = last + 1
    recovery.require(next_block == blocks and sum(end - begin for begin, end in free) == int(match.group(1)),
                     'Ext4 allocation map incomplete')
    return free


def write_samsung_sparse(image, destination, report=None):
    """Match the supplied J701F firmware's 32/16-byte RAW/skip encoding.

    RAW includes every allocated block, even all-zero metadata. DONT_CARE
    ranges are restricted to blocks explicitly free in the clean ext4 map.
    Such ranges are not a secure erase of previous contents on the phone.
    """
    recovery.require(image.is_file() and not image.is_symlink() and image.stat().st_size == DATA_BYTES,
                     'Expected a regular full-capacity host ext4 image')
    if report is None:
        report = subprocess.run(['dumpe2fs', str(image)], check=True, capture_output=True,
                                text=True, env={**os.environ, 'LC_ALL': 'C'}).stdout
    free = ext4_free_ranges(report, DATA_BYTES // 4096)
    position = 0
    ranges = []
    for begin, end in free:
        if begin > position: ranges.append((0xcac1, position, begin))
        ranges.append((0xcac3, begin, end))
        position = end
    if position < DATA_BYTES // 4096: ranges.append((0xcac1, position, DATA_BYTES // 4096))
    # Bound RAW payloads to the largest measured stock firmware RAW chunk.
    chunks = []
    for kind, begin, end in ranges:
        maximum = 65505 if kind == 0xcac1 else 0xffffffff
        while begin < end:
            finish = min(end, begin + maximum)
            chunks.append((kind, begin, finish)); begin = finish
    temporary = destination.with_suffix(destination.suffix + '.part')
    try:
        with image.open('rb') as source, temporary.open('wb') as output:
            output.write(struct.pack('<IHHHHIIII', 0xed26ff3a, 1, 0, 32, 16, 4096,
                                     DATA_BYTES // 4096, len(chunks), 0) + bytes(4))
            for kind, begin, end in chunks:
                length = (end - begin) * 4096
                payload = length if kind == 0xcac1 else 0
                output.write(struct.pack('<HHIII', kind, 0, end - begin, 16 + payload, 0x55ca))
                if payload:
                    source.seek(begin * 4096)
                    while payload:
                        data = source.read(min(payload, 1024 * 1024))
                        recovery.require(bool(data), 'Ext4 RAW input truncated')
                        output.write(data); payload -= len(data)
        sparse_info(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def sparse_info(path):
    """Strictly bound generic or measured Samsung Android sparse chunks."""
    with path.open('rb') as file:
        header = file.read(28)
        recovery.require(len(header) == 28, 'Sparse header truncated')
        magic, major, minor, header_size, chunk_size, block_size, blocks, chunks, checksum = struct.unpack('<IHHHHIIII', header)
        recovery.require((magic, major, minor, block_size) == (0xed26ff3a, 1, 0, 4096) and
                         (header_size, chunk_size) in ((28, 12), (32, 16)), 'Unsupported sparse format')
        samsung = header_size == 32
        if samsung:
            recovery.require(file.read(4) == bytes(4) and checksum == 0, 'Unexpected Samsung sparse extension')
        recovery.require(blocks * block_size == DATA_BYTES and chunks < 100000, 'Sparse expanded capacity mismatch')
        produced = 0
        types = {}
        for _ in range(chunks):
            raw = file.read(chunk_size); recovery.require(len(raw) == chunk_size, 'Sparse chunk truncated')
            kind, reserved, count, total_size = struct.unpack('<HHII', raw[:12])
            if samsung:
                recovery.require(raw[12:] == struct.pack('<I', 0x55ca) and kind in (0xcac1, 0xcac3),
                                 'Unexpected Samsung sparse chunk extension/type')
            payload = total_size - chunk_size
            expected = {0xcac1: count * block_size, 0xcac2: 4, 0xcac3: 0, 0xcac4: 4}.get(kind)
            recovery.require(reserved == 0 and expected is not None and payload == expected, 'Invalid sparse chunk')
            recovery.require(kind != 0xcac4 or count == 0, 'Invalid sparse CRC count')
            produced += count
            recovery.require(produced <= blocks, 'Sparse chunk exceeds partition')
            file.seek(payload, 1)
            recovery.require(file.tell() <= path.stat().st_size, 'Sparse payload truncated')
            types[hex(kind)] = types.get(hex(kind), 0) + 1
        recovery.require(produced == blocks and file.tell() == path.stat().st_size, 'Sparse trailing bytes or missing blocks')
        return dict(expanded_bytes=DATA_BYTES, block_size=block_size, chunks=chunks, chunk_types=types,
                    file_header_bytes=header_size, chunk_header_bytes=chunk_size,
                    encoding='samsung-j701f-raw-skip' if samsung else 'android-generic')


def verify_sparse_roundtrip(sparse, image):
    """Compare decoded bytes exactly, skipping only filesystem-confirmed holes.

    Avoid materializing a dense 11 GiB scratch copy just to check the encoding.
    """
    def compare_fill(raw, start, count, pattern):
        end = start + count
        position = start
        while position < end:
            if pattern == b'\0' * 4:
                try:
                    data_at = os.lseek(raw.fileno(), position, os.SEEK_DATA)
                except OSError as error:
                    if error.errno == 6: return  # ENXIO: remainder is a hole.
                    data_at = position
                if data_at >= end: return
                position = max(position, data_at)
            raw.seek(position)
            length = min(1024 * 1024, end - position)
            recovery.require(raw.read(length) == (pattern * ((length + 3) // 4))[:length], 'Sparse fill/skip differs from raw image')
            position += length
    with sparse.open('rb') as encoded, image.open('rb', buffering=0) as raw:
        header = struct.unpack('<IHHHHIIII', encoded.read(28))
        encoded.read(header[3] - 28)
        offset = 0
        for _ in range(header[7]):
            kind, _, blocks, size = struct.unpack('<HHII', encoded.read(header[4])[:12])
            count = blocks * header[5]
            if kind == 0xcac1:
                remaining = count
                raw.seek(offset)
                while remaining:
                    length = min(1024 * 1024, remaining)
                    recovery.require(encoded.read(length) == raw.read(length), 'Sparse RAW differs from raw image')
                    remaining -= length
            elif kind == 0xcac2:
                compare_fill(raw, offset, count, encoded.read(4))
            elif kind == 0xcac3:
                compare_fill(raw, offset, count, b'\0' * 4)
            else:
                encoded.read(size - header[4])
            offset += count
        recovery.require(offset == image.stat().st_size, 'Sparse roundtrip size differs')
    print('PASS: sparse encoding decodes exactly to the host ext4 image.')


def verify_bundle():
    manifest = json.loads((OUT / 'manifest.json').read_text())
    recovery.require(manifest['version'] == VERSION and manifest['root_uuid'] == UUID and manifest['data_bytes'] == DATA_BYTES and
                     manifest['targets'] == ['BOOT', 'USERDATA'], 'Unexpected system manifest targets/version')
    recovery.require(set(manifest['files']) == {'boot.img', 'userdata.img', 'boot.tar', 'userdata.tar', 'burak-alpine.tar', 'BOOT-restore.tar'}, 'Incomplete bundle manifest')
    startup = manifest.get('startup_file_sha256', {})
    recovery.require(set(startup) == set(STARTUP_FILES) and all(re.fullmatch(r'[0-9a-f]{64}', digest) for digest in startup.values()),
                     'Incomplete installed startup-file hash contract')
    for name, info in manifest['files'].items():
        recovery.require(name in ('boot.img', 'userdata.img', 'boot.tar', 'userdata.tar', 'burak-alpine.tar', 'BOOT-restore.tar'), 'Unexpected bundle file')
        path = OUT / name
        recovery.require(path.stat().st_size == info['bytes'] and recovery.sha(path.read_bytes()) == info['sha256'], 'Bundle integrity failed: ' + name)
    built = recovery.Image((OUT / 'boot.img').read_bytes())
    reference = recovery.baseline()
    original, _ = live_boot_template()
    for name in ('kernel', 'dt', 'second'): recovery.require(built.parts[name] == reference.parts[name], 'Unexpected BOOT payload')
    allowed = set(range(8, 12)) | set(range(16, 20)) | set(range(24, 28)) | set(range(40, 44)) | set(range(576, 596))
    recovery.require(all(a == b or index in allowed for index, (a, b) in enumerate(zip(original.header, built.header))), 'BOOT load parameters changed')
    recovery.require(lzma.decompress(built.parts['ramdisk']) == boot_ramdisk(), 'BOOT ramdisk differs from current source')
    sparse = sparse_info(OUT / 'userdata.img')
    recovery.require(sparse['encoding'] == 'samsung-j701f-raw-skip',
                     'Generic sparse DATA is not approved for this Samsung bootloader')
    with (OUT / 'userdata.img').open('rb') as file:
        file.seek(sparse['file_header_bytes'])
        kind, _, count, _ = struct.unpack('<HHII', file.read(sparse['chunk_header_bytes'])[:12])
        recovery.require(kind == 0xcac1 and count >= 1, 'Missing raw ext4 superblock in sparse image')
        superblock = file.read(4096)[1024:2048]
    recovery.require(struct.unpack_from('<H', superblock, 56)[0] == 0xef53, 'DATA is not ext4')
    recovery.require(superblock[104:120] == uuid.UUID(UUID).bytes, 'DATA UUID differs from BOOT loader')
    recovery.require(struct.unpack_from('<I', superblock, 4)[0] * 4096 == DATA_BYTES and
                     struct.unpack_from('<I', superblock, 24)[0] == 2, 'ext4 block size/capacity mismatch')
    compatibility, incompatible, readonly = struct.unpack_from('<III', superblock, 92)
    recovery.require(compatibility == 0x3c and incompatible == 0x42 and readonly == 0x7b,
                     'Unexpected ext4 features for the legacy kernel')
    layouts = {'boot.tar': [('boot.img', OUT / 'boot.img')],
               'userdata.tar': [('userdata.img', OUT / 'userdata.img')],
               'burak-alpine.tar': [('userdata.img', OUT / 'userdata.img'), ('boot.img', OUT / 'boot.img')],
               'BOOT-restore.tar': [('boot.img', ROOT / 'build/backups/boot-original.img')]}
    for filename, wanted in layouts.items():
        with tarfile.open(OUT / filename, 'r:') as archive:
            members = archive.getmembers()
            recovery.require([m.name for m in members] == [name for name, _ in wanted] and all(m.isfile() for m in members), 'Forbidden/missing tar target')
            for entry, (_, source) in zip(members, wanted):
                recovery.require(archive.extractfile(entry).read() == source.read_bytes(), 'Stale tar payload')
        # Canonical USTAR rejects extra hidden headers, appended payloads and tar tricks.
        temporary = OUT / 'canonical-check.tar'
        try:
            tar_output(temporary, wanted)
            recovery.require(temporary.read_bytes() == (OUT / filename).read_bytes(), 'Noncanonical system archive')
        finally:
            temporary.unlink(missing_ok=True)
    print('PASS: BOOT load parameters and known recovery kernel/DTBH; DATA sparse bounds; exact BOOT/USERDATA tar allowlist; original BOOT restore.')


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    alpine_module().prepare()
    backup = make_boot()
    run('fakeroot', 'python3', Path(__file__).resolve(), 'populate')
    run('e2fsck', '-f', '-n', OUT / 'userdata.ext4')
    write_samsung_sparse(OUT / 'userdata.ext4', OUT / 'userdata.img')
    package()


def startup_file_hashes():
    """Bind the read-back contract to files extracted from the raw host image."""
    result = {}
    with tempfile.TemporaryDirectory(prefix='startup-check-', dir=OUT) as directory:
        for index, name in enumerate(STARTUP_FILES):
            destination = Path(directory) / str(index)
            subprocess.run(['debugfs', '-R', f'dump /{name} {destination}', str(OUT / 'userdata.ext4')],
                           check=True, capture_output=True)
            recovery.require(destination.is_file() and not destination.is_symlink(),
                             'Raw image startup file missing: ' + name)
            result[name] = recovery.sha(destination.read_bytes())
    return result


def package(verify_raw=True):
    _, backup = live_boot_template()
    sparse = sparse_info(OUT / 'userdata.img')
    if verify_raw:
        verify_sparse_roundtrip(OUT / 'userdata.img', OUT / 'userdata.ext4')
    else:
        old = json.loads((OUT / 'manifest.json').read_text())
        recovery.require(recovery.sha((OUT / 'userdata.img').read_bytes()) == old['files']['userdata.img']['sha256'],
                         'DATA image changed; perform a full build/roundtrip before repacking BOOT')
    tar_output(OUT / 'boot.tar', [('boot.img', OUT / 'boot.img')])
    tar_output(OUT / 'userdata.tar', [('userdata.img', OUT / 'userdata.img')])
    tar_output(OUT / 'burak-alpine.tar', [('userdata.img', OUT / 'userdata.img'), ('boot.img', OUT / 'boot.img')])
    tar_output(OUT / 'BOOT-restore.tar', [('boot.img', ROOT / 'build/backups/boot-original.img')])
    names = ('boot.img', 'userdata.img', 'boot.tar', 'userdata.tar', 'burak-alpine.tar', 'BOOT-restore.tar')
    manifest = dict(version=VERSION, root_uuid=UUID, targets=['BOOT', 'USERDATA'],
                    startup_file_sha256=startup_file_hashes(),
                    data_bytes=DATA_BYTES, alpine_sha256=alpine_module().SHA256,
                    ext4_features=FEATURES.split(','), sparse=sparse,
                    mmc_cid_sha256=backup['mmc_cid_sha256'], userdata_backup_available=False,
                    normal_boot_path_hardware_tested=False,
                    isolated_ram_handoff_tested=(ROOT / 'build/phone-system-handoff.txt').exists() and
                    'HANDOFF_RAM_CLEANUP_OK' in (ROOT / 'build/phone-system-handoff.txt').read_text(),
                    files={name: dict(bytes=(OUT/name).stat().st_size,
                    sha256=recovery.sha((OUT/name).read_bytes())) for name in names})
    recovery.json_write(OUT / 'manifest.json', manifest)
    verify_bundle()


def repack_boot():
    make_boot()
    package(verify_raw=False)


def repack_data():
    run('e2fsck', '-f', '-n', OUT / 'userdata.ext4')
    write_samsung_sparse(OUT / 'userdata.ext4', OUT / 'userdata.img')
    package()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'populate', 'verify', 'package', 'repack-boot', 'repack-data'])
    args = parser.parse_args()
    {'build': build, 'populate': populate, 'verify': verify_bundle, 'package': package, 'repack-boot': repack_boot, 'repack-data': repack_data}[args.action]()


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'System images: {error}')
