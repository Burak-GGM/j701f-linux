#!/usr/bin/env python3
"""Prepare a pinned kernel/DT/initramfs RAM payload. Never writes a phone."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/handoff'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()


def align(value, boundary):
    return (value + boundary - 1) // boundary * boundary


def ranges(reg):
    require(len(reg) % 3 == 0, 'Unexpected measured RAM cells')
    return [((reg[i] << 32) | reg[i + 1], ((reg[i] << 32) | reg[i + 1]) + reg[i + 2])
            for i in range(0, len(reg), 3)]


def layout(image_size, text_offset, dtb_bytes, initrd_bytes, hardware):
    banks = sorted(sum([ranges(r) for r in hardware['memory'].values()], []))
    require(banks and banks[0][0] % 0x200000 == 0, 'Measured RAM base is not 2 MiB aligned')
    reserved = sum([ranges(r) for r in hardware['reservations'].values()], [])
    reserved.append((0x46000000, 0x47000000))  # existing conservative debug envelope
    source_limit = min(a for a, b in reserved if a >= banks[0][0])
    require(0 < image_size <= 512 * 1024 * 1024 and 0 <= text_offset < 0x200000,
            'Invalid ARM64 Image size/offset')
    require(0 < dtb_bytes <= 2 * 1024 * 1024 and 0 < initrd_bytes <= 16 * 1024 * 1024,
            'Diagnostic DT/initramfs size out of bounds')
    kernel = banks[0][0] + text_offset
    fdt = align(kernel + image_size, 0x200000)
    fdt_capacity = align(dtb_bytes + 65536, 0x200000)
    initrd = align(fdt + fdt_capacity, 0x200000)
    regions = [('kernel', kernel, image_size), ('fdt', fdt, fdt_capacity),
               ('initramfs', initrd, align(initrd_bytes, 4096))]
    for name, start, size in regions:
        end = start + size
        require(any(a <= start and end <= b for a, b in banks), name + ' outside measured RAM')
        require(not any(start < b and a < end for a, b in reserved), name + ' overlaps reserved memory')
        require(end < source_limit, name + ' leaves no lower-bank room for Samsung RAM payload')
    return dict(kernel=kernel, kernel_memory_size=image_size, fdt=fdt,
                fdt_capacity=fdt_capacity, initramfs=initrd,
                targets_end=regions[-1][1] + regions[-1][2], source_limit=source_limit,
                basis='lowest measured RAM bank, ARM64 header offset/size, 2 MiB alignment, measured reservations')


def fit_properties(blob):
    """Read inline FIT properties, with bounds checks; no extraction or device access."""
    require(len(blob) >= 40, 'Truncated FIT header')
    magic, total, so, strings, reserve, version, last, bootcpu, slen, nlen = struct.unpack_from('>10I', blob)
    require(magic == 0xd00dfeed and total == len(blob) and version >= 17, 'Unexpected FIT header')
    require(40 <= so <= total and so + nlen <= total and strings + slen <= total, 'FIT bounds invalid')
    names = blob[strings:strings + slen]
    cursor, end, stack, result = so, so + nlen, [], {}
    while cursor + 4 <= end:
        tag, = struct.unpack_from('>I', blob, cursor); cursor += 4
        if tag == 1:
            nul = blob.find(b'\0', cursor, end)
            require(nul >= 0, 'Unterminated FIT node')
            stack.append(blob[cursor:nul].decode()); cursor = align(nul + 1, 4)
        elif tag == 2:
            require(bool(stack), 'Unexpected FIT node end'); stack.pop()
        elif tag == 3:
            require(cursor + 8 <= end and stack, 'Truncated FIT property')
            length, name_offset = struct.unpack_from('>2I', blob, cursor); cursor += 8
            require(name_offset < len(names) and cursor + length <= end, 'Invalid FIT property bounds')
            nul = names.find(b'\0', name_offset)
            require(nul >= 0, 'Unterminated FIT property name')
            key = '/'.join(stack) + '/' + names[name_offset:nul].decode()
            require(key not in result, 'Duplicate FIT property')
            result[key] = blob[cursor:cursor + length]; cursor = align(cursor + length, 4)
        elif tag == 4:
            continue
        elif tag == 9:
            require(not stack, 'Unclosed FIT node'); return result
        else:
            raise ValueError('Unknown FIT structure tag')
    raise ValueError('FIT end marker missing')


def validate_payload(data, expected, compression):
    if compression == 'gzip':
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            decoded = decoder.decompress(data, len(expected) + 1)
        except zlib.error as error:
            raise ValueError('Invalid gzip payload') from error
        require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                'Truncated, trailing or oversized gzip payload')
        require(decoded == expected, 'FIT payload mismatch after decompression')
    else:
        require(compression == 'none', 'Unsupported FIT compression')
        require(data == expected, 'FIT payload mismatch')


def verify(blob, inputs, planned, kernel_compression='none'):
    props = fit_properties(blob)
    require(props['/configurations/default'] == b'conf-j701f-diagnostic\0', 'Wrong default FIT configuration')
    conf = '/configurations/conf-j701f-diagnostic/'
    for prop, value in [('kernel', 'kernel'), ('fdt', 'fdt'), ('ramdisk', 'initramfs'),
                        ('compatible', 'samsung,j7velte')]:
        require(props[conf + prop] == value.encode() + b'\0', 'Wrong FIT configuration reference')
    for name, kind in [('kernel', 'kernel'), ('fdt', 'flat_dt'), ('initramfs', 'ramdisk')]:
        prefix = '/images/' + name
        data = props[prefix + '/data']
        compression = kernel_compression if name == 'kernel' else 'none'
        validate_payload(data, inputs[name].read_bytes(), compression)
        require(props[prefix + '/hash-1/value'] == hashlib.sha256(data).digest(), 'FIT SHA256 mismatch: ' + name)
        require(props[prefix + '/hash-1/algo'] == b'sha256\0', 'Unsupported FIT hash')
        require(props[prefix + '/type'] == kind.encode() + b'\0', 'Wrong FIT component type')
        for prop, value in [('arch', 'arm64'), ('os', 'linux'), ('compression', compression)]:
            require(props[prefix + '/' + prop] == value.encode() + b'\0', 'Wrong FIT component encoding')
        require(props[prefix + '/load'] == struct.pack('>I', planned[name]), 'FIT load differs from plan')
    require(props['/images/kernel/entry'] == struct.pack('>I', planned['kernel']), 'Wrong kernel entry')
    return dict(inline_payloads_match=True, sha256_hashes_verified=True, load_addresses_match=True)


def main(out=OUT, kernel_compression='none', diagnostic_dir=None):
    diagnostic_dir = (diagnostic_dir or ROOT / 'build/kernel/j701f-diagnostic').resolve()
    require(diagnostic_dir.is_relative_to(ROOT / 'build/kernel'), 'Diagnostic inputs must be under build/kernel')
    out = out.resolve()
    require(out.is_relative_to(ROOT / 'build/kernel'), 'Output must be under build/kernel')
    require(kernel_compression in ('none', 'gzip'), 'Unsupported kernel compression')
    require(kernel_compression == 'none' or out != OUT, 'Use a separate output for the gzip variant')
    hardware = json.loads((ROOT / 'kernel/j701f-hardware.json').read_text())
    inputs = dict(kernel=ROOT / 'build/kernel/panfrost/Image',
                  fdt=diagnostic_dir / 'exynos7870-j7velte-diagnostic.dtb',
                  initramfs=diagnostic_dir / 'initramfs.cpio.gz')
    reports = {'kernel': ROOT / 'build/kernel/panfrost/report.json',
               'fdt': diagnostic_dir / 'report.json',
               'initramfs': diagnostic_dir / 'initramfs-report.json'}
    for key, path in inputs.items():
        r = json.loads(reports[key].read_text())
        expected = r['sha256'] if key == 'initramfs' else r['files'][path.name]
        require(r['status'] in ('compiled', 'packaged') and sha(path) == expected, 'Input artifact changed: ' + key)
    image = inputs['kernel'].read_bytes()
    require(image[56:60] == b'ARM\x64', 'Kernel is not an ARM64 Image')
    offset, memory_size, flags = struct.unpack_from('<3Q', image, 8)
    require(not flags & 1, 'Big-endian Image unsupported')
    require(memory_size >= len(image), 'Image memory reservation is smaller than its file')
    planned = layout(memory_size, offset, inputs['fdt'].stat().st_size,
                     inputs['initramfs'].stat().st_size, hardware)
    out.mkdir(parents=True, exist_ok=True)
    # Local filenames avoid escaped paths or shell interpolation in the FIT source.
    for name, path in inputs.items():
        destination = out / (name + '.payload')
        data = path.read_bytes()
        if name == 'kernel' and kernel_compression == 'gzip':
            data = gzip.compress(data, compresslevel=9, mtime=0)
        destination.write_bytes(data)
    parts = []
    for name, kind in [('kernel', 'kernel'), ('fdt', 'flat_dt'), ('initramfs', 'ramdisk')]:
        parts.append(f'''        {name} {{
            description = "J701F diagnostic {name}";
            data = /incbin/("{name}.payload");
            type = "{kind}";
            arch = "arm64";
            os = "linux";
            compression = "{kernel_compression if name == 'kernel' else 'none'}";
            load = <0x{planned[name]:x}>;
''' + (f'            entry = <0x{planned[name]:x}>;\n' if name == 'kernel' else '') + '''            hash-1 { algo = "sha256"; };
        };''')
    its = '''/dts-v1/;
/ {
    description = "J701F Linux 6.15 RAM diagnostic";
    #address-cells = <1>;
    images {
''' + '\n'.join(parts) + '''
    };
    configurations {
        default = "conf-j701f-diagnostic";
        conf-j701f-diagnostic {
            description = "SM-J701F rev03 RAM diagnostics; no storage";
            compatible = "samsung,j7velte";
            kernel = "kernel";
            fdt = "fdt";
            ramdisk = "initramfs";
        };
    };
};
'''
    (out / 'mainline.its').write_text(its)
    mkimage = ROOT / 'build/kernel/uboot-j701f-diagnostic/mkimage'
    tool_report = json.loads((mkimage.parent / 'report.json').read_text())
    require(tool_report['status'] in ('compiled', 'host-tools-prepared') and
            sha(mkimage) == tool_report['files']['mkimage'], 'mkimage provenance differs')
    with (out / 'mkimage.log').open('w') as log:
        subprocess.run([str(mkimage), '-f', 'mainline.its', 'mainline.itb'], cwd=out,
                       env=dict(os.environ, SOURCE_DATE_EPOCH='1791331200', LC_ALL='C'),
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    blob = (out / 'mainline.itb').read_bytes()
    validation = verify(blob, inputs, planned, kernel_compression)
    require(len(blob) <= planned['source_limit'] - planned['targets_end'], 'FIT cannot fit after target regions in lower RAM')
    digest = hashlib.sha256(blob).digest()
    header = ('/* Generated by tools/build-mainline-fit.py; paired immutable payload. */\n'
              '#define J701F_FIT_BYTES '+str(len(blob))+'U\n'
              '#define J701F_TARGETS_END 0x'+format(planned['targets_end'],'x')+'UL\n'
              '#define J701F_SOURCE_LIMIT 0x'+format(planned['source_limit'],'x')+'UL\n'
              'static const unsigned char j701f_fit_sha256[32] = {'+
              ','.join('0x'+format(c,'02x') for c in digest)+'};\n')
    (out / 'j701f-fit-payload.h').write_text(header)
    (out / 'report.json').write_text(json.dumps(dict(
        status='packaged', phone_modified=False, hardware_boot_tested=False, flash_ready=False,
        inputs={key: dict(path=str(path.relative_to(ROOT)), sha256=sha(path)) for key, path in inputs.items()},
        layout=planned, validation=validation, fit_bytes=len(blob), fit_sha256=digest.hex(),
        kernel_compression=kernel_compression, kernel_uncompressed_bytes=len(image),
        kernel_payload_bytes=(out / 'kernel.payload').stat().st_size,
        mkimage_sha256=sha(mkimage), generated_header_sha256=sha(out / 'j701f-fit-payload.h'),
        limits=['Load addresses are an offline allocation plan; Samsung handoff must be observed.',
                'Whole FIT hash will be pinned into the diagnostic loader; not a firmware signature.',
                'No phone partitions or running kernel are changed.']), indent=2)+'\n')
    print('PASS: RAM FIT contents, hashes and measured-memory layout verified:', out / 'mainline.itb')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-compression', choices=('none', 'gzip'), default='none')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--diagnostic-dir', type=Path)
    args = parser.parse_args()
    out = args.output_dir or (OUT if args.kernel_compression == 'none' else ROOT / 'build/kernel/handoff-gzip')
    main(out, args.kernel_compression, args.diagnostic_dir)
