#!/usr/bin/env python3
"""Package a supervised diagnostic: embedded FIT, empty Android ramdisk, stub DTBH."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/handoff-embedded'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


recovery = module('embedded_recovery', 'recovery.py')
fit_tool = module('embedded_fit_tool', 'build-mainline-fit.py')
stub_tool = module('embedded_stub_tool', 'prepare-sboot-stub.py')


def checked_inputs(loader, fit, stub, loader_info):
    require = recovery.require
    require(loader_info['status'] == 'compiled' and
            loader_info['payload_source'] == 'embedded-relocated-rodata' and
            recovery.sha(loader) == loader_info['files']['u-boot.bin'] and
            recovery.sha(fit) == loader_info['paired_fit_sha256'], 'Unpaired embedded loader')
    require(loader[56:60] == b'ARM\x64', 'Not ARM64 Image')
    offset, memory_size, flags = struct.unpack_from('<3Q', loader, 8)
    require(offset == 0 and not flags & 1 and 0 < memory_size < 0x04000000,
            'Unsupported loader memory header')
    embedded = loader_info['embedded_fit']
    start, size = embedded['offset'], embedded['bytes']
    require(start % 8 == 0 and size == len(fit) and
            64 <= start < start + size <= embedded['image_copy_bytes'] <= len(loader) and
            embedded['monitor_bytes'] >= embedded['image_copy_bytes'] and
            memory_size >= embedded['monitor_bytes'], 'Embedded payload/monitor bounds')
    require(loader[start:start + size] == fit, 'Embedded payload bytes mismatch')
    fit_tool.fit_properties(fit)
    stub_tool.parse_table(stub)
    # Pin complete generated trees, not just the table's selection metadata.
    report = json.loads((stub_tool.OUT / 'report.json').read_text())
    require(report['status'] == 'offline-stub-prepared' and
            recovery.sha(stub) == report['sha256'] and
            stub == (stub_tool.OUT / 'stub-dtbh.img').read_bytes(), 'Stub table changed')


def package(old, loader, fit, stub, loader_info):
    checked_inputs(loader, fit, stub, loader_info)
    parts = dict(old.parts, kernel=loader, ramdisk=b'', dt=stub)
    header = bytearray(old.header)
    for offset, name in ((8, 'kernel'), (16, 'ramdisk'), (40, 'dt')):
        struct.pack_into('<I', header, offset, len(parts[name]))
    header[576:596] = recovery.Image.digest(parts)
    result = bytes(header)
    for name in ('kernel', 'ramdisk', 'second', 'dt'):
        data = parts[name]
        result += data + bytes(recovery.align(len(data), old.page) - len(data))
    return result + old.trailer


def verify(data, old, loader, fit, stub, loader_info):
    checked_inputs(loader, fit, stub, loader_info)
    candidate = recovery.Image(data)
    allowed = set(range(8, 12)) | set(range(16, 20)) | set(range(40, 44)) | set(range(576, 596))
    recovery.require(len(candidate.header) == len(old.header) and
                     all(a == b or i in allowed for i, (a, b) in
                         enumerate(zip(old.header, candidate.header))), 'Unexpected header change')
    for name, expected in [('kernel', loader), ('ramdisk', b''),
                           ('second', old.parts['second']), ('dt', stub)]:
        recovery.require(candidate.parts[name] == expected, 'Container component mismatch: ' + name)
    recovery.require(candidate.trailer == old.trailer, 'Original trailer changed')
    recovery.require(len(data) <= 77824 * 512, 'Exceeds measured RECOVERY capacity')
    return dict(empty_android_ramdisk=True, embedded_fit_verified=True,
                stub_dtbh_exact=True, model_revision_selection_preserved=True,
                original_load_addresses_page_and_cmdline=True, original_trailer_identical=True,
                fits_measured_recovery=True, sha1_container_digest_verified=True)


def main(out=OUT, loader_dir=None):
    out = out.resolve()
    loader_dir = (loader_dir or ROOT / 'build/kernel/uboot-j701f-embedded').resolve()
    recovery.require(out.is_relative_to(ROOT / 'build/kernel') and
                     loader_dir.is_relative_to(ROOT / 'build/kernel'), 'Paths must be under build/kernel')
    fit = (out / 'mainline.itb').read_bytes()
    fit_report = json.loads((out / 'report.json').read_text())
    recovery.require(fit_report['status'] == 'packaged' and
                     recovery.sha(fit) == fit_report['fit_sha256'], 'Stale FIT')
    loader = (loader_dir / 'u-boot.bin').read_bytes()
    info = json.loads((loader_dir / 'report.json').read_text())
    stub = (stub_tool.OUT / 'stub-dtbh.img').read_bytes()
    old = recovery.baseline()
    data = package(old, loader, fit, stub, info)
    checks = verify(data, old, loader, fit, stub, info)
    image = out / 'recovery-mainline-diagnostic.preview.img'
    recovery.write(image, data)
    recovery.json_write(out / 'container-report.json', dict(
        status='preview-packaged', packaging='embedded-fit-empty-ramdisk-stub-dtbh',
        phone_modified=False, hardware_boot_tested=False, flash_ready=False,
        image=str(image.relative_to(ROOT)), image_bytes=len(data), image_sha256=recovery.sha(data),
        original_image_sha256=recovery.sha(old.data), loader_sha256=recovery.sha(loader),
        fit_sha256=recovery.sha(fit), stub_sha256=recovery.sha(stub), validation=checks,
        limits=['Firmware acceptance, runtime relocation and Linux USB are not proven.',
                'Requires a separate supervised RECOVERY trial and verified rescue backup.']))
    print('PASS: embedded FIT, empty Android ramdisk, stub DTBH and original load parameters:', image)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fit-dir', type=Path, default=OUT)
    parser.add_argument('--loader-dir', type=Path)
    args = parser.parse_args()
    main(args.fit_dir, args.loader_dir)
