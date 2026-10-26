#!/usr/bin/env python3
"""Verify the selected Alpine minirootfs and test it in phone RAM over USB."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import secrets
import shlex
import struct
import subprocess
import tarfile
import termios

ROOT = Path(__file__).resolve().parents[1]
NAME = 'alpine-minirootfs-3.24.0-aarch64.tar.gz'
URL = 'https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/aarch64/' + NAME
SHA256 = '4b8cd66a6688b2a87276c39843ed89c3a06d9534fc6a5823c586aff2696c1f2a'
FINGERPRINT = '0482D84022F52DF1C4E7CD43293ACD0907D9495A'
CHUNK = 24 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def member_path(name):
    require(not name.startswith('/') and '\\' not in name, 'Unsafe archive path')
    parts = PurePosixPath(name).parts
    require('..' not in parts, 'Archive path traverses outside the root')
    return '/'.join(p for p in parts if p != '.')


def inspect_archive(path):
    """Reject path/link traversal and device nodes before the phone extracts it."""
    entries = {}
    total = 0
    with tarfile.open(path, 'r:gz') as archive:
        for entry in archive:
            name = member_path(entry.name)
            require(name not in entries, 'Duplicate archive path: ' + name)
            require(entry.isfile() or entry.isdir() or entry.issym() or entry.islnk(),
                    'Unsupported archive entry: ' + name)
            require(not entry.mode & 0o6000, 'Setuid/setgid archive entry: ' + name)
            require(entry.size >= 0, 'Negative member size')
            total += entry.size
            require(total <= 32 * 1024 * 1024 and len(entries) < 20000, 'Archive exceeds RAM trial limits')
            if entry.issym() or entry.islnk():
                require('\\' not in entry.linkname, 'Unsafe archive link')
                if entry.islnk():
                    target = member_path(entry.linkname)
                else:
                    # An absolute symlink is relative to the eventual chroot.
                    target = posixpath.normpath(entry.linkname.lstrip('/') if entry.linkname.startswith('/')
                                               else posixpath.join(posixpath.dirname(name), entry.linkname))
                    require(target != '..' and not target.startswith('../'), 'Link escapes candidate root')
                require(target not in ('', '.'), 'Unsupported root-directory link')
                if entry.islnk():
                    require(target in entries and entries[target].isfile(), 'Unsafe hardlink ordering/target')
            entries[name] = entry
        # Nothing may be extracted through an archive-provided symlink/file.
        for name in entries:
            ancestor = posixpath.dirname(name)
            while ancestor:
                require(ancestor not in entries or entries[ancestor].isdir(), 'Non-directory archive ancestor')
                ancestor = posixpath.dirname(ancestor)
        for name in ('bin/busybox', 'lib/ld-musl-aarch64.so.1', 'sbin/apk'):
            require(name in entries and entries[name].isfile(), 'Missing regular executable: ' + name)
            header = archive.extractfile(entries[name]).read(64)
            require(len(header) == 64 and header[:7] == b'\x7fELF\x02\x01\x01'
                    and struct.unpack_from('<H', header, 18)[0] == 183, 'Not an AArch64 ELF: ' + name)
        release = archive.extractfile(entries['etc/alpine-release']).read(32).decode().strip()
        require(release == '3.24.0', 'Unexpected Alpine release')
        return dict(entries=len(entries), unpacked_file_bytes=total, release=release,
                    openrc_present='sbin/openrc' in entries)


def prepare():
    downloads = ROOT / 'tools/downloads'
    downloads.mkdir(exist_ok=True)
    for name, url in ((NAME, URL), (NAME + '.sha256', URL + '.sha256'),
                      (NAME + '.asc', URL + '.asc'),
                      ('alpine-release-key.asc', 'https://alpinelinux.org/keys/ncopa.asc')):
        path = downloads / name
        if not path.exists():
            temporary = path.with_name(name + '.part')
            subprocess.run(['curl', '--fail', '--location', '--proto', '=https', '--tlsv1.2',
                            '--max-time', '60', '--output', str(temporary), url], check=True)
            temporary.replace(path)
    path = downloads / NAME
    require(path.stat().st_size <= 8 * 1024 * 1024, 'Compressed archive exceeds trial limit')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    require(digest == SHA256, 'Pinned Alpine archive checksum mismatch')
    require((downloads / (NAME + '.sha256')).read_text().split() == [SHA256, NAME],
            'Published Alpine checksum differs from the pin')
    gpg_home = ROOT / 'build/alpine-gpg'
    gpg_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    prefix = ['gpg', '--batch', '--no-autostart', '--homedir', str(gpg_home)]
    subprocess.run(prefix + ['--import', str(downloads / 'alpine-release-key.asc')],
                   check=True, capture_output=True)
    result = subprocess.run(prefix + ['--status-fd', '1', '--verify',
                            str(downloads / (NAME + '.asc')), str(path)],
                            capture_output=True, text=True, check=True)
    valid = [line.split() for line in result.stdout.splitlines() if line.startswith('[GNUPG:] VALIDSIG ')]
    require(len(valid) == 1 and valid[0][2] == FINGERPRINT and valid[0][-1] == FINGERPRINT,
            'Unexpected Alpine release signing key')
    info = inspect_archive(path)
    info.update(url=URL, sha256=digest, archive_bytes=path.stat().st_size,
                signature_verified=True, signing_fingerprint=FINGERPRINT,
                signing_key_source='https://alpinelinux.org/keys/ncopa.asc')
    (ROOT / 'build/alpine-provenance.json').write_text(json.dumps(info, indent=2) + '\n')
    return path, info


def trial_script(directory):
    """Only temporary RAM mounts and a bounded chroot; never launch init."""
    directory = shlex.quote(directory)
    return f'''set -e
bb=/bin/busybox
trial={directory}
root=$trial/root
root_mounted=no
dev_mounted=no
proc_mounted=no
cleanup() {{
    clean=yes
    if [ "$proc_mounted" = yes ]; then "$bb" umount "$root/proc" || clean=no; fi
    if [ "$dev_mounted" = yes ]; then "$bb" umount "$root/dev" || clean=no; fi
    if [ "$root_mounted" = yes ]; then "$bb" umount "$root" || clean=no; fi
    if [ "$clean" = yes ]; then
        "$bb" rm -rf "$trial"
        printf 'ALPINE_RAM_CLEANUP_OK\\n'
    else
        printf 'ALPINE_RAM_CLEANUP_FAILED: RAM mounts retained at %s\\n' "$root" >&2
        return 1
    fi
}}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
printf '%s  %s\\n' '{SHA256}' "$trial/rootfs.tar.gz" | "$bb" sha256sum -c -
"$bb" mkdir "$root"
"$bb" mount -t tmpfs -o nosuid,nodev,mode=0755,size=64m tmpfs "$root"
root_mounted=yes
"$bb" tar -xzf "$trial/rootfs.tar.gz" -C "$root"
"$bb" mount -t tmpfs -o nosuid,noexec,mode=0755,size=1m tmpfs "$root/dev"
dev_mounted=yes
# Only standard character devices; the chroot gets no storage device nodes.
"$bb" mknod -m 666 "$root/dev/null" c 1 3
"$bb" mknod -m 666 "$root/dev/zero" c 1 5
"$bb" mknod -m 666 "$root/dev/random" c 1 8
"$bb" mknod -m 666 "$root/dev/urandom" c 1 9
"$bb" mount -t proc -o ro,nosuid,nodev,noexec proc "$root/proc"
proc_mounted=yes
printf 'ALPINE_CHROOT_START\\n'
"$bb" timeout -s TERM -k 2 30 "$bb" chroot "$root" /bin/sh -c '
set -e
export PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LC_ALL=C
printf "Alpine release: "; cat /etc/alpine-release
printf "Kernel: "; uname -a
printf "BusyBox: "; /bin/busybox | head -n 1
printf "Dynamic libraries:\\n"; /lib/ld-musl-aarch64.so.1 --list /bin/busybox
printf "APK: "; /sbin/apk --version
printf "Installed packages:\\n"; /sbin/apk info
test "$(printf "pipeline-works\\n" | awk "{{print toupper(\\$0)}}")" = PIPELINE-WORKS
test "$((6 * 7))" = 42
printf "ram-file-test\\n" > /tmp/alpine-test
test "$(cat /tmp/alpine-test)" = ram-file-test
sha256sum /tmp/alpine-test
rm /tmp/alpine-test
printf "ALPINE_BASIC_USERSPACE_PASS\\n"
'
printf 'ALPINE_CHROOT_EXIT_0\\n'
cleanup
trap - EXIT
printf 'Recovery kernel remains running; no PID 1 handoff or block-partition changes.\\n'
cat /proc/mounts
printf 'ALPINE_TRIAL_DONE\\n'
'''


def run_phone(path, port=None):
    spec = importlib.util.spec_from_file_location('usb_console', ROOT / 'tools/usb-console.py')
    console = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(console)
    if not port:
        ports = console.find_ports()
        require(len(ports) == 1, 'Expected one connected recovery USB shell; close other terminals')
        port = ports[0]
    directory = '/tmp/j701f-alpine-' + secrets.token_hex(12)
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    saved = termios.tcgetattr(fd)
    report = ROOT / 'build/phone-alpine-ram-test.txt'
    output = ''
    started = False
    try:
        console.serial_settings(fd)
        output = console.command_session(fd, f'''set -e
/bin/busybox awk '$2 == "/tmp" && $3 == "tmpfs" {{found=1}} END {{exit !found}}' /proc/mounts
test "$(/bin/busybox df -Pk /tmp | /bin/busybox awk 'NR==2 {{print $4}}')" -ge 6000
/bin/busybox mkdir -m 700 {shlex.quote(directory)}
printf 'ALPINE_UPLOAD_READY\\n'
''', 'ALPINE_UPLOAD_READY')
        started = True
        payload = path.read_bytes()
        for offset in range(0, len(payload), CHUNK):
            data = payload[offset:offset + CHUNK]
            chunk_hash = hashlib.sha256(data).hexdigest()
            script = f"/bin/busybox base64 -d > {directory}/chunk <<'ALPINE_CHUNK'\n"
            script += base64.encodebytes(data).decode() + 'ALPINE_CHUNK\n'
            script += f"sum=$(/bin/busybox sha256sum {directory}/chunk)\n"
            script += f"if [ \"${{sum%% *}}\" = '{chunk_hash}' ]; then\n"
            script += f"/bin/busybox cat {directory}/chunk >> {directory}/rootfs.tar.gz && printf 'ALPINE_CHUNK_OK\\n'\nfi\n"
            console.command_session(fd, script, 'ALPINE_CHUNK_OK')
            if offset == 0 or (offset + CHUNK) // (512 * 1024) != offset // (512 * 1024) or offset + CHUNK >= len(payload):
                print(f'Uploaded {min(offset + CHUNK, len(payload))}/{len(payload)} bytes to phone RAM.', flush=True)
        output += '\n' + console.command_session(fd, trial_script(directory), 'ALPINE_TRIAL_DONE', timeout=50)
        require('ALPINE_BASIC_USERSPACE_PASS' in output and 'ALPINE_RAM_CLEANUP_OK' in output,
                'Alpine trial or cleanup did not pass')
        report.write_text(output + '\n')
        print(output)
        print(f'Saved {report}. All trial mounts and files removed; phone partitions unchanged.')
    except Exception as error:
        report.write_text(output + '\nTrial failed: ' + str(error) + '\nRAM directory: ' + directory + '\n')
        if started:
            # Never recursively delete an unconfirmed mountpoint after a failed trial.
            try:
                cleanup = f'''if /bin/busybox awk -v p='{directory}/' 'index($2,p)==1 {{found=1}} END {{exit !found}}' /proc/mounts; then
printf 'RAM mounts remain; preserve trial directory for inspection\\n'
else
/bin/busybox rm -rf {directory}
fi
printf 'ALPINE_FAILURE_CLEANUP_CHECKED\\n'
'''
                console.command_session(fd, cleanup, 'ALPINE_FAILURE_CLEANUP_CHECKED', timeout=10)
            except Exception:
                pass
        raise
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSANOW, saved)
        except (OSError, termios.error):
            pass
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true', help='Verify/download without contacting the phone')
    parser.add_argument('--device', help='Explicit recovery USB serial device')
    args = parser.parse_args()
    path, info = prepare()
    print(f'Verified Alpine {info["release"]}, signature {FINGERPRINT}, {info["unpacked_file_bytes"]} unpacked bytes.', flush=True)
    if not args.prepare_only:
        print('Close other serial terminals. Trial uses RAM only and returns to recovery.', flush=True)
        run_phone(path, args.device)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError, KeyboardInterrupt) as error:
        raise SystemExit(f'Alpine RAM trial: {error}')
