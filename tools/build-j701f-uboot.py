#!/usr/bin/env python3
"""Build an unflashed J701F diagnostic second stage from pinned official U-Boot."""
import argparse
import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
WORK = Path('/tmp/j701f-uboot-source')
ARTIFACT = ROOT / 'build/kernel/uboot-j701f-diagnostic'
PATCH = ROOT / 'kernel/patches/uboot-j701f-diagnostic.patch'
FRAGMENT = ROOT / 'kernel/configs/uboot-j701f-diagnostic.config'


def check_generated_environment(header):
    """Check the actual C string emitted by U-Boot's env2string, not env.txt."""
    prefix = '#define CONFIG_EXTRA_ENV_TEXT '
    lines = [line[len(prefix):] for line in header.splitlines() if line.startswith(prefix)]
    if len(lines) != 1:
        raise ValueError('Expected one generated environment string')
    value = ast.literal_eval(lines[0])
    if not isinstance(value, str) or not value.endswith('\0'):
        raise ValueError('Generated environment must be a NUL-terminated string')
    values = {}
    for entry in value[:-1].split('\0'):
        key, separator, data = entry.partition('=')
        if not separator or not key or key in values or any(c.isspace() for c in key):
            raise ValueError('Invalid or duplicate generated environment key')
        values[key] = data
    expected = dict(stdin='nulldev', stdout='nulldev', stderr='nulldev',
                    bootdelay='0', bootcmd='j701f_ramboot')
    if values != expected:
        raise ValueError('Generated environment differs from the diagnostic allowlist')
    return values


