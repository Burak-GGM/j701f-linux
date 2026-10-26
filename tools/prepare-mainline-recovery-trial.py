#!/usr/bin/env python3
"""Prepare a backed-up RECOVERY-only trial of the paired mainline diagnostic."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/recovery-trial'
CAPACITY = 77824 * 512
BOOT_SHA = '0575c65837f1f993b46884dfa69e9ae54ae5d83aae50bcc02c8b97e3f4f3995c'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def require_recovery_path(candidate_sha=None):
    policy = json.loads((ROOT / 'kernel/hardware-trial-policy.json').read_text())
    require(policy.get('manual_recovery_available') is True or
            policy.get('independent_recovery_verified') is True or
            (policy.get('unattended_failure_accepted') is True and
             policy.get('accepted_attempt_consumed') is False and
             candidate_sha == policy.get('accepted_unattended_candidate_sha256')), 
            'Hardware trial held: user cannot recover the phone manually and no independent recovery path is verified')


def archive(name, data, out=OUT):
    path = out / name
    with tarfile.open(path, 'w', format=tarfile.USTAR_FORMAT) as tar:
        info = tarfile.TarInfo('recovery.img')
        info.size = len(data); info.mode = 0o644; info.mtime = 0
        tar.addfile(info, io.BytesIO(data))
    with tarfile.open(path) as tar:
        require(tar.getnames() == ['recovery.img'], 'Restore archive must target RECOVERY alone')
        require(tar.extractfile('recovery.img').read() == data, 'Archive round trip failed')


def prepare(out=OUT, handoff=None, loader_dir=None, backup_dir=None,
            phone_trial_dir='/home/burak-alpine/j701f-kernel-trial'):
    handoff = (handoff or ROOT / 'build/kernel/handoff').resolve()
    loader_dir = (loader_dir or ROOT / 'build/kernel/uboot-j701f-diagnostic').resolve()
    backup_dir = (backup_dir or out).resolve()
    out = out.resolve()
    require(all(p.is_relative_to(ROOT / 'build/kernel') for p in (out, handoff, loader_dir, backup_dir)),
            'Trial paths must be under build/kernel')
    require(re.fullmatch(r'/home/burak-alpine/j701f-kernel-trial(?:-[a-z0-9-]+)?', phone_trial_dir),
            'Unexpected phone staging path')
    if (out / 'manifest.json').exists():
        require(json.loads((out / 'manifest.json').read_text()).get('phone_partition_written') is not True,
                'Preserve existing flash history; choose a separate trial output')
    backup = (backup_dir / 'recovery-before.img').read_bytes()
    report = (backup_dir / 'phone-backup.txt').read_text()
    match = re.search(r'RECOVERY_BACKUP_SHA256=([a-f0-9]{64})', report)
    require(match and digest(backup) == match.group(1) and len(backup) == CAPACITY,
            'Full recovery backup differs from live read-back evidence')
    rescue = (ROOT / 'build/recovery.img').read_bytes()
    require(backup.startswith(rescue), 'Backup differs from the known working rescue image')
    require(digest((ROOT / 'build/backups/boot-before-cpu-trial.img').read_bytes()) == BOOT_SHA,
            'Working BOOT backup is not verified')
    info = json.loads((handoff / 'container-report.json').read_text())
    embedded = info.get('packaging') == 'embedded-fit-empty-ramdisk-stub-dtbh'
    require(info.get('packaging') in (None, 'embedded-fit-empty-ramdisk-stub-dtbh'),
            'Unknown diagnostic container packaging')
    packager = 'package-embedded-mainline-diagnostic.py' if embedded else 'package-mainline-diagnostic.py'
    spec = importlib.util.spec_from_file_location('candidate', ROOT / 'tools' / packager)
    package = importlib.util.module_from_spec(spec); spec.loader.exec_module(package)
    candidate = (handoff / 'recovery-mainline-diagnostic.preview.img').read_bytes()
    loader = (loader_dir / 'u-boot.bin').read_bytes()
    fit = (handoff / 'mainline.itb').read_bytes()
    require(digest(candidate) == info['image_sha256'] and digest(loader) == info['loader_sha256']
            and digest(fit) == info['fit_sha256'], 'Stale diagnostic container')
    rejected = json.loads((ROOT / 'kernel/rejected-trials.json').read_text())['images']
    require(digest(candidate) not in rejected,
            'Known rejected image: fix the diagnostic packaging before preparing another flash')
    require_recovery_path(digest(candidate))
    loader_info = json.loads((loader_dir / 'report.json').read_text())
    if embedded:
        package.verify(candidate, package.recovery.baseline(), loader, fit,
                       (package.stub_tool.OUT / 'stub-dtbh.img').read_bytes(), loader_info)
        guards = json.loads((handoff / 'guard-validation-report.json').read_text())
        require(guards['status'] == 'passed' and guards['fit_sha256'] == digest(fit) and
                guards['source_sha256'] == digest((ROOT / 'kernel/diagnostic/j701f-embedded-ramboot.c').read_bytes()),
                'Embedded runtime guards are stale or failed')
        for path, expected in loader_info['inputs'].items():
            require(digest((ROOT / path).read_bytes()) == expected, 'Compiled loader input changed: ' + path)
    else:
        package.verify(candidate, package.recovery.baseline(), loader, fit)
    require(loader_info['paired_fit_sha256'] == digest(fit), 'Loader does not match this FIT')
    after = candidate + backup[len(candidate):]
    require(len(after) == CAPACITY, 'Write exceeds RECOVERY capacity')
    out.mkdir(parents=True, exist_ok=True)
    if out != backup_dir:
        (out / 'recovery-before.img').write_bytes(backup)
        (out / 'phone-backup.txt').write_text(report)
    (out / 'recovery-mainline.img').write_bytes(candidate)
    archive('RECOVERY-working-restore.tar', backup, out)
    archive('RECOVERY-mainline-diagnostic.tar', candidate, out)
    manifest = dict(status='prepared-authorized-trial', target='RECOVERY',
                    before_partition_sha256=digest(backup), after_partition_sha256=digest(after),
                    candidate_sha256=digest(candidate), candidate_bytes=len(candidate),
                    capacity_bytes=CAPACITY, boot_sha256=BOOT_SHA,
                    mmc_cid_sha256=json.loads((ROOT / 'build/system/manifest.json').read_text())['mmc_cid_sha256'],
                    working_recovery_backup_verified=True, working_boot_backup_verified=True,
                    phone_partition_written=False, mainline_boot_verified=False,
                    diagnostic_currently_installed=False, phone_trial_dir=phone_trial_dir,
                    handoff_dir=str(handoff.relative_to(ROOT)), loader_dir=str(loader_dir.relative_to(ROOT)),
                    packaging=info.get('packaging', 'fit-in-android-ramdisk'),
                    manual_recovery_available=json.loads((ROOT / 'kernel/hardware-trial-policy.json').read_text())[
                        'manual_recovery_available'])
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    guard = '''set -eu
[ "$(cat /etc/j701f-system-version)" = BURAK_ALPINE_0_1 ]
b=/sys/class/block/mmcblk0p11
grep -qx 'PARTNAME=RECOVERY' "$b/uevent"
[ "$(cat "$b/size")" = 77824 ]
[ "$(cat "$b/dev")" = 259:3 ]
[ -b /dev/mmcblk0p11 ] && [ "$(stat -c '%t:%T' /dev/mmcblk0p11)" = 103:3 ]
[ "$(cat /sys/class/block/mmcblk0/device/type)" = MMC ]
[ "$(cat /sys/class/block/mmcblk0/removable)" = 0 ]
x=$(sha256sum /sys/class/block/mmcblk0/device/cid); [ "${x%% *}" = CID_SHA ]
x=$(sha256sum /dev/mmcblk0p10); [ "${x%% *}" = BOOT_SHA ]
trial=/home/burak-alpine/j701f-kernel-trial
backup="$trial/recovery-before.img"
[ "$(wc -c < "$backup")" = 39845888 ]
x=$(sha256sum "$backup"); [ "${x%% *}" = BEFORE_SHA ]
restore() {
    dd if="$backup" of=/dev/mmcblk0p11 bs=1048576 conv=notrunc 2>/dev/null
    sync
    x=$(sha256sum /dev/mmcblk0p11)
    [ "${x%% *}" = BEFORE_SHA ]
    printf 'RECOVERY_WORKING_RESTORE_READBACK_VERIFIED\n'
}
'''
    guard = guard.replace('CID_SHA', manifest['mmc_cid_sha256']).replace('BOOT_SHA', BOOT_SHA).replace(
        'BEFORE_SHA', digest(backup)).replace('/home/burak-alpine/j701f-kernel-trial', phone_trial_dir)
    write = '''x=$(sha256sum /dev/mmcblk0p11); [ "${x%% *}" = BEFORE_SHA ]
image="$trial/recovery-mainline.img"
[ "$(wc -c < "$image")" = IMAGE_BYTES ]
x=$(sha256sum "$image"); [ "${x%% *}" = IMAGE_SHA ]
trap restore EXIT
dd if="$image" of=/dev/mmcblk0p11 bs=1048576 conv=notrunc 2>/dev/null
sync
x=$(sha256sum /dev/mmcblk0p11); [ "${x%% *}" = AFTER_SHA ]
x=$(sha256sum /dev/mmcblk0p10); [ "${x%% *}" = BOOT_SHA ]
trap - EXIT
printf 'MAINLINE_RECOVERY_FULL_READBACK_VERIFIED\nWORKING_BOOT_UNCHANGED\n'
'''.replace('BEFORE_SHA', digest(backup)).replace('IMAGE_BYTES', str(len(candidate))).replace(
        'IMAGE_SHA', digest(candidate)).replace('AFTER_SHA', digest(after)).replace('BOOT_SHA', BOOT_SHA)
    (out / 'flash.sh').write_text(guard + write)
    (out / 'restore.sh').write_text(guard + 'restore\n')
    print('PASS: exact rescue backup, paired diagnostic, full expected partition hash and RECOVERY-only restore archives.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=OUT)
    parser.add_argument('--handoff-dir', type=Path)
    parser.add_argument('--loader-dir', type=Path)
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--phone-trial-dir', default='/home/burak-alpine/j701f-kernel-trial')
    args = parser.parse_args()
    prepare(args.output_dir, args.handoff_dir, args.loader_dir, args.backup_dir, args.phone_trial_dir)
