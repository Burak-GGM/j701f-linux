#!/usr/bin/env python3
"""Exercise BOOT's switch_root and Alpine PID 1 in an isolated phone RAM namespace."""
import base64
import gzip
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import tarfile
import termios

import recovery

ROOT = recovery.ROOT


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def prepare_fixture(token):
    builder = load('builder', ROOT / 'tools/build-system.py')
    out = ROOT / 'build/handoff-test'
    out.mkdir(exist_ok=True)
    root = out / 'rootfs'
    if root.exists(): shutil.rmtree(root)
    shutil.copytree(builder.OUT / 'rootfs', root, symlinks=True)
    (root / 'etc/inittab').write_text('::sysinit:/sbin/j701f-start\n::once:/bin/sh /sbin/j701f-ram-proof\n')
    (root / 'etc/j701f-ram-token').write_text(token + '\n')
    (root / 'sbin/j701f-ram-proof').write_text('''#!/bin/sh
set -e
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
test "$(cat /etc/alpine-release)" = 3.24.0
test "$(cat /etc/j701f-start-result)" = ALPINE_PID1_START_READY
printf 'Namespace PID 1 command: '; tr '\\0' ' ' < /proc/1/cmdline; printf '\\n'
tr '\\0' ' ' < /proc/1/cmdline | grep -q '/sbin/init'
printf 'APK after handoff: '; /sbin/apk --version
test -x /bin/ondevice-terminal
test -x /bin/usb-debug
printf 'ALPINE_PID1_HANDOFF_PASS\\n' > /etc/j701f-ram-result
while :; do sleep 60; done
''')
    image = out / 'root.ext4'
    with image.open('wb') as file: file.truncate(64 * 1024 * 1024)
    subprocess.run(['fakeroot', 'mkfs.ext4', '-F', '-b', '4096', '-I', '256', '-U', builder.UUID,
                    '-O', 'none,' + builder.FEATURES, '-E', 'lazy_itable_init=0,lazy_journal_init=0,root_owner=0:0',
                    '-d', str(root), str(image)], check=True)
    compressed = out / 'root.ext4.gz'
    with image.open('rb') as source, gzip.open(compressed, 'wb') as output:
        shutil.copyfileobj(source, output)
    ramdisk = out / 'loader.tar.gz'
    with tarfile.open(ramdisk, 'w:gz', format=tarfile.USTAR_FORMAT) as archive:
        for name, values, data in recovery.cpio_entries(builder.boot_ramdisk(ram_test=True)):
            # /dev is created as a fresh private RAM mount on the phone.
            if stat.S_ISCHR(values[1]): continue
            entry = tarfile.TarInfo(name)
            entry.mode = stat.S_IMODE(values[1])
            if stat.S_ISDIR(values[1]): entry.type = tarfile.DIRTYPE
            elif stat.S_ISLNK(values[1]): entry.type = tarfile.SYMTYPE; entry.linkname = data.decode()
            else: entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data) if entry.isfile() else None)
    return ramdisk, compressed


def upload(console, fd, path, target):
    payload = path.read_bytes()
    for offset in range(0, len(payload), 24576):
        chunk = payload[offset:offset+24576]
        digest = hashlib.sha256(chunk).hexdigest()
        script = f"/bin/busybox base64 -d > {target}.chunk <<'HANDOFF_CHUNK'\n"
        script += base64.encodebytes(chunk).decode() + 'HANDOFF_CHUNK\n'
        script += f"sum=$(/bin/busybox sha256sum {target}.chunk)\n"
        script += f"test \"${{sum%% *}}\" = {digest} && /bin/busybox cat {target}.chunk >> {target} && printf 'HANDOFF_CHUNK_OK\\n'\n"
        console.command_session(fd, script, 'HANDOFF_CHUNK_OK')
        if offset == 0 or (offset+24576)//524288 != offset//524288 or offset+24576 >= len(payload):
            print(f'{path.name}: {min(offset+24576,len(payload))}/{len(payload)} bytes', flush=True)


