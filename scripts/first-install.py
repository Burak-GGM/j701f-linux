#!/usr/bin/env python3
"""Host side of the first installation from stock Android (Route A of
docs/installer-first-install-plan.md).

Started by Argon, finished by Claude 2026-10-27. It never runs Odin, never
opens USB and never talks to the phone. By default it only checks:

  * the Odin archives from tools/prepare-first-install.py (manifest and both
    single-member USTAR archives),
  * the release from tools/build-release.py (hashes, release.json),
  * with --sd, the microSD card mounted on this computer (a removable vfat
    disk with room for the release),

and prints the steps, with the Odin commands written out but not run. With
--stage it copies the release, the recovery-side scripts and the BOOT image
to SD/j701f-release/, reading every file back.

  scripts/first-install.py [--sd /run/media/$USER/CARD] [--stage]
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'build/first-install'
RELEASE = ROOT / 'build/release'
RELEASE_FILES = ('userdata.ext4.gz', 'userdata.ext4.gz.sha256', 'userdata.ext4.sha256', 'release.json')
RECOVERY_SCRIPTS = ('install-release-on-recovery.sh', 'recovery-install-job.sh',
                    'restore-userdata-on-recovery.sh')
SECTORS = 23314432
BYTES = 11936989184
UUID = '4ce26b55-8a59-4fb7-aad4-919a5c2cefeb'
FAT32_MAX = 4 * 1024 * 1024 * 1024 - 1
# The pre-installation USERDATA backup that Route A takes on the same card.
BACKUP_BYTES = BYTES


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare_tool():
    spec = importlib.util.spec_from_file_location('prepare_first_install', ROOT / 'tools/prepare-first-install.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def first_hash(path):
    words = Path(path).read_text().split()
    value = words[0] if words else ''
    require(len(value) == 64 and all(c in '0123456789abcdef' for c in value), f'bad hash in {path}')
    return value


def check_bundle(bundle):
    """The Odin archives: manifest present and both archives verify again."""
    manifest_path = bundle / 'manifest.json'
    require(manifest_path.is_file(), f'{manifest_path} missing: run tools/prepare-first-install.py')
    manifest = json.loads(manifest_path.read_text())
    require(manifest.get('status') == 'host-prepared', 'bundle manifest is not host-prepared')
    tool = prepare_tool()
    result = {}
    for role in ('boot', 'recovery'):
        archive = bundle / tool.ROLE_SPEC[role]['archive']
        info = tool.verify_tar(archive, role)
        require(info['archive_sha256'] == manifest[role]['archive_sha256'],
                f'{archive.name} differs from its manifest entry')
        result[role] = info
    # Route A stages boot.img, not the tar: it must be the image inside the
    # archive that was just verified, not merely agree with the manifest.
    boot_sha = sha256_file(bundle / 'boot.img') if (bundle / 'boot.img').is_file() else None
    require(boot_sha == result['boot']['image_sha256'],
            'boot.img is not the image inside the verified BOOT archive')
    require(boot_sha == manifest['boot']['image_sha256'], 'boot.img differs from its manifest entry')
    return manifest, result


def check_release(release):
    """The USERDATA release: files, both hashes and the fixed partition facts."""
    for name in RELEASE_FILES:
        require((release / name).is_file(), f'{release / name} missing: run tools/build-release.py')
    payload = release / 'userdata.ext4.gz'
    require(payload.stat().st_size <= FAT32_MAX, 'userdata.ext4.gz is too large for a FAT32 card')
    payload_sha = sha256_file(payload)
    require(payload_sha == first_hash(release / 'userdata.ext4.gz.sha256'),
            'userdata.ext4.gz does not match userdata.ext4.gz.sha256')
    info = json.loads((release / 'release.json').read_text())
    require(info.get('partition') == 'USERDATA', 'release.json is not for the USERDATA partition')
    require(info.get('sectors') == SECTORS and info.get('bytes') == BYTES, 'release.json is not for this USERDATA')
    require(info.get('filesystem_uuid') == UUID, 'release.json names another filesystem UUID')
    require('j7velte' in str(info.get('device', '')), 'release.json is not for the j7velte')
    # Both hashes in release.json are required and must agree with the files
    # (Codex's review, 2026-10-27).
    require(info.get('sd_payload', {}).get('sha256') == payload_sha,
            'release.json and userdata.ext4.gz disagree')
    require(info.get('raw_image', {}).get('sha256') == first_hash(release / 'userdata.ext4.sha256'),
            'release.json and userdata.ext4.sha256 disagree')
    return info


def block_device_of(path, mounts='/proc/mounts'):
    """(device, fstype) of the mount whose mount point is exactly path."""
    target = os.path.realpath(path)
    found = None
    for line in Path(mounts).read_text().splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[1].replace('\\040', ' ') == target:
            found = (fields[0], fields[2])
    require(found is not None, f'{path} is not a mount point; mount the microSD card first')
    return found


def check_sd(sd, mounts='/proc/mounts', sys_block='/sys/class/block', need=0):
    """The card must be its own removable vfat disk with room for the release."""
    device, fstype = block_device_of(sd, mounts)
    require(fstype == 'vfat', f'{sd} is {fstype}, the phone recovery expects FAT32 (vfat)')
    name = os.path.basename(os.path.realpath(device))
    node = Path(sys_block) / name
    require(node.exists(), f'no sysfs entry for {device}')
    disk = node if (node / 'removable').exists() else Path(os.path.realpath(node)).parent
    require((disk / 'removable').read_text().strip() == '1',
            f'{device} is not on a removable disk; refusing to treat it as the microSD card')
    free = shutil.disk_usage(sd).free
    require(free >= need, f'{sd} has {free} bytes free, {need} needed')
    return {'device': device, 'disk': disk.name, 'free': free}


def stage(sd, release, bundle):
    """Copy everything for Route A to SD/j701f-release/ and read each file back."""
    dest = Path(sd) / 'j701f-release'
    dest.mkdir(exist_ok=True)
    plan = [(release / n, dest / n) for n in RELEASE_FILES]
    plan += [(ROOT / 'scripts' / n, dest / n) for n in RECOVERY_SCRIPTS]
    plan.append((bundle / 'boot.img', dest / 'boot-mainline.img'))
    for src, dst in plan:
        tmp = dst.with_name(dst.name + '.part')
        shutil.copyfile(src, tmp)
        with open(tmp, 'rb') as f:
            os.fsync(f.fileno())
        require(sha256_file(tmp) == sha256_file(src), f'{dst.name}: read-back differs from the source')
        os.replace(tmp, dst)
        print(f'  staged {dst.name}')
    os.sync()
    return dest


def steps(manifest):
    boot_sha = manifest['boot']['image_sha256']
    return f"""
