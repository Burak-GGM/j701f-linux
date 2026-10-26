#!/usr/bin/env python3
"""Validate the isolated native display trial, never access the phone.

Checks topology, physical DMA, reserved RAM, compiled opt-in parameter and
panel/probe build hashes. Success means prepared software, not visible output.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(dtb, handoff=None):
    dtb = dtb.resolve()
    require(dtb.is_relative_to(ROOT / 'build/kernel'), 'DTB must be a build/kernel artifact')
    spec = importlib.util.spec_from_file_location('board_dtb', ROOT / 'tools/build-j701f-dtb.py')
    board = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(board)
    # Preserve the existing board/memory/PMIC/PSCI verification too.
    board.verify(dtb, allow_emmc=True, allow_gpu=True, allow_wifi=True,
                 allow_audio=True, allow_sd=True, allow_mfc=True)
    prop = lambda node, name, kind='x': board.prop(dtb, node, name, kind)
    properties = lambda node: subprocess.check_output(
        ['fdtget', '-p', str(dtb), node], text=True).split()
    checks = []

    def check(condition, label):
        require(condition, label)
        checks.append(label)

    decon = '/soc@0/display-controller@14830000'
    dsi = '/soc@0/dsi@14800000'
    mmu = '/soc@0/iommu@14860000'
    panel = dsi + '/panel@0'
    regs = '/soc@0/i2c@10510000/pmic@66/regulators/'
    check(prop('/', 'compatible', 's') == 'samsung,j7velte samsung,exynos7870', 'J701F board')
    check(prop(decon, 'status', 's') == prop(dsi, 'status', 's') == 'okay', 'DECON and DSIM enabled')
    check(prop('/chosen/framebuffer@67000000', 'status', 's') == 'disabled',
          'simple-framebuffer device disabled')
    check(prop(mmu, 'status', 's') == 'disabled' and 'iommus' not in properties(decon),
          'physical DMA with no display IOMMU attachment')
    check(prop(decon, 'reg') == [0x14830000, 0x8000] and prop(dsi, 'reg') == [0x14800000, 0x100],
          'measured controller register ranges')
    check(prop(panel, 'compatible', 's') == 'samsung,j701f-ea8061s', 'opt-in experimental panel')
    check(prop(panel, 'vddio-supply') == prop(regs + 'ldo30', 'phandle') and
          prop(panel, 'vci-supply') == prop(regs + 'ldo29', 'phandle'), 'panel supply phandles')
    gpio = prop('/__symbols__', 'gpd3', 's')
    check(gpio == '/soc@0/pinctrl@139b0000/gpd3-gpio-bank', 'measured gpd3 bank')
    check(prop(panel, 'reset-gpios') == prop(gpio, 'phandle') + [4, 1],
          'active-low gpd3-4 reset')
    check([prop(dsi, 'samsung,' + name + '-clock-frequency')[0]
           for name in ('pll', 'burst', 'esc')] == [26000000, 477000000, 16000000],
          '26MHz reference, 477MHz HS request, 16MHz escape request')
    output = dsi + '/ports/port@1/endpoint'
    endpoint = panel + '/port/endpoint'
    check(prop(output, 'data-lanes') == [1, 2, 3, 4], 'four DSI lanes')
    check(prop(output, 'remote-endpoint') == prop(endpoint, 'phandle') and
          prop(endpoint, 'remote-endpoint') == prop(output, 'phandle'), 'reciprocal panel graph')
    # Physical framebuffer RAM and the adjacent ramoops must survive takeover.
    check(prop('/reserved-memory/bootloader-fb@67000000', 'reg') == [0, 0x67000000, 0xa00000],
          'firmware framebuffer reservation retained')
    check(prop('/ramoops@67900000', 'reg') == [0, 0x67900000, 0x100000], 'ramoops retained')

    kernel = ROOT / 'build/kernel/panfrost'
    report = json.loads((kernel / 'report.json').read_text())
    check(report['status'] == 'compiled' and sha(kernel / 'Image') == report['image']['sha256'],
          'kernel Image matches successful build report')
    check(b'samsung_dsim.j701f_vendor_timing\0' in (kernel / 'Image').read_bytes(),
          'compiled explicit DSIM trial parameter')
    check('# CONFIG_EXYNOS_IOMMU is not set' in (kernel / 'config').read_text().splitlines(),
          'current kernel retains disabled Exynos IOMMU')
    artifact = ROOT / 'build/kernel/ea8061s-prototype'
    modules = json.loads((artifact / 'report.json').read_text())
    check(modules['built'] and modules['kernel_release'] == report['kernel_release'],
          'matching panel/probe kernel release')
    check(modules.get('kernel_image_sha256') == sha(kernel / 'Image')
          and modules['config_sha256'] == sha(kernel / 'config'),
          'panel/probe build pinned to current kernel Image and config')
    for name in ('panel-j701f-ea8061s', 'j701f-display-info'):
        check(sha(artifact / (name + '.ko')) == modules[name]['module_sha256'] and
              sha(ROOT / 'tools/kmod/ea8061s' / (name + '.c')) == modules[name]['source_sha256'],
              name + ' module and source hashes')
    fit_hash = None
    if handoff is not None:
        handoff = handoff.resolve()
        require(handoff.is_relative_to(ROOT / 'build/kernel'), 'FIT directory must be under build/kernel')
        fit_report = json.loads((handoff / 'report.json').read_text())
        fit_blob = (handoff / 'mainline.itb').read_bytes()
        spec = importlib.util.spec_from_file_location('display_fit', ROOT / 'tools/build-mainline-fit.py')
        fit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fit)
        inputs = {}
        for name in ('kernel', 'fdt', 'initramfs'):
            info = fit_report['inputs'][name]
            path = (ROOT / info['path']).resolve()
            require(path.is_relative_to(ROOT / 'build/kernel'), 'FIT input outside build/kernel')
            require(sha(path) == info['sha256'], 'Stale FIT input: ' + name)
            inputs[name] = path
        check(inputs['kernel'] == (kernel / 'Image').resolve() and inputs['fdt'] == dtb,
              'FIT references this exact current kernel and trial DTB')
        fit_hash = hashlib.sha256(fit_blob).hexdigest()
        check(fit_hash == fit_report['fit_sha256'] and len(fit_blob) == fit_report['fit_bytes'],
              'FIT bytes match package report')
        fit.verify(fit_blob, inputs, fit_report['layout'], fit_report['kernel_compression'])
        checks.append('actual FIT payloads, hashes and load fields verified')
    result = dict(stage='isolated native display trial', status='software-validated',
                  dtb=str(dtb.relative_to(ROOT)), dtb_sha256=sha(dtb),
                  kernel_image_sha256=sha(kernel / 'Image'), checks=checks,
                  fit_sha256=fit_hash, packaged_fit_verified=handoff is not None,
                  validation_scope='DTB and current kernel/modules' if handoff is None else
                      'DTB, current kernel/modules and actual FIT payloads; not Samsung container',
                  hardware_verified=False, installed=False,
                  requires=['Stopped graphical session', 'Root DSIM timing opt-in before panel load',
                            'Manual panel allow_init=1', 'Bounded modeset/page-flip test',
                            'Proven automatic return to working image',
                            'Record panel appearance as unseen unless owner confirms'])
    (dtb.parent / 'display-trial-validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS:', len(checks), 'native-display software checks; not hardware-tested or installed')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dtb', type=Path,
                        default=ROOT / 'build/kernel/j701f-display-trial/exynos7870-j7velte-diagnostic.dtb')
    parser.add_argument('--handoff-dir', type=Path,
                        help='Also verify actual FIT payloads against current kernel and this DTB')
    args = parser.parse_args()
    try:
        validate(args.dtb, args.handoff_dir)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        raise SystemExit('Display trial validation: ' + str(exc))