def trial_script(directory, loader_digest, root_digest):
    token = directory.rsplit('-', 1)[-1]
    return f'''set -e
bb=/bin/busybox
trial={directory}
initial=$trial/initial
loop=
supervisor=
child=
initial_mounted=no
root_mounted=no
dev_mounted=no
sys_mounted=no
tmp_mounted=no
base_namespace=$(readlink /proc/1/ns/pid)
stop_test_namespace() {{
    for process in /proc/[0-9]*; do
        pid=${{process##*/}}
        [ "$pid" -gt 1 ] || continue
        ns=$(readlink "$process/ns/pid" 2>/dev/null || :)
        [ -n "$ns" ] && [ "$ns" != "$base_namespace" ] || continue
        [ "$(cat "$process/root/etc/j701f-ram-token" 2>/dev/null || :)" = '{token}' ] || continue
        kill -KILL "$pid" 2>/dev/null || :
    done
    [ -z "$supervisor" ] || kill -KILL "$supervisor" 2>/dev/null || :
    [ -z "$supervisor" ] || wait "$supervisor" 2>/dev/null || :
}}
cleanup() {{
    stop_test_namespace
    clean=yes
    if [ "$root_mounted" = yes ]; then "$bb" umount "$initial/newroot" || clean=no; fi
    if [ "$tmp_mounted" = yes ]; then "$bb" umount "$initial/tmp" || clean=no; fi
    if [ "$sys_mounted" = yes ]; then "$bb" umount "$initial/sys" || clean=no; fi
    if [ "$dev_mounted" = yes ]; then "$bb" umount "$initial/dev" || clean=no; fi
    if [ "$initial_mounted" = yes ]; then "$bb" umount "$initial" || clean=no; fi
    [ -z "$loop" ] || "$bb" losetup -d "$loop" || clean=no
    if [ "$clean" = yes ]; then
        "$bb" rm -rf "$trial"
        printf 'HANDOFF_RAM_CLEANUP_OK\\n'
    else
        printf 'Handoff RAM cleanup incomplete at %s\\n' "$trial" >&2
        return 1
    fi
}}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
printf '%s  %s\\n' '{loader_digest}' "$trial/loader.tar.gz" '{root_digest}' "$trial/root.ext4.gz" | "$bb" sha256sum -c -
"$bb" mkdir "$initial"
"$bb" mount -t tmpfs -o nosuid,mode=0755,size=8m tmpfs "$initial"
initial_mounted=yes
"$bb" tar -xzf "$trial/loader.tar.gz" -C "$initial"
printf '%s\\n' '{token}' > "$initial/etc/j701f-ram-token"
"$bb" gunzip -c "$trial/root.ext4.gz" > "$trial/root.ext4"
loop=$("$bb" losetup -f)
"$bb" losetup "$loop" "$trial/root.ext4"
"$bb" mount -t ext4 -o ro,noload "$loop" "$initial/newroot"
root_mounted=yes
"$bb" chroot "$initial" /bin/boot-manager validate-root /newroot
"$bb" umount "$initial/newroot"
root_mounted=no
"$bb" mount -t ext4 -o rw "$loop" "$initial/newroot"
root_mounted=yes
"$bb" mount -t tmpfs -o nosuid,noexec,mode=0755,size=1m tmpfs "$initial/dev"
dev_mounted=yes
"$bb" mknod -m 666 "$initial/dev/null" c 1 3
"$bb" mknod -m 666 "$initial/dev/zero" c 1 5
"$bb" mknod -m 666 "$initial/dev/urandom" c 1 9
"$bb" mount -t sysfs -o ro,nosuid,nodev,noexec sysfs "$initial/sys"
sys_mounted=yes
"$bb" mount -t tmpfs -o nosuid,nodev,mode=1777,size=8m tmpfs "$initial/tmp"
tmp_mounted=yes
"$bb" unshare -m -p -u -f --propagation private "$bb" chroot "$initial" /bin/sh -c '
/bin/busybox mount -t proc -o nosuid,nodev,noexec proc /proc || exit 1
exec /init
' > "$trial/handoff.log" 2>&1 &
supervisor=$!
# Locate PID 1 by its separate namespace, init name and private RAM token.
# /proc/.../children is unavailable on this vendor kernel.
n=0
while [ "$n" -lt 20 ]; do
    for process in /proc/[0-9]*; do
        pid=${{process##*/}}
        [ "$pid" -gt 1 ] || continue
        [ "$(cat "$process/comm" 2>/dev/null || :)" = init ] || continue
        ns=$(readlink "$process/ns/pid" 2>/dev/null || :)
        [ -n "$ns" ] && [ "$ns" != "$base_namespace" ] || continue
        [ "$(cat "$process/root/etc/j701f-ram-token" 2>/dev/null || :)" = '{token}' ] || continue
        child=$pid
        break
    done
    [ -z "$child" ] || break
    sleep 1; n=$((n+1))
done
case "$child" in ''|1|*[!0-9]*) printf 'No unique isolated PID 1 found\\n' >&2; exit 1 ;; esac
n=0
while [ "$n" -lt 20 ] && [ ! -r "$initial/newroot/etc/j701f-ram-result" ]; do sleep 1; n=$((n+1)); done
cat "$trial/handoff.log"
test "$(cat "$initial/newroot/etc/j701f-ram-result")" = ALPINE_PID1_HANDOFF_PASS
printf 'ALPINE_PID1_HANDOFF_PASS\\n'
cleanup
trap - EXIT
cat /proc/mounts
printf 'SYSTEM_HANDOFF_TRIAL_DONE\\n'
'''


