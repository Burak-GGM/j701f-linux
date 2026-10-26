#!/usr/bin/env python3
"""Record local, read-only GPU observations. Does not create or enable OPPs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def observations(text):
    attributes = {}
    name = None
    for line in text.splitlines():
        if line.startswith('ATTRIBUTE='):
            name = line.removeprefix('ATTRIBUTE=')
            require(name not in attributes, 'Duplicate GPU attribute')
            attributes[name] = []
        elif line.startswith('GPU_PATH='):
            require(line.endswith('/11400000.mali'), 'Unexpected GPU device')
        elif name:
            attributes[name].append(line)
    for name in ('clock', 'vol', 'power_state', 'asv_table', 'dvfs_table'):
        require(name in attributes, 'Missing GPU observation: ' + name)
    scalar = lambda name: int('\n'.join(attributes[name]).strip())
    require(scalar('power_state') in (0, 1), 'Unknown GPU power state')
    rows = []
    for line in attributes['asv_table']:
        if not line.strip() or line.startswith('GPU,'):
            continue
        require(re.fullmatch(r'\s*\d+\s*(,\s*\d+\s*){7}', line) is not None, 'Malformed ASV table row')
        fields = [int(part.strip()) for part in line.split(',')]
        mhz, microvolt, low, high, stay, mif, interconnect, cpu = fields
        require(0 < mhz <= 2000 and 0 <= low <= high <= 100 and stay > 0, 'Invalid ASV table values')
        rows.append(dict(frequency_hz=mhz * 1000000, microvolt=microvolt,
                         vendor_mif_khz=mif, vendor_interconnect_khz=interconnect,
                         vendor_cpu_min_khz=cpu))
    require(rows and len({r['frequency_hz'] for r in rows}) == len(rows), 'Empty/duplicate ASV frequencies')
    frequencies = [int(c) * 1000000 for c in '\n'.join(attributes['dvfs_table']).split()]
    require(frequencies == [r['frequency_hz'] for r in rows], 'ASV and DVFS tables disagree')
    return dict(current_clock_mhz=scalar('clock'), current_microvolt=scalar('vol'),
                power_on=bool(scalar('power_state')), vendor_asv_rows=rows)


def main():
    capture = ROOT / 'build/kernel/phone-gpu-live.txt'
    result = observations(capture.read_text())
    spec = importlib.util.spec_from_file_location('board', ROOT / 'tools/j701f-board-evidence.py')
    board = importlib.util.module_from_spec(spec); spec.loader.exec_module(board)
    properties = board.capture(board.CAPTURE)
    handles = {board.cells(value)[0]: key.removesuffix('/phandle') for key, value in properties.items()
               if key.endswith('/phandle')}
    gpu = 'mali@11400000'
    domain = handles[board.cells(properties[gpu + '/samsung,power-domain'])[0]]
    require(domain == 'pd-g3d@10484000', 'Unexpected GPU power domain')
    config = (ROOT / 'kernel/configs/vendor-running.config').read_text()
    require('CONFIG_MALI_R28P0=y\n' in config, 'Audit the selected vendor driver revision first')
    source_dir = ROOT / 'build/kernel/vendor-gpu-reference-r28p0'
    source = source_dir / 'gpu_exynos7870.c'
    provenance = json.loads((source_dir / 'provenance.json').read_text())
    source_key = 'drivers/gpu/arm/t83x/r28p0/platform/exynos/gpu_exynos7870.c'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    require(source_hash == provenance['files'][source_key], 'Vendor GPU reference changed')
    require('regulator_get(NULL, "BUCK2")' in source.read_text(), 'Unexpected vendor GPU supply lookup')
    hardware = json.loads((ROOT / 'kernel/j701f-hardware.json').read_text())
    regulator = hardware['regulators']['buck2']
    minimum, maximum = regulator['regulator-min-microvolt'][0], regulator['regulator-max-microvolt'][0]
    require(minimum <= result['current_microvolt'] <= maximum and
            all(minimum <= r['microvolt'] <= maximum for r in result['vendor_asv_rows']),
            'Observed voltage exceeds measured regulator constraints')
    pmic = 'hsi2c@10510000/s2mpu05_pmic@66/'
    result.update(
        observed_sysfs_sha256=hashlib.sha256(capture.read_bytes()).hexdigest(),
        live_dt_capture_sha256=hashlib.sha256(board.CAPTURE.read_bytes()).hexdigest(),
        vendor_source=provenance['source'], vendor_gpu_source_sha256=source_hash,
        vendor_driver_revision='r28p0', vendor_supply_lookup='BUCK2',
        modern_supply_property='mali-supply', proposed_regulator_label='vdd_buck2',
        gpu_reg_cells=board.cells(properties[gpu + '/reg']),
        gpu_interrupt_cells=board.cells(properties[gpu + '/interrupts']),
        vendor_power_domain=dict(node=domain, reg_cells=board.cells(properties[domain + '/reg'])),
        vendor_buck2_enable_pin=properties[pmic + 'buck2en_pin'].rstrip(b'\0').decode(),
        vendor_g3d_enable=board.cells(properties[pmic + 'g3d_en']),
        limits=['This is one handset/vendor-kernel snapshot; not universal J701F OPPs.',
                'Vendor ASV entries are observations, not a mainline voltage/frequency policy.',
                'Voltage margins, PMIC external enable, power sequencing and memory QoS still require a port.',
                'BUCK2 mapping is source/runtime evidence, not independent physical wiring measurement.',
                'No mainline GPU probe, render node, acceleration or power transition was tested.'])
    destination = ROOT / 'kernel/j701f-gpu-evidence.json'
    destination.write_text(json.dumps(result, indent=2)+'\n')
    print('Saved measured GPU tables and source mapping; GPU remains disabled:', destination)


if __name__ == '__main__':
    main()
