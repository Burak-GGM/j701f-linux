#!/usr/bin/env python3
"""Create an uninstalled Samsung-container preview. No phone I/O or Odin tar."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/handoff'


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


recovery = module('recovery', 'recovery.py')
fit_tool = module('fit_tool', 'build-mainline-fit.py')


def package(old, loader, fit):
    recovery.require(loader[56:60] == b'ARM\x64', 'Loader is not an ARM64 Image')
    fit_tool.fit_properties(fit)
    header = bytearray(old.header)
    parts = dict(old.parts, kernel=loader, ramdisk=fit)
    struct.pack_into('<I', header, 8, len(loader))
    struct.pack_into('<I', header, 16, len(fit))
    header[576:596] = recovery.Image.digest(parts)
    result = bytes(header)
    for name in ('kernel', 'ramdisk', 'second', 'dt'):
        data = parts[name]
        result += data + bytes(recovery.align(len(data), old.page) - len(data))
    return result + old.trailer


def verify(data, old, loader, fit):
    candidate = recovery.Image(data)
    allowed = set(range(8, 12)) | set(range(16, 20)) | set(range(576, 596))
    recovery.require(all(a == b or i in allowed for i, (a, b) in
                         enumerate(zip(old.header, candidate.header))), 'Unexpected header change')
    for name, expected in [('kernel', loader), ('ramdisk', fit),
                           ('second', old.parts['second']), ('dt', old.parts['dt'])]:
        recovery.require(candidate.parts[name] == expected, 'Container component mismatch: ' + name)
    recovery.require(candidate.trailer == old.trailer, 'Original trailer changed')
    # Measured RECOVERY capacity; this is a preview, not installation approval.
    recovery.require(len(data) <= 77824 * 512, 'Preview exceeds measured RECOVERY capacity')
    return dict(original_dtbh_identical=True, original_header_except_sizes_digest=True,
                original_trailer_identical=True, fits_measured_recovery=True,
                sha1_container_digest_verified=True)


def main(out=OUT, loader_dir=None):
    out = out.resolve()
    loader_dir = (loader_dir or ROOT / 'build/kernel/uboot-j701f-diagnostic').resolve()
    recovery.require(out.is_relative_to(ROOT / 'build/kernel') and
                     loader_dir.is_relative_to(ROOT / 'build/kernel'), 'Paths must be under build/kernel')
    fit = (out / 'mainline.itb').read_bytes()
    fit_report = json.loads((out / 'report.json').read_text())
    loader = (loader_dir / 'u-boot.bin').read_bytes()
    loader_report = json.loads((loader_dir / 'report.json').read_text())
    fit_sha, loader_sha = recovery.sha(fit), recovery.sha(loader)
    recovery.require(fit_report['status'] == 'packaged' and fit_sha == fit_report['fit_sha256'], 'Stale FIT')
    recovery.require(loader_report['status'] == 'compiled' and
                     loader_sha == loader_report['files']['u-boot.bin'] and
                     fit_sha == loader_report['paired_fit_sha256'], 'Loader and FIT are not paired')
    old = recovery.baseline()
    data = package(old, loader, fit)
    checks = verify(data, old, loader, fit)
    image = out / 'recovery-mainline-diagnostic.preview.img'
    recovery.write(image, data)
    recovery.json_write(out / 'container-report.json', dict(
        status='preview-packaged', phone_modified=False, hardware_boot_tested=False, flash_ready=False,
        image=str(image.relative_to(ROOT)), image_bytes=len(data), image_sha256=recovery.sha(data),
        original_image_sha256=recovery.sha(old.data), loader_sha256=loader_sha, fit_sha256=fit_sha,
        validation=checks, limits=[
            'Host-only container preview. No Odin archive or flashing action is generated.',
            'S-BOOT acceptance, RAM pointers, relocation and Linux USB remain untested.',
            'RECOVERY in the filename describes the original container and size check; it was not written.',
            'A supervised trial needs the exact working rescue image and physical recovery access.']))
    print('PASS: paired Samsung-container preview verified. Not flash-ready:', image)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fit-dir', type=Path, default=OUT)
    parser.add_argument('--loader-dir', type=Path)
    args = parser.parse_args()
    main(args.fit_dir, args.loader_dir)
