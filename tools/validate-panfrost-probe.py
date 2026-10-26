#!/usr/bin/env python3
"""Compile/check the rendering probe in existing Alpine phone RAM only."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import secrets
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel'


def validate(phone):
    ipaddress.IPv4Address(phone)
    source = ROOT / 'tools/panfrost-render-probe.c'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    options = ['-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-i', str(Path.home() / '.ssh/id_ed25519'),
               '-o', 'StrictHostKeyChecking=yes', '-o', 'UserKnownHostsFile=' + str(ROOT / 'build/phone-ssh-known-hosts'),
               '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=1']
    host = 'burak-alpine@' + phone
    remote = '/tmp/j701f-panfrost-probe-' + secrets.token_hex(6)
    # Validate the filesystem before copying anything; no persistent upload fallback.
    subprocess.run(['ssh', *options, host, "awk '$2 == \"/tmp\" && $3 == \"tmpfs\" {found=1} END {exit !found}' /proc/mounts"],
                   check=True, timeout=20)
    subprocess.run(['scp', *options, str(source), host + ':' + remote + '.c'], check=True, timeout=20)
    script = '''set -eu
trial=$1
cleanup() { rm -rf "$trial"; rm -f "$trial.c"; }
trap cleanup EXIT
trap 'exit 143' HUP INT TERM
mkdir -m 700 "$trial"
actual=$(sha256sum "$trial.c")
[ "${actual%% *}" = SOURCE_SHA ]
mv "$trial.c" "$trial/probe.c"
export HOME="$trial" TMPDIR="$trial" XDG_CACHE_HOME="$trial/cache"
export MESA_SHADER_CACHE_DISABLE=true
cc -O2 -Wall -Wextra -Werror "$trial/probe.c" $(pkg-config --cflags --libs egl glesv2 gbm libdrm) -o "$trial/probe"
uname -r
status=0
"$trial/probe" --inspect || status=$?
[ "$status" = 0 ] || [ "$status" = 2 ]
# Run only the explicitly labeled software pipeline test, never --render.
LIBGL_ALWAYS_SOFTWARE=1 timeout 20 "$trial/probe" --self-test
cleanup
trap - EXIT HUP INT TERM
[ ! -e "$trial" ] && [ ! -e "$trial.c" ]
printf 'PANFROST_PROBE_RAM_CLEANUP_OK\\n'
'''.replace('SOURCE_SHA', digest)
    result = subprocess.run(['ssh', *options, host, 'sh -s -- ' + remote], input=script,
                            text=True, capture_output=True, timeout=60)
    (OUT / 'phone-panfrost-probe-validation.txt').write_text(result.stdout + result.stderr)
    result.check_returncode()
    if ('PANFROST_PROBE_RAM_CLEANUP_OK' not in result.stdout or
            'PIPELINE_SELF_TEST_PASS' not in result.stdout):
        raise ValueError('Software pipeline or RAM cleanup was not confirmed')
    (OUT / 'panfrost-probe-validation-report.json').write_text(json.dumps(dict(
        status='passed', source_sha256=digest, native_aarch64_compilation=True,
        drm_identity_inspected=True, software_shader_pixels_verified=4096,
        temporary_ram_files_cleaned=True, phone_persistent_files_modified=False,
        partitions_modified=False, mainline_kernel_boot_tested=False,
        hardware_acceleration_verified=False,
        limits=['Software shader/readback test and DRM inventory only; --render was not run.',
                'No on-screen GUI or input device was accessed.']), indent=2)+'\n')
    print(result.stdout, end='')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phone', required=True, help='IPv4 address of the pinned Alpine phone')
    validate(parser.parse_args().phone)