def main():
    token = secrets.token_hex(12)
    loader, root = prepare_fixture(token)
    console = load('console', ROOT / 'tools/usb-console.py')
    ports = console.find_ports()
    if len(ports) != 1: raise ValueError('Expected one recovery USB port')
    directory = '/tmp/j701f-handoff-' + token
    fd = os.open(ports[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    saved = termios.tcgetattr(fd)
    try:
        console.serial_settings(fd)
        script = f'''set -e
/bin/busybox mkdir -m 700 {directory}
/bin/busybox mount -t tmpfs -o nosuid,nodev,mode=0700,size=192m tmpfs {directory}
printf 'HANDOFF_RAM_READY\\n'
'''
        console.command_session(fd, script, 'HANDOFF_RAM_READY')
        upload(console, fd, loader, directory + '/loader.tar.gz')
        upload(console, fd, root, directory + '/root.ext4.gz')
        script = trial_script(directory, recovery.sha(loader.read_bytes()), recovery.sha(root.read_bytes()))
        # The outer RAM mount is kept separate from the destructive switch_root
        # tree and cleaned only after all nested mounts and namespace processes.
        script = script.replace('"$bb" rm -rf "$trial"', '"$bb" rm -rf "$trial"/*\n        "$bb" umount "$trial"\n        "$bb" rmdir "$trial"')
        output = console.command_session(fd, script, 'SYSTEM_HANDOFF_TRIAL_DONE', timeout=55)
        (ROOT / 'build/phone-system-handoff.txt').write_text(output + '\n')
        print(output)
    except Exception as error:
        (ROOT / 'build/phone-system-handoff.txt').write_text(str(error) + '\nRAM trial path: ' + directory + '\n')
        raise
    finally:
        try: termios.tcsetattr(fd, termios.TCSANOW, saved)
        except (OSError, termios.error): pass
        os.close(fd)


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, subprocess.CalledProcessError, KeyboardInterrupt) as error:
        raise SystemExit(f'RAM system handoff: {error}')
