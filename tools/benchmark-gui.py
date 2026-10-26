#!/usr/bin/env python3
"""Measure the actual GUI's PTY/paint path on Alpine, entirely offscreen in RAM."""
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


def benchmark(phone, label, runs=3, check_render=False, full_render=False, poll_render=False):
    ipaddress.IPv4Address(phone)
    if not re.fullmatch(r'[a-z0-9-]{1,40}', label):
        raise ValueError('Use a short lowercase label')
    archive = io.BytesIO()
    hashes = {}
    with tarfile.open(fileobj=archive, mode='w:gz') as tar:
        for name in ('main.cpp', 'latency-test.h', 'Makefile'):
            data = (ROOT / 'gui' / name).read_bytes()
            hashes[name] = hashlib.sha256(data).hexdigest()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
    payload = base64.b64encode(archive.getvalue()).decode()
    out = ROOT / 'build/gui-latency'
    out.mkdir(parents=True, exist_ok=True)
    (out / (label + '-source.tar.gz')).write_bytes(archive.getvalue())
    remote = '/tmp/j701f-gui-benchmark-' + secrets.token_hex(6)
    script = '''set -eu
awk '$2 == "/tmp" && $3 == "tmpfs" {found=1} END {exit !found}' /proc/mounts
trial=REMOTE
mkdir -m 700 "$trial"
cleanup() { rm -rf "$trial"; }
trap cleanup EXIT
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
printf 'J701F_GUI_BINARY_SHA '
sha256sum j701f-gui
uname -r
for run in RUNS; do
    printf 'J701F_BENCHMARK_RUN %s\n' "$run"
    timeout 25 ./j701f-gui --no-fb --latency-test --seconds 20 EXTRA
done
cd /
cleanup
trap - EXIT HUP INT TERM
[ ! -e "$trial" ]
printf 'GUI_BENCHMARK_RAM_CLEANUP_OK\n'
'''.replace('REMOTE', remote).replace('PAYLOAD', payload).replace(
        'HASH_CHECK', '\n'.join('echo "' + digest + '  ' + name + '" | sha256sum -c -'
                               for name, digest in hashes.items())).replace(
        'RUNS', ' '.join(str(n + 1) for n in range(runs))).replace(
        'EXTRA', ('--check-render ' if check_render else '') + ('--full-render ' if full_render else '') +
        ('--poll-render' if poll_render else ''))
    options = ['-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-i', str(Path.home() / '.ssh/id_ed25519'),
               '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(ROOT / 'build/phone-ssh-known-hosts'),
               '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=1']
    result = subprocess.run(['ssh', *options, 'burak-alpine@' + phone, 'sh -s'],
                            input=script, text=True, capture_output=True, timeout=150)
    output = result.stdout + result.stderr
    (out / (label + '.txt')).write_text(output)
    print(output, end='')
    result.check_returncode()
    samples = [dict((key, int(value)) for key, value in re.findall(r'(\w+)=(\d+)', line))
               for line in output.splitlines() if line.startswith('J701F_TERMINAL_LATENCY sample=')]
    if len(samples) != runs * 16 or output.count('J701F_TERMINAL_LATENCY_PASS') != runs or \
            'GUI_BENCHMARK_RAM_CLEANUP_OK' not in output:
        raise ValueError('Incomplete latency or cleanup evidence')
    if check_render and output.count('J701F_RENDER_CHECK_PASS') != runs:
        raise ValueError('Pixel comparison or interaction check failed')
    binary = re.search(r'J701F_GUI_BINARY_SHA ([a-f0-9]{64})', output)
    if not binary:
        raise ValueError('Compiled binary identity missing')
    (out / (label + '.json')).write_text(json.dumps(dict(
        source_sha256=hashes, binary_sha256=binary.group(1), samples=samples, runs=runs, full_render=full_render, poll_render=poll_render,
        full_image_pixel_comparison=check_render, framebuffer_accessed=False,
        input_devices_accessed=False, phone_persistent_files_modified=False,
        temporary_ram_files_cleaned=True,
        limits=['Measures PTY receipt, normal Qt paint and software image composition; excludes physical touch and framebuffer presentation.']), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phone', required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--runs', type=int, choices=range(1, 6), default=3)
    parser.add_argument('--check-render', action='store_true')
    parser.add_argument('--full-render', action='store_true')
    parser.add_argument('--poll-render', action='store_true')
    args = parser.parse_args()
    benchmark(args.phone, args.label, args.runs, args.check_render, args.full_render, args.poll_render)
