#!/usr/bin/env python3
"""Build the J701F Alpine DATA image on a host; never access the phone.

The public image starts from the signed, pinned Alpine 3.24.0 aarch64
minirootfs and resolves AArch64 APK packages using a pinned Alpine container.
The BOOT loader's USERDATA UUID and root marker are intentionally immutable.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
OUTPUT = REPO / 'build/release'
UUID = '4ce26b55-8a59-4fb7-aad4-919a5c2cefeb'
VERSION = 'BURAK_ALPINE_0_1'
SECTORS = 23314432
BYTES = SECTORS * 512
CONTAINER = 'alpine@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a'
FEATURES = ('has_journal,ext_attr,resize_inode,dir_index,filetype,extent,'
            'sparse_super,large_file,huge_file,uninit_bg,dir_nlink,extra_isize')
PKG_RE = re.compile(r'^[a-zA-Z0-9+_.-]+$')


def run(args, *, log=None):
    print('+', ' '.join(map(str, args)), flush=True)
    with log.open('w') if log else open('/dev/null', 'w') as output:
        subprocess.run(list(map(str, args)), check=True,
                       stdout=output if log else None,
                       stderr=subprocess.STDOUT if log else None)


def docker(*args, log=None):
    run(['docker', 'run', '--rm', *args], log=log)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def package_names(development):
    paths = [REPO / 'system/release/base-packages.txt',
             REPO / 'system/apps/core.txt']
    if development:
        paths.append(REPO / 'system/apps/optional-development.txt')
    names = set()
    for path in paths:
        for line in path.read_text().splitlines():
            name = line.strip()
            if not name or name.startswith('#'):
                continue
            if not PKG_RE.fullmatch(name):
                raise ValueError(f'Invalid package in {path}: {name!r}')
            names.add(name)
    return sorted(names)


def signed_alpine():
    spec = importlib.util.spec_from_file_location('alpine_ram_test', REPO / 'tools/alpine-ram-test.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.prepare()


def validate_root(root):
    required = ['etc/j701f-root', 'etc/j701f-system-version', 'etc/inittab',
                'etc/alpine-release', 'bin/usb-debug', 'bin/usb-shell',
                'bin/display-status', 'sbin/init', 'sbin/j701f-start',
                'sbin/j701f-openrc', 'sbin/apk', 'lib/ld-musl-aarch64.so.1',
                'usr/bin/kwin_wayland', 'usr/bin/sddm', 'etc/fstab',
                'media/sdcard', 'etc/runlevels/boot/localmount',
                'etc/local.d/j701f-usb-mtp.start',
                'usr/local/sbin/j701f-usb-mtp']
    # BusyBox uses absolute in-root symlinks such as /sbin/init -> /bin/busybox;
    # Path.exists() on the host would incorrectly resolve these against /.
    missing = [name for name in required
               if not (root / name).exists() and not (root / name).is_symlink()]
    if missing:
        raise ValueError('Missing critical release paths: ' + ', '.join(missing))
    if (root / 'etc/j701f-system-version').read_text().strip() != VERSION:
        raise ValueError('BOOT handoff version marker differs')
    if (root / 'etc/alpine-release').read_text().strip() != '3.24.0':
        raise ValueError('Unexpected Alpine base release')
    fstab = (root / 'etc/fstab').read_text()
    if '/dev/mmcblk2p1 /media/sdcard vfat nofail,' not in fstab:
        raise ValueError('Missing optional physical SD card mount')
    if (root / 'etc/j701f-display-native').exists():
        if (root / 'etc/j701f-display-native').read_text().strip() != 'always':
            raise ValueError('Invalid native-display startup mode')
        if not (root / 'home/burak-alpine/j701f/modules/display/kernel-notes.sha256').is_file():
            raise ValueError('Native-display startup lacks a pinned kernel identity')
    passwd = (root / 'etc/passwd').read_text().splitlines()
    if not any(row.startswith('burak-alpine:x:1000:1000:') for row in passwd):
        raise ValueError('Missing expected unprivileged local account')
    docker('-v', f'{root}:/target:ro', CONTAINER, 'sh', '-ec',
           "grep -q '^burak-alpine::' /target/etc/shadow; "
           "! grep -q '^burak-alpine:[^:]*:0:' /target/etc/shadow; "
           "grep -q '^PasswordAuthentication no$' "
           "/target/etc/ssh/sshd_config.d/00-j701f.conf; "
           "[ \"$(stat -c %a /target/etc/shadow)\" = 640 ]; "
           "[ \"$(stat -c %G /target/etc/shadow)\" = shadow ]; "
           "[ \"$(stat -c %a /target/etc/umtprd)\" = 700 ]; "
           "test -f /target/etc/umtprd/umtprd.conf; "
           "grep -qx 'Autolock=false' "
           "/target/home/burak-alpine/.config/kscreenlockerrc; "
           "grep -qx 'RequirePassword=false' "
           "/target/home/burak-alpine/.config/kscreenlockerrc")
    if (root / 'home/burak-alpine/.ssh/authorized_keys').exists():
        raise ValueError('Refusing to include a preinstalled SSH public key')
    if list((root / 'etc/ssh').glob('ssh_host_*')):
        raise ValueError('Refusing to include a machine SSH host key')
    docker('-v', f'{root}:/target:ro', CONTAINER, 'sh', '-ec',
           'd=/target/etc/NetworkManager/system-connections; '
           '[ ! -d "$d" ] || [ -z "$(ls -A "$d")" ]')
    if (root / 'etc/wpa_supplicant/wlan0.conf').stat().st_mode & 0o077:
        raise ValueError('Wi-Fi configuration permissions are too broad')


def build_rootfs(root, work, archive, names, modules):
    if root.exists():
        # Root-owned files are removed from inside the same isolated container.
        docker('-v', f'{root.parent}:/work', CONTAINER,
               'sh', '-c', 'rm -rf /work/rootfs')
    root.mkdir(parents=True)
    docker('-v', f'{root}:/target', '-v', f'{archive}:/alpine.tar.gz:ro', CONTAINER,
           'sh', '-ec', 'tar -xzf /alpine.tar.gz -C /target; '
                       'printf "%s\\n" '
                       'https://dl-cdn.alpinelinux.org/alpine/v3.24/main '
                       'https://dl-cdn.alpinelinux.org/alpine/v3.24/community '
                       '> /target/etc/apk/repositories')
    (work / 'packages.txt').write_text('\n'.join(names) + '\n')
    docker('-v', f'{root}:/target', '-v', f'{work / "packages.txt"}:/packages:ro',
           CONTAINER, 'sh', '-ec',
           'apk --root /target --arch aarch64 update; '
           'xargs apk --root /target --arch aarch64 add --no-scripts </packages',
           log=work / 'apk-install.log')
    docker('-v', f'{root}:/target', '-v', f'{REPO}:/src:ro', CONTAINER,
           'sh', '/src/system/release/provision.sh', '/target', '/src')
    if modules:
        if not modules.is_dir():
            raise ValueError(f'Modules directory not found: {modules}')
        # The Samsung MFC firmware copied from a personal handset may not be
        # redistributed. The Alpine firmware package is installed separately.
        if (modules / 'mfc/mfc_fw.bin').exists():
            print('Excluding phone-extracted mfc_fw.bin from the image')
        docker('-v', f'{root}:/target', '-v', f'{modules}:/modules:ro', CONTAINER,
               'sh', '-ec',
               'cp -a /modules/. /target/home/burak-alpine/j701f/modules/; '
               'rm -f /target/home/burak-alpine/j701f/modules/mfc/mfc_fw.bin; '
               'chown -R 1000:1000 /target/home/burak-alpine/j701f/modules')
    validate_root(root)


def copy_local_wifi_firmware(root, directory):
    if not directory:
        return
    print('Local device firmware requested: generated payload must stay private')
    required = ('brcmfmac43430-sdio.bin', 'brcmfmac43430-sdio.clm_blob',
                'brcmfmac43430-sdio.txt')
    for name in required:
        source = directory / name
        if not source.is_file() or source.is_symlink() or source.stat().st_size == 0:
            raise ValueError(f'Missing regular local J701F Wi-Fi firmware: {source}')
    docker('-v', f'{root}:/target', '-v', f'{directory}:/firmware:ro', CONTAINER,
           'sh', '-ec',
           'mkdir -p /target/lib/firmware/brcm; '
           'for name in brcmfmac43430-sdio.bin brcmfmac43430-sdio.clm_blob '
           'brcmfmac43430-sdio.txt; do '
           'install -m 644 "/firmware/$name" "/target/lib/firmware/brcm/$name"; '
           'done; '
           'if [ -f /firmware/BCM43430A1.hcd ]; then '
           'install -m 644 /firmware/BCM43430A1.hcd '
           '/target/lib/firmware/brcm/BCM43430A1.hcd; fi')
    for name in required:
        if sha256(directory / name) != sha256(root / 'lib/firmware/brcm' / name):
            raise ValueError(f'Wi-Fi firmware copy mismatch: {name}')


def copy_local_mfc_firmware(root, source):
    if not source:
        return
    if not source.is_file() or source.is_symlink() or source.stat().st_size == 0:
        raise ValueError(f'Missing regular local MFC firmware: {source}')
    print('Local Samsung video firmware requested: generated payload must stay private')
    docker('-v', f'{root}:/target', '-v', f'{source}:/mfc.bin:ro', CONTAINER,
           'sh', '-ec',
           'install -m 644 /mfc.bin /target/lib/firmware/s5p-mfc-v10.fw')
    if sha256(source) != sha256(root / 'lib/firmware/s5p-mfc-v10.fw'):
        raise ValueError('MFC firmware copy mismatch')


def ensure_user_services(root):
    """Also repairs roots made before the user-runlevel source was added."""
    docker('-v', f'{root}:/target', CONTAINER, 'sh', '-ec',
           'd=/target/home/burak-alpine/.config/rc/runlevels/default; '
           'mkdir -p "$d"; '
           'for name in dbus pipewire pipewire-pulse wireplumber; do '
           '[ -e "/target/etc/user/init.d/$name" ] || exit 1; '
           'ln -sfn "/etc/user/init.d/$name" "$d/$name"; done; '
           'chown -R 1000:1000 /target/home/burak-alpine/.config/rc')


def ensure_persistent_wifi(root):
    docker('-v', f'{root}:/target', '-v', f'{REPO}:/src:ro', CONTAINER,
           'sh', '-ec',
           'install -m 755 /src/system/wifi /target/sbin/j701f-wifi-classic; '
           'install -m 755 /src/system/release/wifi.sh /target/sbin/j701f-wifi; '
           'printf "%s\\n" "Keep NetworkManager running while Wi-Fi is unconfigured." '
           '> /target/etc/j701f-wifi-nm-persistent; '
           'chmod 644 /target/etc/j701f-wifi-nm-persistent')


def refresh_release_scripts(root):
    docker('-v', f'{root}:/target', '-v', f'{REPO}:/src:ro', CONTAINER,
           'sh', '-ec',
           'install -m 755 /src/system/release/firstboot.sh '
           '/target/usr/local/sbin/j701f-release-firstboot; '
           'install -m 755 /src/system/release/j701f-release-setup.initd '
           '/target/etc/init.d/j701f-release-setup; '
           'install -m 644 /src/system/release/kscreenlockerrc '
           '/target/home/burak-alpine/.config/kscreenlockerrc; '
           'install -m 644 /src/system/release/fstab /target/etc/fstab; '
           'mkdir -p /target/media/sdcard /target/etc/umtprd /target/etc/local.d; '
           'install -m 755 /src/system/usb-mtp/start.sh '
           '/target/usr/local/sbin/j701f-usb-mtp; '
           'install -m 644 /src/system/usb-mtp/umtprd.conf '
           '/target/etc/umtprd/umtprd.conf; '
           'install -m 755 /src/system/release/j701f-usb-mtp.start '
           '/target/etc/local.d/j701f-usb-mtp.start; '
           'chmod 700 /target/etc/umtprd; '
           'mkdir -p /target/etc/runlevels/boot; '
           'ln -sfn /etc/init.d/localmount '
           '/target/etc/runlevels/boot/localmount; '
           'chown 1000:1000 /target/home/burak-alpine/.config/kscreenlockerrc; '
           'chgrp shadow /target/etc/shadow; chmod 640 /target/etc/shadow')


def copy_local_umtprd(root, source):
    if not source:
        return
    if not source.is_file() or source.is_symlink() or source.stat().st_size == 0:
        raise ValueError(f'Missing regular local uMTP-Responder binary: {source}')
    print('Local uMTP-Responder requested: generated payload must stay private')
    docker('-v', f'{root}:/target', '-v', f'{source}:/umtprd:ro', CONTAINER,
           'sh', '-ec', 'install -m 755 /umtprd /target/usr/local/bin/umtprd')
    if sha256(source) != sha256(root / 'usr/local/bin/umtprd'):
        raise ValueError('uMTP-Responder binary copy mismatch')


def enable_native_display_for_matching_modules(root):
    display = root / 'home/burak-alpine/j701f/modules/display'
    required = ('kernel-notes.sha256', 'panel-j701f-ea8061s.ko',
                'j701f-display-overlay.ko')
    if not all((display / name).is_file() for name in required):
        (root / 'etc/j701f-display-native').unlink(missing_ok=True)
        return False
    expected = (display / 'kernel-notes.sha256').read_text().strip()
    if not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('Invalid native-display kernel-notes hash')
    docker('-v', f'{root}:/target', CONTAINER, 'sh', '-ec',
           "printf 'always\\n' > /target/etc/j701f-display-native; "
           'chmod 644 /target/etc/j701f-display-native')
    return True


def migrate_unconfigured_account(root):
    """Bring a reused, never-installed build root to the passwordless first-boot contract."""
    docker('-v', f'{root}:/target', CONTAINER, 'sh', '-ec',
           "sed -i 's/^burak-alpine:!:/burak-alpine::/' /target/etc/shadow; "
           # A 0 last-change field forces a password change and breaks autologin.
           "sed -i 's/^burak-alpine:\\([^:]*\\):0:/burak-alpine:\\1::/' /target/etc/shadow; "
           'chgrp shadow /target/etc/shadow; chmod 640 /target/etc/shadow')


def compile_schema_cache(root):
    """Make the quiet feedback profile effective even before firstboot setup."""
    docker('-v', f'{root}:/target', CONTAINER, 'sh', '-ec',
           'apk add --no-cache glib >/dev/null; '
           'glib-compile-schemas --strict '
           '/target/usr/share/glib-2.0/schemas')


def make_image(root, work):
    raw = OUTPUT / 'userdata.ext4'
    if raw.exists():
        raw.unlink()
    docker('-v', f'{root}:/target:ro', '-v', f'{OUTPUT}:/out', CONTAINER,
           'sh', '-ec',
           'apk add --no-cache e2fsprogs >/dev/null; '
           f'truncate -s {BYTES} /out/userdata.ext4; '
           'mkfs.ext4 -F -b 4096 -I 256 -L BURAK_LINUX '
           f'-U {UUID} -m 1 -O none,{FEATURES} '
           '-E lazy_itable_init=0,lazy_journal_init=0,root_owner=0:0 '
           '-d /target /out/userdata.ext4',
           log=work / 'mkfs.log')
    if raw.stat().st_size != BYTES:
        raise ValueError('USERDATA image length differs from the PIT partition')
    result = subprocess.run(['blkid', '-o', 'value', '-s', 'UUID', str(raw)],
                            check=True, capture_output=True, text=True).stdout.strip()
    if result != UUID:
        raise ValueError(f'Unexpected ext4 UUID: {result}')
    fsck = subprocess.run(['e2fsck', '-fn', str(raw)],
                          capture_output=True, text=True)
    (work / 'e2fsck.log').write_text(fsck.stdout + fsck.stderr)
    if fsck.returncode != 0:
        raise ValueError(f'Offline ext4 fsck failed with status {fsck.returncode}')
    raw_digest = sha256(raw)
    (OUTPUT / 'userdata.ext4.sha256').write_text(f'{raw_digest}  userdata.ext4\n')
    packed = OUTPUT / 'userdata.ext4.gz'
    with packed.open('wb') as target:
        subprocess.run(['gzip', '-1', '-n', '-c', str(raw)],
                       stdout=target, check=True)
    if packed.stat().st_size >= 4 * 1024 * 1024 * 1024:
        raise ValueError('Compressed payload exceeds the FAT32 single-file limit')
    packed_digest = sha256(packed)
    (OUTPUT / 'userdata.ext4.gz.sha256').write_text(
        f'{packed_digest}  userdata.ext4.gz\n')
    return raw, packed, raw_digest, packed_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--development', action='store_true',
                        help='include on-device compilers, Git and diagnostics')
    parser.add_argument('--modules-dir', type=Path,
                        help='optional kernel-matched local modules directory; no private firmware copied')
    parser.add_argument('--wifi-firmware-dir', type=Path,
                        help='private, device-extracted Broadcom firmware; keep output local')
    parser.add_argument('--mfc-firmware-file', type=Path,
                        help='private, device-extracted Samsung video firmware; keep output local')
    parser.add_argument('--umtprd-binary', type=Path,
                        help='local AArch64 uMTP-Responder executable; keep output private')
    parser.add_argument('--reuse-rootfs', action='store_true',
                        help='developer-only: rebuild payload from the already provisioned rootfs')
    args = parser.parse_args()
    if shutil.which('docker') is None:
        parser.error('Docker is required for the AArch64 cross-build')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    work = OUTPUT / 'work'
    work.mkdir(exist_ok=True)
    names = package_names(args.development)
    archive, provenance = signed_alpine()
    root = work / 'rootfs'
    if args.reuse_rootfs:
        migrate_unconfigured_account(root)
        refresh_release_scripts(root)
        validate_root(root)
        world = set((root / 'etc/apk/world').read_text().splitlines())
        if world != set(names):
            raise ValueError('Reused APK world differs from requested package profile')
    else:
        build_rootfs(root, work, archive, names,
                     args.modules_dir.resolve() if args.modules_dir else None)
    ensure_user_services(root)
    ensure_persistent_wifi(root)
    refresh_release_scripts(root)
    compile_schema_cache(root)
    copy_local_wifi_firmware(root, args.wifi_firmware_dir.resolve()
                             if args.wifi_firmware_dir else None)
    copy_local_mfc_firmware(root, args.mfc_firmware_file.resolve()
                            if args.mfc_firmware_file else None)
    copy_local_umtprd(root, args.umtprd_binary.resolve()
                      if args.umtprd_binary else None)
    native_display = enable_native_display_for_matching_modules(root)
    validate_root(root)
    private_wifi = (root / 'lib/firmware/brcm/brcmfmac43430-sdio.bin').exists()
    private_mfc = (root / 'lib/firmware/s5p-mfc-v10.fw').exists()
    private_umtprd = (root / 'usr/local/bin/umtprd').exists()
    (OUTPUT / 'release.json').unlink(missing_ok=True)
    raw, packed, raw_digest, packed_digest = make_image(root, work)
    release = {
        'device': 'SM-J701F / samsung,j7velte',
        'partition': 'USERDATA',
        'sectors': SECTORS,
        'bytes': BYTES,
        'filesystem': 'ext4',
        'filesystem_uuid': UUID,
        'root_version': VERSION,
        'alpine_base_version': '3.24.0',
        'alpine_base_sha256': provenance['sha256'],
        'alpine_signing_fingerprint': provenance['signing_fingerprint'],
        'apk_package_requests': names,
        'development_tools': args.development,
        'external_modules': bool(args.modules_dir),
        'personal_wifi_firmware': private_wifi,
        'personal_mfc_firmware': private_mfc,
        'local_umtprd_binary': private_umtprd,
        'native_display_enabled': native_display,
        'redistributable': not (private_wifi or private_mfc or private_umtprd),
        'container': CONTAINER,
        'raw_image': {'file': raw.name, 'sha256': raw_digest, 'bytes': raw.stat().st_size},
        'sd_payload': {'file': packed.name, 'sha256': packed_digest,
                       'bytes': packed.stat().st_size},
        'credentials_included': False,
    }
    (OUTPUT / 'release.json').write_text(json.dumps(release, indent=2) + '\n')
    print(f'Release payload: {packed} ({packed.stat().st_size} bytes)')
    print(f'Offline filesystem check: PASS; USB/BOOT/RECOVERY untouched')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        sys.exit(f'Release build failed: {error}')
