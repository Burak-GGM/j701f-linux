#!/usr/bin/env python3
"""Build the RAM-only display trial; never install or change phone/BOOT."""
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/display-runtime'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    lock = ROOT / 'build/coord/locks/kbuild'
    assert (lock / 'owner').read_text().strip() == 'codex', 'Acquire Codex kbuild lock'
    assert int((lock / 'time').read_text()) + 60 * int((lock / 'ttl').read_text()) > time.time() + 120
    src = Path('/tmp/j701f-kernel-build/sources/linux-7.1.13')
    kbuild = Path('/tmp/j701f-kernel-build/out/mainline-panfrost')
    config = json.loads((ROOT / 'kernel/inputs.json').read_text())['panfrost']
    assert sha(kbuild / '.config') == config['resolved_config_sha256']
    assert sha(kbuild / 'arch/arm64/boot/Image') == sha(ROOT / 'build/kernel/panfrost/Image')
    for option in ('CONFIG_OF_DYNAMIC=y', 'CONFIG_OF_OVERLAY=y'):
        assert option in (kbuild / '.config').read_text().splitlines()
    OUT.mkdir(parents=True, exist_ok=True)
    overlay = OUT / 'display.dtbo'
    run('dtc', '-@', '-I', 'dts', '-O', 'dtb', '-o', overlay,
        ROOT / 'kernel/dts/j701f-display-runtime.dtso')
    slot = json.loads((ROOT / 'build/kernel/boot-slot.json').read_text())
    handoff = ROOT / 'build/kernel' / ('handoff-' + slot['boot_candidate'])
    paired = json.loads((handoff / 'report.json').read_text())['inputs']
    base = ROOT / paired['fdt']['path']
    assert sha(base) == paired['fdt']['sha256'], 'Stale baseline DTB'
    assert paired['kernel']['sha256'] == sha(ROOT / 'build/kernel/panfrost/Image'), 'Baseline kernel changed'
    physical = OUT / 'physical-base.dtb'
    shutil.copy2(base, physical)
    # Same property removal as the guarded kernel loader; DT overlays alone
    # do not implement deletion of a base-tree property.
    run('fdtput', '-d', physical, '/soc@0/display-controller@14830000', 'iommus')
    merged = OUT / 'merged-native.dtb'
    run('fdtoverlay', '-i', physical, '-o', merged, overlay)
    spec = importlib.util.spec_from_file_location('native', ROOT / 'tools/validate-display-trial.py')
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    validation = native.validate(merged)
    module = OUT / 'module'
    module.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'tools/kmod/ea8061s/j701f-display-overlay.c', module)
    shutil.copy2(ROOT / 'tools/kmod/ea8061s/j701f-panel-status.c', module)
    (module / 'Makefile').write_text('obj-m += j701f-display-overlay.o\nobj-m += j701f-panel-status.o\n')
    blob = overlay.read_bytes()
    lines = [', '.join(f'0x{x:02x}' for x in blob[i:i+16]) for i in range(0, len(blob), 16)]
    (module / 'display-overlay-blob.h').write_text(
        '/* Generated from validated display.dtbo. */\n'
        'static const unsigned char display_overlay_blob[] __aligned(8) = {\n'
        + ',\n'.join(lines) + '\n};\n')
    env = dict(os.environ, LC_ALL='C', KBUILD_BUILD_USER='burak',
               KBUILD_BUILD_HOST='j701f-builder', KBUILD_BUILD_VERSION='1',
               KBUILD_BUILD_TIMESTAMP='Thu Oct 8 00:00:00 UTC 2026')
    with (OUT / 'build.log').open('w') as log:
        run('make', '-C', src, 'O=' + str(kbuild), 'ARCH=arm64', 'LLVM=1',
            'M=' + str(module), 'W=1', 'modules', env=env, stdout=log, stderr=subprocess.STDOUT)
    ko = OUT / 'j701f-display-overlay.ko'
    shutil.copy2(module / ko.name, ko)
    shutil.copy2(module / 'j701f-panel-status.ko', OUT)
    assert ko.read_bytes()[:6] == b'\x7fELF\x02\x01'
    symbols = subprocess.check_output(['readelf', '-sW', str(ko)], text=True)
    blob_symbol = re.search(r'^\s*\d+:\s*([0-9a-f]+)\s+\d+\s+OBJECT\s+LOCAL\s+DEFAULT\s+\d+\s+display_overlay_blob$',
                            symbols, re.MULTILINE)
    assert blob_symbol and int(blob_symbol.group(1), 16) % 8 == 0, 'FDT pointer must be 8-byte aligned'
    report = dict(status='compiled', installed=False, hardware_verified=False,
                  source_sha256=sha(ROOT / 'tools/kmod/ea8061s/j701f-display-overlay.c'),
                  overlay_source_sha256=sha(ROOT / 'kernel/dts/j701f-display-runtime.dtso'),
                  overlay_sha256=sha(overlay), module_sha256=sha(ko),
                  overlay_blob_alignment=8,
                  status_module_sha256=sha(OUT / 'j701f-panel-status.ko'),
                  status_source_sha256=sha(ROOT / 'tools/kmod/ea8061s/j701f-panel-status.c'),
                  kernel_image_sha256=sha(kbuild / 'arch/arm64/boot/Image'),
                  config_sha256=sha(kbuild / '.config'),
                  module_symvers_sha256=sha(kbuild / 'Module.symvers'),
                  base_dtb_sha256=sha(base), merged_dtb_sha256=sha(merged),
                  baseline_slot=slot['boot_candidate'],
                  baseline_boot_sha256=slot['boot_partition_sha256'],
                  validation=validation,
                  teardown='Reboot only; BOOT and all partitions remain unchanged')
    notes = subprocess.check_output(['readelf', '-n', str(kbuild / 'vmlinux')], text=True)
    report['kernel_build_id'] = re.search(r'Build ID: ([0-9a-f]+)', notes).group(1)
    (OUT / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: RAM-only native display overlay built and merged tree validated; no phone changes')


if __name__ == '__main__':
    main()
