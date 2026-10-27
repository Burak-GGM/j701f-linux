#!/usr/bin/env python3
"""Compile and verify the RAM-diagnostic J701F tree; no packaging or device I/O."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/j701f-diagnostic'
DTS = ROOT / 'kernel/dts/exynos7870-j7velte-diagnostic.dts'
EVIDENCE = ROOT / 'kernel/j701f-hardware.json'
DTB = OUT / 'exynos7870-j7velte-diagnostic.dtb'


def builder():
    spec = importlib.util.spec_from_file_location('kernel_builder', ROOT / 'tools/build-kernel.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prop(dtb, node, name, kind='x'):
    text = subprocess.check_output(['fdtget', '-t', kind, str(dtb), node, name], text=True).strip()
    return [int(c, 16) for c in text.split()] if kind == 'x' else text


def subnodes(dtb, node):
    return subprocess.check_output(['fdtget', '-l', str(dtb), node], text=True).split()


def intervals(reg, address_cells=2):
    width = address_cells + 1
    if len(reg) % width:
        raise ValueError('Invalid memory reg cell count')
    result = []
    for i in range(0, len(reg), width):
        base = 0
        for cell in reg[i:i + address_cells]:
            base = base << 32 | cell
        size = reg[i + address_cells]
        if size == 0 or base + size > 1 << 64:
            raise ValueError('Invalid memory region')
        result.append((base, base + size))
    return result


def verify(dtb, allow_emmc=False, allow_gpu=False, allow_wifi=False, allow_audio=False, allow_sd=False, allow_mfc=False):
    h = json.loads(EVIDENCE.read_text())
    if prop(dtb, '/', 'compatible', 's') != 'samsung,j7velte samsung,exynos7870':
        raise ValueError('Wrong board compatible')
    memory = prop(dtb, '/memory@40000000', 'reg')
    expected_memory = sum([h['memory'][key] for key in sorted(h['memory'])], [])
    if memory != expected_memory:
        raise ValueError('Memory differs from the measured J701F banks')
    banks = intervals(memory)
    reservations = []
    for node in subnodes(dtb, '/reserved-memory'):
        path = '/reserved-memory/' + node
        reservations.extend(intervals(prop(dtb, path, 'reg')))
        # Claude 2026-10-09: a reusable shared-dma-pool (CMA area for one device) is the
        # one kind of region that must not be no-map.
        def has(name):
            try:
                return prop(dtb, path, name) == []
            except subprocess.CalledProcessError:
                return False
        pool = has('reusable') and prop(dtb, path, 'compatible', 's') == 'shared-dma-pool'
        if not pool and not has('no-map'):
            raise ValueError('Reserved region must be no-map')
    for reg in h['reservations'].values():
        for start, end in intervals(reg):
            if not any(a <= start and end <= b for a, b in reservations):
                raise ValueError('Measured vendor reservation is unprotected')
    if not any(a <= 0x46000000 and 0x47000000 <= b for a, b in reservations):
        raise ValueError('Vendor debug envelope is unprotected')
    for i, (start, end) in enumerate(sorted(reservations)):
        if not any(a <= start and end <= b for a, b in banks):
            raise ValueError('Reservation lies outside measured RAM')
        if i and sorted(reservations)[i - 1][1] > start:
            raise ValueError('Overlapping reservations')
    for node in ('mmc@13540000', 'mmc@13550000', 'mmc@13560000', 'gpu@11400000'):
        # eMMC enumeration is an explicit later stage, after a verified RAM/USB boot.
        if allow_emmc and node == 'mmc@13540000':
            continue
        # GPU bring-up is a later explicit stage; registers/IRQs/supply are still checked below.
        if allow_gpu and node == 'gpu@11400000':
            continue
        # SDIO Wi-Fi (mmc1) is its own explicit stage; the SD slot (mmc2) stays off.
        if allow_wifi and node == 'mmc@13550000':
            continue
        # Claude 2026-10-09: the microSD slot (mmc2) is its own explicit stage.
        if allow_sd and node == 'mmc@13560000':
            continue
        if prop(dtb, '/soc@0/' + node, 'status', 's') != 'disabled':
            raise ValueError('First diagnostic must disable storage and GPU')
    for node in ('clock-controller@11460000', 'clock-controller@148d0000',
                 'clock-controller@144d0000', 'clock-controller@12cb0000'):
        if allow_gpu and node == 'clock-controller@11460000':
            continue
        # Claude 2026-10-09: the audio stage needs CMU DISPAUD (audio PLL, I2S, mixer clocks).
        if allow_audio and node == 'clock-controller@148d0000':
            continue
        # Claude 2026-10-09: hardware video codec stage; its power domain is on at boot (measured).
        if allow_mfc and node == 'clock-controller@12cb0000':
            continue
        if prop(dtb, '/soc@0/' + node, 'status', 's') != 'disabled':
            raise ValueError('First diagnostic must disable unused powered-domain clocks')
    gpu = '/soc@0/gpu@11400000'
    live_gpu = h['nodes']['mali@11400000']
    if prop(dtb, gpu, 'reg') != [live_gpu['reg'][1], live_gpu['reg'][2]]:
        raise ValueError('GPU registers differ from the measured board')
    if prop(dtb, gpu, 'interrupts')[1::3] != live_gpu['interrupts'][1::3]:
        raise ValueError('GPU interrupt numbers differ from the measured board')
    if prop(dtb, gpu, 'interrupt-names', 's') != 'job mmu gpu':
        raise ValueError('GPU interrupt ordering/names differ from the modern binding')
    buck2 = '/soc@0/i2c@10510000/pmic@66/regulators/buck2'
    if prop(dtb, gpu, 'mali-supply') != prop(dtb, buck2, 'phandle'):
        raise ValueError('GPU supply differs from the audited vendor BUCK2 mapping')
    for name in ('cpu_on', 'cpu_off', 'cpu_suspend'):
        if prop(dtb, '/psci', name) != h['nodes']['psci'][name]:
            raise ValueError('PSCI call differs from working firmware')
    if prop(dtb, '/psci', 'method', 's') != 'smc':
        raise ValueError('Unexpected PSCI conduit')
    for regulator, props in h['regulators'].items():
        node = '/soc@0/i2c@10510000/pmic@66/regulators/' + regulator
        for key in ('regulator-min-microvolt', 'regulator-max-microvolt'):
            if prop(dtb, node, key) != props[key]:
                raise ValueError('Regulator constraint differs from live board')
    chosen = subprocess.check_output(['fdtget', '-p', str(dtb), '/chosen'], text=True).split()
    # Address translation for a firmware framebuffer child needs these three.
    if set(chosen) - {'#address-cells', '#size-cells', 'ranges'} != {'stdout-path', 'bootargs'}:
        raise ValueError('Unexpected chosen properties: avoid stale initrd pointers or identifiers')
    if prop(dtb, '/soc@0/system-controller@10480000/reboot-mode', 'mode-normal') != [0x12345670]:
        raise ValueError('Normal restart reason differs from the vendor recovery return path')
    if 'root=' in prop(dtb, '/chosen', 'bootargs', 's'):
        raise ValueError('First diagnostic must run from initramfs')
    return dict(memory_banks=[[hex(a), hex(b)] for a, b in banks],
                reserved_regions=len(reservations), storage_disabled=True, gpu_disabled=True,
                unused_domain_clocks_disabled=True,
                gpu_registers_interrupts_match_live=True, disabled_gpu_supply_is_buck2=True,
                psci_matches_live=True, regulator_constraints_match_live=True)


def build(dts=DTS, out=OUT, allow_emmc=False, allow_gpu=False, allow_wifi=False, allow_audio=False, allow_sd=False, allow_mfc=False,
          kernel_profile='panfrost'):
    dts, out = dts.resolve(), out.resolve()
    if not dts.is_relative_to(ROOT / "kernel/dts") or not out.is_relative_to(ROOT / "build/kernel"):
        raise ValueError("Unexpected diagnostic source/output path")
    dtb = out / "exynos7870-j7velte-diagnostic.dtb"
    module = builder()
    if kernel_profile not in ('panfrost', 'panfrost-7.2'):
        raise ValueError('Unsupported kernel profile')
    src, entry = module.source(kernel_profile)
    out.mkdir(parents=True, exist_ok=True)
    report = dict(status='preparing', phone_modified=False, hardware_boot_tested=False,
                  flash_ready=False, source=entry, kernel_profile=kernel_profile,
                  board_source=str(dts.relative_to(ROOT)))
    module.json_write(out / 'report.json', report)
    try:
        preprocessed = out / 'board.preprocessed.dts'
        deps = out / 'board.dependencies'
        with preprocessed.open('w') as output:
            subprocess.run(['gcc', '-E', '-nostdinc', '-undef', '-D__DTS__',
                            '-x', 'assembler-with-cpp', '-MD', '-MF', str(deps),
                            '-I', str(ROOT / 'kernel/dts'),
                            '-I', str(src / 'arch/arm64/boot/dts/exynos'),
                            '-I', str(src / 'scripts/dtc/include-prefixes'),
                            '-I', str(src / 'include'), str(dts)], stdout=output, check=True)
        with (out / 'dtc.log').open('w') as log:
            subprocess.run(['dtc', '-@', '-I', 'dts', '-O', 'dtb', '-o', str(dtb),
                            str(preprocessed)], stderr=log, check=True)
        validation = verify(dtb, allow_emmc, allow_gpu, allow_wifi, allow_audio, allow_sd, allow_mfc)
        input_paths = deps.read_text().replace('\\\n', ' ').split(':', 1)[1].split()
        report.update(status='compiled', validation=validation,
                      compiler=subprocess.check_output(['dtc', '--version'], text=True).strip(),
                      evidence_sha256=module.sha(EVIDENCE),
                      inputs={str(Path(p)): module.sha(Path(p)) for p in input_paths},
                      files={p.name: module.sha(p) for p in out.iterdir()
                             if p.is_file() and p.name != 'report.json'},
                      remaining=['USB VDD33=LDO8 needs board wiring confirmation.',
                                 'Samsung load offset/FDT handoff needs a tested second-stage path.',
                                 'No hardware boot or complete DT schema validation yet.',
                                 'Display, touch, Wi-Fi, eMMC and GPU are later stages.'])
        module.json_write(out / 'report.json', report)
        print('PASS: J701F diagnostic DT compiled; measured memory/PSCI/regulator checks passed.')
        print('Not flashed or boot-tested. dtb:', dtb)
    except Exception as error:
        report.update(status='failed', error=str(error))
        module.json_write(out / 'report.json', report)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', type=Path, help='Verify an existing diagnostic DTB instead of building')
    parser.add_argument('--source', type=Path, default=DTS)
    parser.add_argument('--output-dir', type=Path, default=OUT)
    parser.add_argument('--kernel-profile', choices=('panfrost', 'panfrost-7.2'), default='panfrost')
    parser.add_argument('--allow-emmc', action='store_true',
                        help='Permit an enabled mmc0 (eMMC enumeration stage); SD/SDIO and GPU stay disabled')
    parser.add_argument('--allow-gpu', action='store_true',
                        help='Permit an enabled Mali GPU and CMU G3D (Panfrost stage)')
    parser.add_argument('--allow-wifi', action='store_true',
                        help='Permit an enabled mmc1 (SDIO Wi-Fi stage)')
    parser.add_argument('--allow-mfc', action='store_true',
                        help='Permit an enabled CMU MFCMSCL (hardware video codec stage)')
    parser.add_argument('--allow-sd', action='store_true',
                        help='Permit an enabled mmc2 (microSD slot stage)')
    parser.add_argument('--allow-audio', action='store_true',
                        help='Permit an enabled CMU DISPAUD (audio stage)')
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify, args.allow_emmc, args.allow_gpu, args.allow_wifi, args.allow_audio, args.allow_sd, args.allow_mfc), indent=2))
    else:
        build(args.source, args.output_dir, args.allow_emmc, args.allow_gpu, args.allow_wifi, args.allow_audio,
              args.allow_sd, args.allow_mfc, args.kernel_profile)
