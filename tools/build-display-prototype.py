#!/usr/bin/env python3
"""Build opt-in display prototypes, never install or load them on the phone."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
WORK = Path('/tmp/j701f-kernel-build')
ARTIFACT = ROOT / 'build/kernel/ea8061s-prototype'
SOURCES = ROOT / 'tools/kmod/ea8061s'
MODULES = ('panel-j701f-ea8061s', 'j701f-display-info')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def build(worker):
    lock = ROOT / 'build/coord/locks/kbuild'
    require((lock / 'owner').is_file() and (lock / 'owner').read_text().strip() == worker,
            'Acquire the kbuild lock for this worker with tools/coord.sh first')
    expiry = int((lock / 'time').read_text()) + 60 * int((lock / 'ttl').read_text())
    require(expiry - time.time() >= 120, 'Renew kbuild lock; less than two minutes remain')

    inputs = json.loads((ROOT / 'kernel/inputs.json').read_text())['panfrost']
    src = WORK / 'sources' / inputs['directory']
    out = WORK / 'out/mainline-panfrost'
    require((src / 'Makefile').is_file(), 'Prepared mainline source tree missing')
    require((out / 'Module.symvers').is_file(), 'Build the configured kernel first')
    require((out / 'arch/arm64/boot/Image').is_file(), 'Compiled ARM64 Image missing')
    require(sha(out / '.config') == inputs['resolved_config_sha256'],
            'Shared resolved config does not match kernel/inputs.json')

    module_dir = ARTIFACT / 'module'
    module_dir.mkdir(parents=True, exist_ok=True)
    for name in ('Makefile', *(name + '.c' for name in MODULES)):
        shutil.copy2(SOURCES / name, module_dir / name)

    env = dict(os.environ, LC_ALL='C', KBUILD_BUILD_USER='burak',
               KBUILD_BUILD_HOST='j701f-builder', KBUILD_BUILD_VERSION='1',
               KBUILD_BUILD_TIMESTAMP='Thu Oct 8 00:00:00 UTC 2026')
    command = ['make', '-C', str(src), 'O=' + str(out), 'ARCH=arm64', 'LLVM=1',
               'M=' + str(module_dir), 'W=1', 'modules']
    report = dict(stage='EA8061S panel and read-only display-info prototypes',
                  time=datetime.now(timezone.utc).isoformat(), built=False,
                  panel_hardware_tested=False, phone_modified=False,
                  installed=False, worker=worker, make_command=command,
                  kernel_release=(out / 'include/config/kernel.release').read_text().strip(),
                  kernel_image_sha256=sha(out / 'arch/arm64/boot/Image'),
                  module_symvers_sha256=sha(out / 'Module.symvers'),
                  config_sha256=sha(out / '.config'),
                  requires_explicit_panel_parameter='allow_init=1',
                  limitations=['No active display device tree',
                               'Fixed initial gamma only; no calibrated brightness',
                               'DECON DMA, SysMMU integration and takeover untested'])
    report_path = ARTIFACT / 'report.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    with (ARTIFACT / 'build.log').open('w') as log:
        subprocess.run(command, env=env, check=True, stdout=log, stderr=subprocess.STDOUT)

    for name in MODULES:
        module = module_dir / (name + '.ko')
        data = module.read_bytes()
        require(data[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<H', data, 18)[0] == 183,
                name + ': not a little-endian AArch64 ELF module')
        shutil.copy2(module, ARTIFACT / module.name)
        report[name] = dict(source_sha256=sha(SOURCES / (name + '.c')),
                            module_sha256=sha(module), bytes=module.stat().st_size)
    report['built'] = True
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print('Built AArch64 modules:', ARTIFACT)
    print('No phone installation or loading performed. See build.log and report.json.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=('codex', 'claude'), default='codex')
    args = parser.parse_args()
    try:
        build(args.worker)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit('Display prototype build: ' + str(exc))