def main(jobs, prepare_tools=False, fit_dir=None, artifact=ARTIFACT, embed_fit=False):
    work = Path('/tmp/j701f-uboot-embedded-source') if embed_fit else WORK
    if embed_fit and (prepare_tools or artifact.resolve() == ARTIFACT.resolve()):
        raise ValueError('Embedded variant requires separate artifact path and a paired FIT')
    source_file = ROOT / ('kernel/diagnostic/j701f-embedded-ramboot.c' if embed_fit else
                          'kernel/diagnostic/j701f-ramboot.c')
    artifact = artifact.resolve()
    if not artifact.is_relative_to(ROOT / 'build/kernel'):
        raise ValueError('Artifact output must be under build/kernel')
    fit_dir = (fit_dir or ROOT / 'build/kernel/handoff').resolve()
    if not fit_dir.is_relative_to(ROOT / 'build/kernel'):
        raise ValueError('FIT inputs must be under build/kernel')
    spec = importlib.util.spec_from_file_location('kb', ROOT / 'tools/build-kernel.py')
    kb = importlib.util.module_from_spec(spec); spec.loader.exec_module(kb)
    entry = json.loads((ROOT / 'kernel/uboot-input.json').read_text())
    archive = ROOT / 'kernel/downloads' / entry['archive']
    kb.require(kb.sha(archive) == entry['sha256'], 'U-Boot archive checksum mismatch')
    src = work / entry['directory']
    if not src.exists():
        work.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            kb.require(all(m.name == entry['directory'] or m.name.startswith(entry['directory'] + '/')
                           for m in tar.getmembers()), 'Unexpected U-Boot source archive prefix')
            tar.extractall(work, filter='data')
    patch_marker = src / '.j701f-patch'
    if not patch_marker.exists():
        subprocess.run(['patch', '--dry-run', '-p1', '-i', str(PATCH)], cwd=src, check=True)
        subprocess.run(['patch', '-p1', '-i', str(PATCH)], cwd=src, check=True)
        patch_marker.write_text(kb.sha(PATCH))
    kb.require(patch_marker.read_text() == kb.sha(PATCH), 'Patch changed: recreate temporary source cache')
    if embed_fit:
        bss_patch = ROOT / 'kernel/patches/uboot-aarch64-lld-bss.patch'
        marker = src / '.j701f-lld-bss-patch'
        if not marker.exists():
            subprocess.run(['patch', '--dry-run', '-p1', '-i', str(bss_patch)], cwd=src, check=True)
            subprocess.run(['patch', '-p1', '-i', str(bss_patch)], cwd=src, check=True)
            marker.write_text(kb.sha(bss_patch))
        kb.require(marker.read_text() == kb.sha(bss_patch), 'BSS patch changed: recreate source cache')
    dts = src / 'dts/upstream/src/arm64/exynos'
    shutil.copyfile(ROOT / 'kernel/dts/exynos7870-j7velte-uboot.dts', dts / 'exynos7870-j7velte.dts')
    shutil.copyfile(ROOT / 'kernel/dts/exynos7870-j7velte-diagnostic.dts', dts / 'exynos7870-j7velte-diagnostic.dts')
    shutil.copyfile(ROOT / 'kernel/dts/exynos7870-j7velte-pmic.dtsi', dts / 'exynos7870-j7velte-pmic.dtsi')
    shutil.copyfile(ROOT / 'kernel/diagnostic/uboot.env', src / 'board/samsung/exynos-mobile/exynos-mobile.env')
    board = src / 'board/samsung/exynos-mobile'
    shutil.copyfile(source_file, board / 'j701f-ramboot.c')
    board_makefile = board / 'Makefile'
    if 'j701f-ramboot.o' not in board_makefile.read_text():
        with board_makefile.open('a') as output:
            output.write('\nobj-y += j701f-ramboot.o\n')
    if not prepare_tools:
        fit_report = json.loads((fit_dir / 'report.json').read_text())
        kb.require(fit_report['status'] == 'packaged' and
                   kb.sha(fit_dir / 'mainline.itb') == fit_report['fit_sha256'] and
                   kb.sha(fit_dir / 'j701f-fit-payload.h') == fit_report['generated_header_sha256'],
                   'Paired FIT artifact/header changed; rebuild it first')
        shutil.copyfile(fit_dir / 'j701f-fit-payload.h', board / 'j701f-fit-payload.h')
    if embed_fit:
        payload = board / 'j701f-embedded.itb'
        shutil.copyfile(fit_dir / 'mainline.itb', payload)
        (board / 'j701f-embedded-file.h').write_text(
            '#define J701F_EMBEDDED_FILE ' + json.dumps(str(payload)) + '\n')
        shutil.copyfile(ROOT / 'kernel/diagnostic/j701f-embedded-fit.S', board / 'j701f-embedded-fit.S')
        if 'j701f-embedded-fit.o' not in board_makefile.read_text():
            with board_makefile.open('a') as output:
                output.write('obj-y += j701f-embedded-fit.o\n')
    out = work / ('out-j701f' if artifact == ARTIFACT else 'out-' + artifact.name)
    out.mkdir(exist_ok=True)
    artifact.mkdir(parents=True, exist_ok=True)
    report_path = artifact / 'report.json'
    env = dict(os.environ, LC_ALL='C', SOURCE_DATE_EPOCH='1791331200',
               KBUILD_BUILD_USER='burak', KBUILD_BUILD_HOST='j701f-builder')
    command = ['make', '-C', str(src), 'O=' + str(out),
               'CROSS_COMPILE=aarch64-linux-gnu-',
               'CC=clang --target=aarch64-none-elf -mno-outline-atomics',
               'CLANG_FLAGS=',
               'LD=ld.lld', 'AR=llvm-ar', 'NM=llvm-nm', 'OBJCOPY=llvm-objcopy',
               'OBJDUMP=llvm-objdump', 'STRIP=llvm-strip', 'READELF=llvm-readelf',
               'HOSTCC=clang', 'HOSTCXX=clang++']
    report = dict(status='preparing', phone_modified=False, hardware_boot_tested=False,
                  flash_ready=False, source=entry, make_command=command,
                  compiler=subprocess.check_output(['clang', '--version'], text=True).splitlines()[0],
                  inputs={str(p.relative_to(ROOT)): kb.sha(p) for p in [PATCH, FRAGMENT,
                          ROOT / 'kernel/dts/exynos7870-j7velte-diagnostic.dts',
                          ROOT / 'kernel/dts/exynos7870-j7velte-uboot.dts',
                          ROOT / 'kernel/dts/exynos7870-j7velte-pmic.dtsi',
                          source_file,
                          ROOT / 'kernel/diagnostic/uboot.env']},
                  patched_board_sha256=kb.sha(src / 'board/samsung/exynos-mobile/exynos-mobile.c'),
                  build_environment={key: env[key] for key in ('LC_ALL', 'SOURCE_DATE_EPOCH',
                      'KBUILD_BUILD_USER', 'KBUILD_BUILD_HOST')})
    if not prepare_tools:
        report['paired_fit_sha256'] = fit_report['fit_sha256']
        report['paired_fit_header_sha256'] = kb.sha(board / 'j701f-fit-payload.h')
    if embed_fit:
        report['inputs']['kernel/patches/uboot-aarch64-lld-bss.patch'] = kb.sha(bss_patch)
    report['payload_source'] = 'embedded-relocated-rodata' if embed_fit else 'samsung-initrd'
    if embed_fit:
        report['inputs']['kernel/diagnostic/j701f-embedded-fit.S'] = kb.sha(ROOT / 'kernel/diagnostic/j701f-embedded-fit.S')
    report['board_makefile_sha256'] = kb.sha(board_makefile)
    kb.json_write(report_path, report)
    try:
        with (artifact / 'build.log').open('w') as log:
            def run(*targets):
                subprocess.run(command + list(targets), env=env, stdout=log,
                               stderr=subprocess.STDOUT, check=True)
            run('exynos-mobile_defconfig')
            subprocess.run(['bash', str(src / 'scripts/kconfig/merge_config.sh'), '-m',
                            str(out / '.config'), str(FRAGMENT)], cwd=out, env=env,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
            run('olddefconfig')
            report['status'] = 'compiling'; kb.json_write(report_path, report)
            run('-j' + str(jobs), 'tools-only' if prepare_tools else 'u-boot.bin')
        shutil.copy2(out / 'tools/mkimage', artifact / 'mkimage')
        (artifact / 'mkimage').chmod(0o755)
        if prepare_tools:
            report.update(status='host-tools-prepared', files={'mkimage': kb.sha(artifact / 'mkimage')})
            kb.json_write(report_path, report)
            print('PASS: pinned host mkimage prepared. Next build the FIT, then the loader.')
            return
        config = dict(line.split('=', 1) for line in (out / '.config').read_text().splitlines()
                      if line.startswith('CONFIG_') and '=' in line)
        # Kconfig omits unavailable symbols when their parent is disabled.
        for option in ('FASTBOOT_FLASH', 'CMD_MMC', 'USB_FUNCTION_FASTBOOT',
                       'CMD_USB_MASS_STORAGE', 'ENV_IS_IN_MMC', 'ENV_IS_IN_FAT', 'ENV_IS_IN_EXT4',
                       'USB', 'USB_GADGET', 'USB_FUNCTION_ACM', 'MMC_DW', 'MMC_WRITE', 'DM_PMIC',
                       'DM_REGULATOR', 'PHY', 'SERIAL_PRESENT', 'REQUIRE_SERIAL_CONSOLE',
                       'FS_EXT4', 'FS_FAT', 'CMD_FS_GENERIC'):
            kb.require(config.get('CONFIG_' + option, 'n') == 'n', 'Diagnostic guard missing: ' + option)
        for option in ('ENV_IS_NOWHERE', 'SYS_DEVICE_NULLDEV', 'FIT', 'FIT_FULL_CHECK', 'SHA256'):
            kb.require(config.get('CONFIG_' + option) == 'y', 'Diagnostic guard missing: ' + option)
        compression = fit_report.get('kernel_compression', 'none')
        kb.require(compression in ('none', 'gzip'), 'Unknown paired FIT compression')
        if compression == 'gzip':
            kb.require(config.get('CONFIG_GZIP') == 'y', 'Loader cannot decompress the paired kernel')
            kb.require(int(config['CONFIG_SYS_BOOTM_LEN'], 0) >= fit_report['kernel_uncompressed_bytes'],
                       'Loader decompression limit is smaller than the kernel')
        report['paired_kernel_compression'] = compression
        kb.require(config.get('CONFIG_BOOTCOMMAND') == '"j701f_ramboot"' and
                   config.get('CONFIG_BOOTDELAY') == '0', 'Unexpected automatic boot command')
        env_text = (out / 'include/generated/env.txt').read_text().splitlines()
        kb.require('bootcmd=j701f_ramboot' in env_text and 'stdout=nulldev' in env_text,
                   'Generated loader environment differs')
        report['generated_environment'] = check_generated_environment(
            (out / 'include/generated/environment.h').read_text())
        shutil.copyfile(out / 'include/generated/environment.h', artifact / 'environment.h')
        for name in ('u-boot.bin', 'u-boot', 'u-boot.map', '.config'):
            shutil.copyfile(out / name, artifact / ('config' if name == '.config' else name))
        shutil.copyfile(out / 'dts/dt.dtb', artifact / 'u-boot.dtb')
        spec = importlib.util.spec_from_file_location('board_check', ROOT / 'tools/build-j701f-dtb.py')
        board_check = importlib.util.module_from_spec(spec); spec.loader.exec_module(board_check)
        validation = board_check.verify(artifact / 'u-boot.dtb')
        for node in ('i2c@10510000', 'usb@13600000', 'phy@135c0000', 'serial@13820000'):
            kb.require(board_check.prop(artifact / 'u-boot.dtb', '/soc@0/' + node, 'status', 's') == 'disabled',
                       'Loader must not probe unvalidated peripheral: ' + node)
        symbols = subprocess.check_output(['llvm-nm', str(artifact / 'u-boot')], text=True)
        kb.require('do_j701f_ramboot' in symbols, 'RAM handoff command was not linked')
        if embed_fit:
            addresses = {line.split()[2]: int(line.split()[0], 16)
                         for line in symbols.splitlines() if len(line.split()) == 3}
            start, end = addresses['j701f_embedded_fit'], addresses['j701f_embedded_fit_end']
            base, copy_end = addresses['__image_copy_start'], addresses['__image_copy_end']
            kb.require(copy_end <= addresses['__rel_dyn_start'] < addresses['__rel_dyn_end'] <=
                       addresses['__bss_start'] < addresses['__bss_end'],
                       'BSS overlaps executable image or relocation records')
            kb.require(addresses['__bss_end'] - base < 0x04000000,
                       'Loader initial reservation reaches vendor debug area')
            kb.require(start % 8 == 0 and base <= start < end <= copy_end and
                       end - start == fit_report['fit_bytes'], 'Embedded FIT is not inside relocated image')
            image_data = (artifact / 'u-boot.bin').read_bytes()
            kb.require(image_data[start-base:end-base] == (fit_dir / 'mainline.itb').read_bytes(),
                       'Embedded FIT bytes differ from paired payload')
            report['embedded_fit'] = dict(offset=start-base, bytes=end-start,
                image_copy_bytes=copy_end-base, monitor_bytes=addresses['__bss_end']-base,
                source_is_relocated=True, sha256=fit_report['fit_sha256'])
        validation['loader_peripherals_disabled'] = True
        report.update(status='compiled', image=kb.check_image(artifact / 'u-boot.bin'),
                      internal_dt_validation=validation,
                      files={p.name: kb.sha(p) for p in artifact.iterdir()
                             if p.is_file() and p.name != 'report.json'},
                      limits=['Not installed or hardware-booted.',
                              'Matches measured J701F firmware prefix and revision 3 only.',
                              'U-Boot does not supply USB or probe PMIC; Linux owns peripheral bring-up.',
                              'Paired RAM payload boots automatically only if all handoff guards pass.',
                              'Failure stops without a storage fallback; no loader USB console.',
                              'A reliable recovery path is required before supervised hardware trials.'])
        kb.json_write(report_path, report)
        print('PASS: compiled guarded RAM handoff loader. Not flashed:', artifact)
    except Exception as error:
        report.update(status='failed', error=str(error)); kb.json_write(report_path, report)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--prepare-tools', action='store_true', help='Bootstrap pinned host mkimage before packaging FIT')
    parser.add_argument('--fit-dir', type=Path, help='Paired FIT output directory')
    parser.add_argument('--artifact-dir', type=Path, default=ARTIFACT, help='Separate loader artifacts for a new candidate')
    parser.add_argument('--embed-fit', action='store_true', help='Embed the paired FIT in relocated rodata; no Samsung initrd needed')
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        parser.error('Use 1–8 jobs')
    main(args.jobs, args.prepare_tools, args.fit_dir, args.artifact_dir, args.embed_fit)
