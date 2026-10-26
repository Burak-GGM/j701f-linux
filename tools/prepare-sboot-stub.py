#!/usr/bin/env python3
"""Prepare an offline J701F S-BOOT stub table; no phone I/O or boot image."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/sboot-stub'
PAGE = 2048
BASELINE_DTBH_SHA = 'afbf297a9ea000c596d68471852b16678251b61e21eb088040510a11714e8191'
SELECTION = [(7870, 0x50a6, 0x217584da, 0, 0, 0x20),
             (7870, 0x50a6, 0x217584da, 1, 2, 0x20),
             (7870, 0x50a6, 0x217584da, 3, 255, 0x20)]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def align(n):
    return (n + PAGE - 1) // PAGE * PAGE


def parse_table(data):
    require(len(data) >= PAGE and len(data) % PAGE == 0, 'DTBH table size/alignment')
    require(data[:4] == b'DTBH' and struct.unpack_from('<II', data, 4) == (2, 3),
            'Expected measured DTBH v2 with three revisions')
    require(not any(data[108:PAGE]), 'Nonzero DTBH header padding')
    entries = []
    cursor = PAGE
    for i, wanted in enumerate(SELECTION):
        entry = struct.unpack_from('<8I', data, 12 + i * 32)
        require(entry[:5] + entry[7:] == wanted, 'Changed model/revision selection keys')
        offset, size = entry[5:7]
        require(offset == cursor and size > 0 and size % PAGE == 0 and
                offset + size <= len(data), 'DTBH payload bounds/order')
        blob = data[offset:offset + size]
        require(len(blob) >= 40, 'Truncated stub DTB')
        magic, total = struct.unpack_from('>II', blob)
        require(magic == 0xd00dfeed and 40 <= total <= size, 'DTB header/length')
        require(not any(blob[total:]), 'Nonzero DTB tail padding')
        entries.append((entry, blob[:total]))
        cursor = offset + size
    require(cursor == len(data), 'Unexpected trailing DTBH payload')
    return entries


def pack_table(blobs):
    require(len(blobs) == 3, 'Three stub trees required')
    header = bytearray(b'DTBH' + struct.pack('<II', 2, 3))
    cursor = PAGE
    payload = bytearray()
    for keys, blob in zip(SELECTION, blobs):
        size = align(len(blob))
        header.extend(struct.pack('<8I', *keys[:5], cursor, size, keys[5]))
        payload.extend(blob + bytes(size - len(blob)))
        cursor += size
    result = bytes(header) + bytes(PAGE - len(header)) + bytes(payload)
    parse_table(result)
    return result


def stub_source(low, high):
    # Selection metadata is copied from the known table. Chosen and zero-sized
    # memory placeholders are for S-BOOT overlays, not fabricated bootargs.
    return f'''/dts-v1/;
/ {{
    compatible = "samsung,exynos7870";
    #address-cells = <2>;
    #size-cells = <1>;
    model_info-chip = <7870>;
    model_info-platform = "android";
    model_info-subtype = "samsung";
    model_info-hw_rev = <{low}>;
    model_info-hw_rev_end = <{high}>;
    chosen {{ }};
    memory@40000000 {{ device_type = "memory"; reg = <0 0x40000000 0>; }};
    memory@80000000 {{ device_type = "memory"; reg = <0 0x80000000 0>; }};
}};
'''


def prop(path, node, name, kind='s'):
    return subprocess.check_output(['fdtget', '-t', kind, str(path), node, name], text=True).strip()


def prepare():
    original = (ROOT / 'extracted/dtb').read_bytes()
    require(hashlib.sha256(original).hexdigest() == BASELINE_DTBH_SHA, 'Baseline DTBH hash changed')
    parse_table(original)
    OUT.mkdir(parents=True, exist_ok=True)
    blobs = []
    for i, keys in enumerate(SELECTION):
        source, dtb = OUT / f'stub-{i}.dts', OUT / f'stub-{i}.dtb'
        source.write_text(stub_source(keys[3], keys[4]))
        subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(dtb), str(source)], check=True)
        require(prop(dtb, '/', 'model_info-chip', 'i') == '7870', 'Wrong chip metadata')
        require(prop(dtb, '/', 'model_info-hw_rev', 'i') == str(keys[3]) and
                prop(dtb, '/', 'model_info-hw_rev_end', 'i') == str(keys[4]), 'Wrong revision metadata')
        names = subprocess.check_output(['fdtget', '-p', str(dtb), '/chosen'], text=True).strip()
        require(not names, 'Stub must not fake chosen properties')
        require(prop(dtb, '/memory@40000000', 'reg', 'x') == '0 40000000 0' and
                prop(dtb, '/memory@80000000', 'reg', 'x') == '0 80000000 0', 'Wrong memory placeholders')
        blobs.append(dtb.read_bytes())
    packed = pack_table(blobs)
    output = OUT / 'stub-dtbh.img'; output.write_bytes(packed)
    report = dict(status='offline-stub-prepared', phone_modified=False, flash_ready=False,
                  image_bytes=len(packed), sha256=hashlib.sha256(packed).hexdigest(),
                  original_dtbh_sha256=BASELINE_DTBH_SHA, selection_keys_preserved=True,
                  empty_chosen=True, zero_size_memory_placeholders=True,
                  official_source='https://docs.u-boot.org/en/latest/board/samsung/exynos-mobile/exynos7870.html',
                  pinned_source_document='doc/board/samsung/exynos-mobile/exynos7870.rst in U-Boot v2026.01',
                  changes_from_pinned_example=['Include measured lower RAM base 0x40000000 and upper base 0x80000000; omit absent third bank', 'Keep all three exact J701F DTBH selection records and their model metadata'],
                  next_step='Embed paired FIT in a relocated loader and validate its source range; Android ramdisk must be empty for that variant.',
                  limits=['This is only a DT table, not a flashable boot image.',
                          'Existing loader requires linux,initrd-start/end and will refuse a no-ramdisk image.',
                          'S-BOOT overlays, board matching and firmware acceptance are not hardware-proven.',
                          'Neither rejected candidate may be retried unchanged.'])
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: three compiled stub DTBs and exact selection metadata; offline table only:', output)


if __name__ == '__main__':
    prepare()