Route A, by hand (nothing below has been run):
 1. Back up the phone. In Android: Developer options > OEM unlocking on; battery >= 50 %.
 2. Download Mode (Volume Down + Home + Power, then Volume Up), then:
      tools/odin4 -l
      python3 tools/prepare-first-install.py --verify-tar build/first-install/RECOVERY-j701f-mainline.tar --role recovery
      tools/odin4 -a build/first-install/RECOVERY-j701f-mainline.tar -d /dev/bus/usb/BBB/DDD
    and hold Volume Up + Home + Power while it restarts, so stock Android cannot replace RECOVERY.
 3. In the project recovery, from python3 tools/usb-console.py:
      : > /run/recovery-state/stay; sh /recovery/scripts/storage.sh mount-sd
      sh /recovery/scripts/mtp.sh down; sh /recovery/scripts/wifi.sh down
      mkdir -p /mnt/sd/j701f-backups
      dd if=/dev/mmcblk0p10 of=/mnt/sd/j701f-backups/boot-stock-backup.img bs=1048576; sync
 4. BOOT: J701F_RECOVERY_STATE=/run/recovery-state sh /recovery/scripts/flash-boot.sh write \\
      /mnt/sd/j701f-release/boot-mainline.img {boot_sha}
 5. USERDATA, dry run, then for real (ERASES ALL ANDROID DATA):
      sh /mnt/sd/j701f-release/install-release-on-recovery.sh --source /mnt/sd/j701f-release --erase-userdata
      sh /mnt/sd/j701f-release/install-release-on-recovery.sh --source /mnt/sd/j701f-release --execute --erase-userdata
 6. Boot system. See docs/installer-first-install-plan.md for the way back."""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--bundle', type=Path, default=BUNDLE)
    parser.add_argument('--release', type=Path, default=RELEASE)
    parser.add_argument('--sd', type=Path, help='mount point of the microSD card on this computer')
    parser.add_argument('--stage', action='store_true', help='copy the release to the card (needs --sd)')
    args = parser.parse_args()
    if args.stage and not args.sd:
        parser.error('--stage needs --sd')

    manifest, archives = check_bundle(args.bundle)
    print(f"Odin archives verified: BOOT {archives['boot']['archive_sha256'][:16]}..., "
          f"RECOVERY {archives['recovery']['archive_sha256'][:16]}...")
    info = check_release(args.release)
    print(f"Release verified: {info.get('root_version', '?')}, payload "
          f"{(args.release / 'userdata.ext4.gz').stat().st_size} bytes")
    if args.sd:
        need = sum((args.release / n).stat().st_size for n in RELEASE_FILES) + (args.bundle / 'boot.img').stat().st_size
        sd = check_sd(args.sd, need=need)
        print(f"microSD: {sd['device']} on removable {sd['disk']}, {sd['free']} bytes free")
        if sd['free'] < need + BACKUP_BYTES:
            print(f'  note: the pre-installation USERDATA backup needs another {BACKUP_BYTES} bytes on this card')
        if args.stage:
            dest = stage(args.sd, args.release, args.bundle)
            print(f'Staged and read back: {dest}')
    print(steps(manifest))
    print('\nDRY RUN: no Odin, USB or phone action was taken.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        raise SystemExit(f'ERROR: {exc}')
