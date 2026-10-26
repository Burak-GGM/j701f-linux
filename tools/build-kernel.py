#!/usr/bin/env python3
"""Build isolated vendor/Panfrost compile targets. Never packages or flashes a phone."""
import argparse
import difflib
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WORK = Path('/tmp/j701f-kernel-build')
GCC_COMMIT = '84fb09fafc92a3d9b4d160f049d46c3c784cc941'
GCC_URL = 'https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9'
GCC_DIR = ROOT / 'kernel/toolchains/android-aarch64-gcc49'
RUNNING_CONFIG_SHA256 = '669d32f426befcb9706b83097a7c92020479caca6c4eaed5bb99764011c0598f'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def source(profile):
    inputs = json.loads((ROOT / 'kernel/inputs.json').read_text())
    entry = inputs[profile]
    archive = ROOT / 'kernel/downloads' / entry['archive']
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        temporary = archive.with_suffix('.part')
        print('Downloading pinned source:', entry['url'], flush=True)
        with urllib.request.urlopen(entry['url'], timeout=90) as src, temporary.open('wb') as dst:
            shutil.copyfileobj(src, dst)
        require(sha(temporary) == entry['sha256'], 'Downloaded source checksum mismatch')
        temporary.replace(archive)
    require(sha(archive) == entry['sha256'], 'Cached source checksum mismatch')
    src = WORK / 'sources' / entry['directory']
    marker = WORK / 'sources' / (entry['directory'] + '.ready')
    if not marker.exists():
        src.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            require(all(m.name == entry['directory'] or m.name.startswith(entry['directory'] + '/')
                        for m in members), 'Unexpected source archive prefix')
            tar.extractall(src.parent, members=members, filter='data')
        marker.write_text(entry['sha256'] + '\n')
    require(marker.read_text().strip() == entry['sha256'] and (src / 'Makefile').is_file(),
            'Source cache marker mismatch')
    return src, entry


def toolchain():
    if not GCC_DIR.exists():
        GCC_DIR.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--depth', '1', '--single-branch', '--branch',
                        'android10-release', GCC_URL, str(GCC_DIR)], check=True)
    commit = subprocess.check_output(['git', '-C', str(GCC_DIR), 'rev-parse', 'HEAD'], text=True).strip()
    origin = subprocess.check_output(['git', '-C', str(GCC_DIR), 'remote', 'get-url', 'origin'], text=True).strip()
    require(commit == GCC_COMMIT and origin == GCC_URL, 'Unexpected GCC source checkout')
    require(not subprocess.check_output(['git', '-C', str(GCC_DIR), 'status', '--porcelain']),
            'GCC checkout has local changes')
    return str(GCC_DIR / 'bin/aarch64-linux-android-')


def check_image(path):
    with path.open('rb') as stream:
        header = stream.read(64)
    require(header[56:60] == b'ARM\x64', 'Output lacks AArch64 Image magic')
    offset, size, flags = struct.unpack_from('<3Q', header, 8)
    # image_size reserves runtime memory, including BSS; it can exceed file bytes.
    require(0 < size <= 512 * 1024 * 1024, 'Invalid Image memory size field')
    require(offset <= 512 * 1024 * 1024 and not flags & 1, 'Unsupported load offset/endianness')
    return dict(bytes=path.stat().st_size, text_offset=hex(offset),
                image_size=size, flags=hex(flags), sha256=sha(path))


def apply_patches(src, patches):
    """Apply each patch once to the tree `src`; markers beside the tree record what is applied.

    Claude 2026-10-13: a patch that was edited after it had been applied used
    to be applied on top of its own older version, which fails (met with the
    charger patch). A copy of every applied patch is now kept next to its
    marker, so the older version can be taken out first. A tree prepared before
    this change has no such copy: then the only honest answer is to start from
    a clean tree.
    """
    for patch in patches:
        digest = sha(patch)
        prefix = src.name + '.' + patch.stem + '.'
        marker = src.parent / (prefix + digest[:16] + '.applied')
        if marker.exists():
            continue
        for old in sorted(src.parent.glob(prefix + '*.applied')):
            if not re.fullmatch(re.escape(prefix) + '[0-9a-f]{16}[.]applied', old.name):
                continue    # the marker of another patch whose name starts the same way
            kept = old.with_suffix('.patch')
            require(kept.exists(),
                    patch.name + ' was changed after it had been applied to ' + str(src) +
                    ' and the applied version was not kept: remove that tree and its ' +
                    '.applied markers so that it is prepared afresh')
            subprocess.run(['patch', '-p1', '-R', '-i', str(kept)], cwd=src, check=True,
                           stdout=subprocess.DEVNULL)
            old.unlink()
            kept.unlink()
        subprocess.run(['patch', '-p1', '--forward', '-i', str(patch)], cwd=src, check=True,
                       stdout=subprocess.DEVNULL)
        shutil.copyfile(patch, marker.with_suffix('.patch'))
        marker.write_text(digest + '\n')


