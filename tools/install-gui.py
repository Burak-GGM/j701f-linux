#!/usr/bin/env python3
"""Install a benchmarked manual GUI, preserving its previous files and boot setup."""
import argparse
import base64
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import re
import secrets
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def install(phone, benchmark, pixel_check):
    ipaddress.IPv4Address(phone)
    measurements = json.loads(Path(benchmark).read_text())
    pixels = json.loads(Path(pixel_check).read_text())
    if not re.fullmatch(r'[a-f0-9]{64}', measurements.get('binary_sha256', '')):
        raise ValueError('Missing or invalid compiled binary hash')
    if not pixels.get('full_image_pixel_comparison') or measurements.get('full_render') or \
            measurements.get('poll_render') or len(measurements.get('samples', [])) < 48:
        raise ValueError('Require complete optimized latency runs and full-image pixel validation')
    files = ('main.cpp', 'latency-test.h', 'Makefile')
    hashes = {name: hashlib.sha256((ROOT / 'gui' / name).read_bytes()).hexdigest() for name in files}
    if hashes != measurements['source_sha256'] or hashes != pixels['source_sha256']:
        raise ValueError('Current sources differ from the validated sources')
    bundle = io.BytesIO()
    with tarfile.open(fileobj=bundle, mode='w:gz') as tar:
        for name in files:
            data = (ROOT / 'gui' / name).read_bytes()
            info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
    remote = '/tmp/j701f-gui-install-' + secrets.token_hex(6)
    script = '''set -eu
awk '$2 == "/tmp" && $3 == "tmpfs" {found=1} END {exit !found}' /proc/mounts
trial=REMOTE
mkdir -m 700 "$trial"
trap 'rm -rf "$trial"' EXIT
trap 'exit 143' HUP INT TERM
export HOME="$trial" TMPDIR="$trial" XDG_CACHE_HOME="$trial/cache" XDG_RUNTIME_DIR="$trial/runtime"
mkdir -m 700 "$XDG_RUNTIME_DIR"
base64 -d > "$trial/source.tar.gz" <<'J701F_ARCHIVE'
PAYLOAD
J701F_ARCHIVE
tar xzf "$trial/source.tar.gz" -C "$trial"
cd "$trial"
HASH_CHECK
make CXXFLAGS='-O2 -Wall -Wextra -Werror -std=c++17'
echo 'BINARY_SHA  j701f-gui' | sha256sum -c -
timeout 25 ./j701f-gui --no-fb --latency-test --check-render --seconds 20 > validation.txt 2>&1
cat validation.txt
grep -q '^J701F_TERMINAL_LATENCY_PASS samples=16 ' validation.txt
grep -q '^J701F_RENDER_CHECK_PASS ' validation.txt
target=/home/burak-alpine/j701f-gui
[ -d "$target" ] && [ -f "$target/j701f-gui" ]
backup="$target/backups/latency-BINARY_PREFIX"
# Unique backup directory: refuse to overwrite an earlier backup.
mkdir -p "$target/backups"
mkdir -m 700 "$backup"
for file in j701f-gui main.cpp Makefile latency-test.h; do
    if [ -f "$target/$file" ]; then cp -p "$target/$file" "$backup/$file"; fi
done
(cd "$backup"; sha256sum *) > "$backup.sha256"
for file in main.cpp latency-test.h Makefile; do
    install -m 644 "$file" "$target/$file"
done
install -m 755 j701f-gui "$target/j701f-gui.new"
mv "$target/j701f-gui.new" "$target/j701f-gui"
echo 'BINARY_SHA  /home/burak-alpine/j701f-gui/j701f-gui' | sha256sum -c -
printf 'J701F_GUI_BACKUP %s\n' "$backup"
printf 'J701F_GUI_INSTALL_VERIFIED\n'
cd /
rm -rf "$trial"
trap - EXIT HUP INT TERM
[ ! -e "$trial" ]
printf 'GUI_INSTALL_RAM_CLEANUP_OK\n'
'''.replace('REMOTE', remote).replace('PAYLOAD', base64.b64encode(bundle.getvalue()).decode()).replace(
        'HASH_CHECK', '\n'.join('echo "' + digest + '  ' + name + '" | sha256sum -c -'
                               for name, digest in hashes.items())).replace(
        'BINARY_PREFIX', measurements['binary_sha256'][:12]).replace('BINARY_SHA', measurements['binary_sha256'])
    options = ['-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-i', str(Path.home() / '.ssh/id_ed25519'),
               '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(ROOT / 'build/phone-ssh-known-hosts'),
               '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=1']
    result = subprocess.run(['ssh', *options, 'burak-alpine@' + phone, 'sh -s'], input=script,
                            text=True, capture_output=True, timeout=150)
    output = result.stdout + result.stderr
    (ROOT / 'build/gui-latency/install.txt').write_text(output)
    print(output, end='')
    result.check_returncode()
    if 'J701F_GUI_INSTALL_VERIFIED' not in output or 'GUI_INSTALL_RAM_CLEANUP_OK' not in output:
        raise ValueError('Installation or RAM cleanup evidence incomplete')
    (ROOT / 'build/gui-latency/install.json').write_text(json.dumps(dict(
        source_sha256=hashes, binary_sha256=measurements['binary_sha256'],
        offscreen_pixel_check_passed=True, installed_manual_gui=True,
        previous_files_backed_up=True, boot_startup_changed=False,
        framebuffer_accessed=False, input_devices_accessed=False,
        temporary_ram_files_cleaned=True, physical_touch_latency_verified=False), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phone', required=True)
    parser.add_argument('--benchmark', required=True)
    parser.add_argument('--pixel-check', required=True)
    args = parser.parse_args()
    install(args.phone, args.benchmark, args.pixel_check)