def build(args):
    artifact = ROOT / 'build/kernel' / args.profile
    artifact.mkdir(parents=True, exist_ok=True)
    report = dict(profile=args.profile, status='preparing', phone_modified=False,
                  hardware_boot_tested=False, flash_ready=False)
    report_path = artifact / 'report.json'
    json_write(report_path, report)
    try:
        src, entry = source(args.profile)
        if args.profile == 'panfrost':
            # Claude 2026-10-08: local kernel patches (kernel/patches/linux-*.patch),
            # applied once per extracted tree and recorded beside it.
            patches = [f for pattern in entry.get('patches', ['linux-*.patch'])
                       for f in sorted((ROOT / 'kernel/patches').glob(pattern))]
            apply_patches(src, patches)
        out = WORK / 'out' / ('vendor-baseline' if args.profile == 'baseline' else 'mainline-panfrost')
        out.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, LC_ALL='C', KBUILD_BUILD_USER='burak',
                   KBUILD_BUILD_HOST='j701f-builder', KBUILD_BUILD_VERSION='1',
                   KBUILD_BUILD_TIMESTAMP='Thu Oct 8 00:00:00 UTC 2026')
        command = ['make', '-C', str(src), 'O=' + str(out), 'ARCH=arm64']
        if args.profile == 'baseline':
            prefix = toolchain()
            env.update(ANDROID_MAJOR_VERSION='q', ANDROID_PLATFORM_VERSION='10')
            command += ['CROSS_COMPILE=' + prefix, 'CCACHE=', 'HOSTCC=gcc',
                        'HOSTCFLAGS=-O2 -std=gnu89 -fcommon']
            baseline = ROOT / 'kernel/configs/vendor-running.config'
            require(sha(baseline) == RUNNING_CONFIG_SHA256, 'Running kernel config changed')
            normalized = ROOT / 'kernel/configs/vendor-baseline.config'
            require(sha(normalized) == entry['config_sha256'], 'Resolved baseline config changed')
            if not (out / '.config').exists() or (out / '.config').read_bytes() != normalized.read_bytes():
                shutil.copyfile(normalized, out / '.config')
            compiler = prefix + 'gcc'
        else:
            # lld 23 occasionally needs a third kallsyms pass after the LE
            # stack changes the linked image; the kernel explicitly recommends it.
            command += ['LLVM=1', 'KALLSYMS_EXTRA_PASS=1']
            compiler = 'clang'
        report.update(source=entry, compiler=subprocess.check_output([compiler, '--version'],
                      text=True, stderr=subprocess.DEVNULL).splitlines()[0],
                      make_command=command, jobs=args.jobs,
                      build_environment={key: env[key] for key in ('LC_ALL', 'KBUILD_BUILD_USER',
                          'KBUILD_BUILD_HOST', 'KBUILD_BUILD_VERSION', 'KBUILD_BUILD_TIMESTAMP')})
        report['config_inputs'] = {p.name: sha(p) for p in (
            [baseline, normalized] if args.profile == 'baseline' else
            [src / 'arch/arm64/configs/exynos7870.config', ROOT / 'kernel/configs/mainline-bringup.config'])}
        if args.profile == 'baseline':
            report.update(gcc_commit=GCC_COMMIT, android_major_version='q', android_platform_version='10')
        if args.prepare_only:
            report['status'] = 'prepared'
            json_write(report_path, report)
            print('Prepared source/compiler; no compilation or phone changes.', flush=True)
            return
        with (artifact / 'build.log').open('w') as log:
            def run(*targets):
                subprocess.run(command + list(targets), env=env, stdout=log,
                               stderr=subprocess.STDOUT, check=True)
            # Re-merge on every invocation. Checking only the previous .config hash
            # misses changes to the fragment: the old config can still match the
            # previous pinned digest while the requested new options are ignored.
            if args.profile == 'panfrost':
                run('defconfig')
                run('exynos7870.config')
                subprocess.run(['bash', str(src / 'scripts/kconfig/merge_config.sh'), '-m',
                                str(out / '.config'), str(ROOT / 'kernel/configs/mainline-bringup.config')],
                               cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            run('olddefconfig')
            if args.profile == 'panfrost':
                require(sha(out / '.config') == entry['resolved_config_sha256'],
                        'Resolved mainline configuration differs; review compiler/fragment changes')
            report['status'] = 'compiling'
            json_write(report_path, report)
            print('Compiling', args.profile, 'with', args.jobs, 'jobs; log:', artifact / 'build.log', flush=True)
            run('-j' + str(args.jobs), 'Image', 'dtb.img' if args.profile == 'baseline' else 'dtbs')
            if args.modules:
                # Not needed for the image. Separately built modules (tools/kmod/, the
                # charger, the display modules) need the Module.symvers this leaves in
                # the output tree; without it modpost reports every kernel symbol as
                # undefined (met 2026-10-13, after a host reboot had emptied /tmp).
                run('-j' + str(args.jobs), 'modules')
        image = check_image(out / 'arch/arm64/boot/Image')
        config = (out / '.config').read_text()
        if args.profile == 'baseline':
            for option in ('CONFIG_SOC_EXYNOS7870=y', 'CONFIG_EXT4_FS=y', 'CONFIG_DEVTMPFS=y',
                           'CONFIG_USB_G_ANDROID=y', 'CONFIG_USB_F_ACM=y', 'CONFIG_SMP=y',
                           'CONFIG_EXYNOS_DECON_7870=y', 'CONFIG_PANEL_EA8061S_J7VE=y',
                           'CONFIG_TOUCHSCREEN_MELFAS_MMS438=y'):
                require(option in config.splitlines(), 'Baseline hardware option missing: ' + option)
        if args.profile == 'panfrost':
            for option in ('CONFIG_DRM=y', 'CONFIG_DRM_PANFROST=y', 'CONFIG_DRM_EXYNOS=y',
                           'CONFIG_DRM_EXYNOS7_DECON=y', 'CONFIG_EXT4_FS=y', 'CONFIG_DEVTMPFS=y'):
                require(option in config.splitlines(), 'Required option missing: ' + option)
        for original, name in [(out / 'arch/arm64/boot/Image', 'Image'),
                               (out / '.config', 'config'), (out / 'System.map', 'System.map')]:
            shutil.copyfile(original, artifact / name)
        if args.profile == 'baseline':
            diff = difflib.unified_diff(baseline.read_text().splitlines(True), config.splitlines(True),
                                       fromfile='running-binary.config', tofile='built-baseline.config')
            (artifact / 'config.diff').write_text(''.join(diff))
            dtb_image = out / 'arch/arm64/boot/dtb.img'
            require(dtb_image.is_file(), 'Baseline DTBH output is absent')
            with dtb_image.open('rb') as stream:
                require(stream.read(4) == b'DTBH', 'Baseline device tree image lacks DTBH magic')
            shutil.copyfile(dtb_image, artifact / 'dtb.img')
        else:
            trees = out / 'arch/arm64/boot/dts/exynos'
            dtbs = artifact / 'dtbs'; dtbs.mkdir(exist_ok=True)
            for dtb in trees.glob('exynos7870-*.dtb'):
                shutil.copyfile(dtb, dtbs / dtb.name)
            report['board_limit'] = 'No J701F/j7velte DT in pinned source; related-board DTBs are not substitutes.'
        if args.save_vmlinux:
            with (out / 'vmlinux').open('rb') as f, (artifact / 'vmlinux.gz').open('wb') as raw:
                with gzip.GzipFile(filename='', mode='wb', compresslevel=1, fileobj=raw, mtime=0) as gz:
                    shutil.copyfileobj(f, gz)
        report.update(status='compiled', image=image,
                      kernel_release=(out / 'include/config/kernel.release').read_text().strip(),
                      files={str(p.relative_to(artifact)): sha(p) for p in artifact.rglob('*')
                             if p.is_file() and p.name != 'report.json'})
        json_write(report_path, report)
        print('PASS: compiled AArch64 Image and device trees. Artifact:', artifact, flush=True)
        print('Compile evidence only; not flashed or hardware-validated.', flush=True)
    except Exception as error:
        report.update(status='failed', error=str(error))
        json_write(report_path, report)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', choices=['baseline', 'panfrost'])
    parser.add_argument('--jobs', type=int, default=3)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--save-vmlinux', action='store_true')
    parser.add_argument('--modules', action='store_true',
                        help='also build the in-tree modules (leaves Module.symvers for out-of-tree module builds)')
    args = parser.parse_args()
    require(1 <= args.jobs <= 12, 'Use between one and twelve parallel jobs')
    build(args)
