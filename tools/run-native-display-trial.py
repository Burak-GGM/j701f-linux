#!/usr/bin/env python3
"""Coordinated bounded RAM display trial, with a mandatory watchdog rehearsal.

No boot image writes. Stages temporary helpers, records before/after evidence,
and requires reboot into the same BOOT. Never plays sound or publishes data.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PHONE = os.environ.get('J701F_PHONE_IP') or (
    (ROOT / '.phone-ip').read_text().strip() if (ROOT / '.phone-ip').exists() else 'j701f.local')
ART = ROOT / 'build/kernel/display-runtime'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=5',
       '-o', 'StrictHostKeyChecking=yes', '-o', 'ServerAliveInterval=5',
       '-o', 'ServerAliveCountMax=1', '-o', 'UserKnownHostsFile=' + str(ROOT / 'build/phone-ssh-known-hosts'),
       'burak-alpine@' + PHONE]
IDENTITY = r'''import hashlib,json,os,struct,subprocess
from pathlib import Path
b=Path('/sys/kernel/notes').read_bytes(); offset=0; build_id=None
while offset+12<=len(b):
    ns,ds,kind=struct.unpack_from('<III',b,offset); offset+=12
    name=b[offset:offset+ns].rstrip(b'\0'); offset+=(ns+3)&~3
    value=b[offset:offset+ds]; offset+=(ds+3)&~3
    if name==b'GNU' and kind==3: build_id=value.hex()
boot=subprocess.check_output(['sudo','-n','sha256sum','/dev/mmcblk0p10'],text=True).split()[0]
print(json.dumps(dict(release=os.uname().release,build_id=build_id,boot_sha256=boot,
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
    uptime=Path('/proc/uptime').read_text().split()[0],
    pending=[name for name in ('j701f-gpufreq.pending','j701f-audio.pending')
             if (Path('/var/lib')/name).exists()],
    session={name:subprocess.run(['pidof',name],stdout=subprocess.DEVNULL).returncode==0
             for name in ('kwin_wayland','plasmashell')},
    drm={p.name:(p/'device/driver').resolve().name
         for p in Path('/sys/class/drm').glob('card*') if (p/'device/driver').exists()})))
'''


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remote(command, timeout=30, data=None):
    return subprocess.run(SSH + [command], input=data, text=True, capture_output=True,
                          timeout=timeout, check=True).stdout


def identity():
    return json.loads(remote('python3 -c ' + shlex.quote(IDENTITY), timeout=20))


def lock_check(seconds=300):
    lock = ROOT / 'build/coord/locks/phone'
    # Claude 2026-10-10: the display work was handed over by the owner while Codex
    # is away (docs/roadmap-2.md, B); either of us may hold the lock.
    require((lock/'owner').read_text().strip() in ('codex', 'claude'), 'Acquire the phone lock')
    require(int((lock/'time').read_text()) + 60*int((lock/'ttl').read_text()) > time.time()+seconds,
            'Renew phone lock')


def wait_startup_guards(before):
    # GPU limit raising starts 40 seconds after local.d, then keeps its crash
    # stamp for 180 seconds. An early empty stamp list is not a settled boot:
    # a reset could occur after that delayed job creates the stamp.
    for attempt in range(37):
        if not before['pending'] and float(before['uptime']) >= 240:
            return before
        if attempt % 3 == 0:
            print('WAIT_STARTUP_GUARDS uptime='+before['uptime']
                  +' pending='+','.join(before['pending']), flush=True)
        time.sleep(10)
        before = identity()
    raise RuntimeError('Boot has not settled past delayed startup guards; no trial armed')


def analyse_native(kms_log, kernel_log):
    def register(block, name):
        match = re.search(r'j701f-display-info: '+block+' '+name
                          +r' offset=0x[0-9a-f]+ value=(0x[0-9a-f]+)', kernel_log)
        return int(match.group(1), 16) if match else None
    fb_address = register('DECON', 'VIDW_ADD0')
    panel_reply = re.search(r'J701F_PANEL_DCS_POWER_MODE result=0 value=(0x[0-9a-f]{2})\b', kernel_log)
    # drm_mipi_dsi.h defines display/normal/sleep and partial/idle bits 2..6.
    # Both observed 0x9c and 0x1c have the requested core state; bit7 remains
    # recorded separately rather than guessed from a transport-success code.
    panel_ready = bool(panel_reply and int(panel_reply.group(1), 16) & 0x7c == 0x1c)
    checks = dict(
        modeset='NATIVE_MODESET_OK' in kms_log,
        flips_120=bool(re.search(r'NATIVE_FLIPS_OK count=120\b', kms_log)),
        panel_dcs_answer=panel_ready,
        native_framebuffer_address=fb_address is not None and 0x40000000 <= fb_address < 0xC0000000
            and fb_address != 0x67000000,
        dsi_resolution=register('DSIM', 'RESOL') == 0x050002D0,
        measured_horizontal_porch=register('DSIM', 'HPORCH') == 0x00380030,
        physical_dma=register('SYSMMU', 'CTRL') == 0)
    return checks, hex(fb_address) if fb_address else None


def analyse_pll(log):
    """Require fresh completion on the first attempt; retries cannot hide it."""
    pattern = (r'exynos-dsi 14800000\.dsi: J701F PLL completion=([01]) '
               r'mask_before=(0x[0-9a-f]+) mask_now=(0x[0-9a-f]+) '
               r'link_before=(0x[0-9a-f]+) link_now=(0x[0-9a-f]+) '
               r'pll_before=(0x[0-9a-f]+) reset_done=([01])')
    observations = []
    for match in re.finditer(pattern, log):
        completion, mask_before, mask_now, link_before, link_now, pll_before, reset = match.groups()
        observations.append(dict(completion=completion == '1', reset_done=reset == '1',
                                 mask_before=int(mask_before, 16), mask_now=int(mask_now, 16),
                                 link_before=int(link_before, 16), link_now=int(link_now, 16),
                                 pll_before=int(pll_before, 16)))
    errors = re.findall(r'exynos-dsi 14800000\.dsi: (PLL failed to stabilize|failed to configure DSI PLL)', log)
    first_ok = bool(observations and observations[0]['completion']
                    and observations[0]['reset_done']
                    and observations[0]['link_now'] & (1 << 24)
                    and not observations[0]['pll_before'] & (1 << 23))
    return dict(status='first-init-verified' if first_ok and not errors else
                ('inconclusive' if observations or errors else 'not-observed'),
                first_init_verified=first_ok and not errors,
                attempts=observations, errors=errors)


def analyse_prime(log):
    """Import/FB-object evidence only; this probe never scans out its buffer."""
    result = dict(status='not-run' if not log else 'inconclusive',
                  import_verified=False, framebuffer_object_verified=False,
                  scanout_performed=False)
    allocator = re.search(r'NATIVE_PRIME_ALLOCATOR (render|display)\b', log)
    result['allocator'] = allocator.group(1) if allocator else None
    buffer = re.search(r'NATIVE_PRIME_BUFFER width=720 height=1280 format=XRGB8888 '
                       r'stride=(\d+) modifier=(\d+)\b', log)
    if buffer:
        result.update(stride=int(buffer.group(1)), modifier=int(buffer.group(2)))
    rejected = re.search(r'NATIVE_PRIME_(IMPORT|FB)_REJECTED errno=(\d+)\b', log)
    if rejected:
        result.update(status='rejected', rejected_stage=rejected.group(1),
                      errno=int(rejected.group(2)))
    valid_buffer = bool(allocator and buffer and result['stride'] >= 2880 and result['modifier'] == 0)
    result['import_verified'] = valid_buffer and 'NATIVE_PRIME_IMPORT_OK' in log
    result['framebuffer_object_verified'] = (result['import_verified']
                                            and 'NATIVE_PRIME_SCANOUT_OBJECT_OK' in log
                                            and not rejected)
    if result['framebuffer_object_verified']:
        result['status'] = 'framebuffer-object-ready'
    return result


def analyse_egl(log):
    """A reported context renderer does not prove rendering or scanout."""
    renderer = re.search(r'^NATIVE_EGL_RENDERER=(.+)$', log, re.MULTILINE)
    path = re.search(r'^NATIVE_EGL_PATH=(render|display) DRM_DRIVER=(panfrost|exynos)$',
                     log, re.MULTILINE)
    ready = bool(path and renderer and 'NATIVE_EGL_CONTEXT_READY' in log)
    name = renderer.group(1) if renderer else None
    return dict(status='context-ready' if ready else ('inconclusive' if log else 'not-run'),
                path=path.group(1) if path else None, renderer=name,
                panfrost_t830_context=bool(ready and 'panfrost' in name.lower() and 'T830' in name
                                          and 'NATIVE_EGL_PANFROST_T830=1' in log),
                draw_verified=False, scanout_performed=False)


def analyse_shared_render(log):
    renderer = re.search(r'^NATIVE_SHARED_RENDERER=(.+)$', log, re.MULTILINE)
    buffer = re.search(r'NATIVE_SHARED_BUFFER width=720 height=1280 format=XRGB8888 '
                       r'stride=(\d+) modifier=0\b', log)
    checks = dict(panfrost_t830=bool(renderer and 'panfrost' in renderer.group(1).lower()
                                   and 'T830' in renderer.group(1)),
                  linear_buffer=bool(buffer and 2880 <= int(buffer.group(1)) <= 16384),
                  egl_image_import='NATIVE_SHARED_EGLIMAGE_IMPORT_OK' in log,
                  gpu_pixels='NATIVE_SHARED_GPU_RENDER_READBACK_OK pixels=4096' in log,
                  exported_cpu_pixels='NATIVE_SHARED_CPU_BUFFER_OK pixels=4096' in log)
    shared = all(checks.values())
    return dict(status='buffer-render-verified' if shared else ('inconclusive' if log else 'not-run'),
                checks=checks, renderer=renderer.group(1) if renderer else None,
                shared_gpu_buffer_verified=shared,
                framebuffer_object_verified=shared and 'NATIVE_SHARED_FB_OBJECT_OK' in log,
                scanout_performed=False)


def analyse_plasma(measurement, gears, support):
    """App swap FPS and native compositor binding, not proof of no CPU copies."""
    renderer = re.search(r'^\s*OpenGL renderer string:\s*(.+)$', support, re.M)
    app_renderer = re.search(r'^GEARS_GL_RENDERER=(.+)$', gears, re.M)
    sizes = re.findall(r'^GEARS_EGL_SIZE width=(\d+) height=(\d+)', gears, re.M)
    fps = [float(value) for value in re.findall(r'=\s*([0-9]+\.[0-9]+) FPS\b', gears)]
    # The first 5-second interval includes startup/geometry instrumentation.
    samples = fps[1:]
    geometry = tuple(map(int, sizes[-1])) if sizes else None
    gpu = lambda match: bool(match and 'panfrost' in match.group(1).lower() and 'T830' in match.group(1))
    good_samples = len(samples) >= 3 and all(0 < value <= 1000 for value in samples)
    mode = measurement.get('mode')
    drivers = measurement.get('drm_devices', {})
    native_opened = any(driver == 'exynos-drm' and '/dev/dri/'+name in measurement.get('kwin_drm_fds', [])
                        for name, driver in drivers.items())
    correct_path = ((mode == 'baseline' and 'simple-framebuffer' in drivers.values()) or
                    (mode == 'native' and native_opened and measurement.get('native_active_state')
                     and 'simple-framebuffer' not in drivers.values()))
    return dict(completed=measurement.get('completed', False),
                compositor_panfrost_t830=gpu(renderer), app_panfrost_t830=gpu(app_renderer),
                egl_size=geometry, fps_samples=samples,
                median_app_swap_fps=statistics.median(samples) if good_samples else None,
                measurement_valid=bool(measurement.get('completed') and correct_path and gpu(renderer)
                                       and gpu(app_renderer) and geometry and min(geometry) > 0 and good_samples),
                native_drm_opened=native_opened, path_verified=correct_path,
                scanout_copy_verified_absent=False, physical_appearance='unseen')


def require_native_prerequisite(previous, report):
    require(previous.get('automatic_return_verified') and previous.get('native_hardware_verified')
            and previous.get('pll_initialization', {}).get('first_init_verified')
            and previous.get('shared_buffer_render', {}).get('shared_gpu_buffer_verified')
            and previous.get('shared_buffer_render', {}).get('framebuffer_object_verified')
            and previous.get('before', {}).get('boot_sha256') == report['baseline_boot_sha256']
            and previous.get('source_build', {}).get('kernel_image_sha256') == report['kernel_image_sha256'],
            'Plasma requires successful same-BOOT native/PLL/shared-GPU trial')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true', required=True)
    p.add_argument('--label', required=True)
    p.add_argument('--rehearsal', action='store_true')
    p.add_argument('--rehearsal-report', type=Path)
    p.add_argument('--prime-probe', action='store_true',
                   help='Compare GBM import paths and EGL renderers; no GPU scanout')
    p.add_argument('--plasma-probe', action='store_true', help='Bounded native Plasma and matched gears benchmark')
    p.add_argument('--native-report', type=Path, help='Successful same-BOOT native/PLL/shared-GPU prerequisite')
    a = p.parse_args()
    require(not (a.rehearsal and a.prime_probe), 'PRIME probe requires a native trial')
    require(not (a.plasma_probe and (a.rehearsal or a.prime_probe)),
            'Plasma is a separate trial after PRIME verification')
    require(re.fullmatch('[a-z0-9-]{1,40}', a.label), 'Simple unique run label required')
    lock_check(600)
    report = json.loads((ART/'report.json').read_text())
    slot = json.loads((ROOT/'build/kernel/boot-slot.json').read_text())
    require(report['baseline_boot_sha256'] == slot['boot_partition_sha256'], 'Rebuild for current BOOT')
    require(report['kernel_image_sha256'] == sha(ROOT/'build/kernel/panfrost/Image'), 'Rebuild for current kernel')
    if a.plasma_probe:
        require(a.native_report is not None, 'Provide successful native/PLL/shared-GPU report')
        require_native_prerequisite(json.loads(a.native_report.read_text()), report)
    if not a.rehearsal:
        require(a.rehearsal_report is not None, 'Provide successful watchdog rehearsal report')
        rehearsal = json.loads(a.rehearsal_report.read_text())
        require(rehearsal.get('mode') == 'watchdog-rehearsal' and rehearsal.get('automatic_return_verified')
                and rehearsal.get('rehearsal_reset_log_seen')
                and rehearsal['before']['boot_sha256'] == report['baseline_boot_sha256'],
                'Rehearsal must prove automatic return on this BOOT')
    local = ART/'runs'/a.label
    local.mkdir(parents=True, exist_ok=False)
    before = wait_startup_guards(identity())
    require(all(before['session'].values()) and 'simple-framebuffer' in before['drm'].values(),
            'Working baseline Plasma/simpledrm session required')
    require(before['boot_sha256'] == report['baseline_boot_sha256']
            and before['build_id'] == report['kernel_build_id'], 'Running kernel/BOOT does not match modules')
    state = dict(mode='watchdog-rehearsal' if a.rehearsal else 'native-display',
                 before=before, automatic_return_verified=False, panel_appearance='unseen',
                 boot_written=False, recovery_written=False, source_build=report)
    state['prime_probe_requested'] = a.prime_probe
    state['plasma_probe_requested'] = a.plasma_probe
    (local/'result.json').write_text(json.dumps(state, indent=2)+'\n')
    phone = '/home/burak-alpine/j701f/display-runtime/' + a.label
    remote('umask 077; mkdir -p ' + shlex.quote(str(Path(phone).parent))
           + '; mkdir ' + shlex.quote(phone))
    files = [ROOT/'tools/display-trial-supervisor.py']
    if not a.rehearsal:
        files += [ROOT/'tools/native-display-trial.sh', ROOT/'tools/native-display-kms.c',
                  ART/'j701f-display-overlay.ko', ART/'j701f-panel-status.ko',
                  ROOT/'build/kernel/ea8061s-prototype/panel-j701f-ea8061s.ko',
                  ROOT/'build/kernel/ea8061s-prototype/j701f-display-info.ko']
        if a.prime_probe:
            files += [ROOT/'tools/native-display-prime.c', ROOT/'tools/native-display-egl.c',
                      ROOT/'tools/native-display-dmabuf.c']
        if a.plasma_probe:
            files += [ROOT/'tools/native-display-gui.py', ROOT/'tools/native-display-gears-info.c']
        require(sha(ART/'j701f-display-overlay.ko') == report['module_sha256'], 'Overlay module changed')
        require(sha(ART/'j701f-panel-status.ko') == report['status_module_sha256'], 'DCS module changed')
        panel = json.loads((ROOT/'build/kernel/ea8061s-prototype/report.json').read_text())
        require(panel['kernel_image_sha256'] == report['kernel_image_sha256'], 'Panel kernel mismatch')
        for name in ('panel-j701f-ea8061s', 'j701f-display-info'):
            require(sha(ROOT/'build/kernel/ea8061s-prototype'/(name+'.ko')) == panel[name]['module_sha256'],
                    'Panel/probe bytes changed')
    scp = ['scp'] + SSH[1:-1] + list(map(str, files)) + [SSH[-1]+':'+phone+'/']
    subprocess.run(scp, check=True, timeout=45)
    if not a.rehearsal:
        remote('test -f /usr/include/xf86drm.h || sudo -n apk add libdrm-dev', timeout=90)
        remote('cd '+shlex.quote(phone)+'; cc -std=c11 -D_GNU_SOURCE -Wall -Wextra -Werror '
               '-I/usr/include/libdrm native-display-kms.c -ldrm -o native-display-kms', timeout=30)
        if a.plasma_probe:
            remote('set -eu; test -x /usr/bin/es2gears_wayland; test -x /usr/bin/qdbus6; '
                   'test -x /usr/bin/kscreen-doctor; cd '+shlex.quote(phone)
                   +'; cc -std=c11 -Wall -Wextra -Werror -fPIC -shared '
                    'native-display-gears-info.c -lEGL -lGLESv2 -ldl -o native-display-gears-info.so', timeout=30)
        if a.prime_probe:
            remote('test -f /usr/include/gbm.h; cd '+shlex.quote(phone)
                   +'; cc -std=c11 -D_GNU_SOURCE -Wall -Wextra -Werror -I/usr/include/libdrm '
                    'native-display-prime.c -ldrm -lgbm -o native-display-prime', timeout=30)
            remote('cd '+shlex.quote(phone)
                   +'; cc -std=c11 -D_GNU_SOURCE -Wall -Wextra -Werror -I/usr/include/libdrm '
                    'native-display-egl.c -ldrm -lgbm -lEGL -lGLESv2 -o native-display-egl', timeout=30)
            remote('cd '+shlex.quote(phone)
                   +'; cc -std=c11 -D_GNU_SOURCE -Wall -Wextra -Werror -I/usr/include/libdrm '
                    'native-display-dmabuf.c -ldrm -lgbm -lEGL -lGLESv2 -o native-display-dmabuf', timeout=30)
        hashes = ''.join(sha(f)+'  '+f.name+'\n' for f in files)
        remote('cat > '+shlex.quote(phone+'/hashes.sha256'), data=hashes)
        remote('cd '+shlex.quote(phone)+'; sha256sum native-display-kms >> hashes.sha256')
        if a.prime_probe:
            remote('cd '+shlex.quote(phone)
                   +'; sha256sum native-display-prime native-display-egl native-display-dmabuf >> hashes.sha256')
        if a.plasma_probe:
            remote('cd '+shlex.quote(phone)+'; sha256sum native-display-gears-info.so '
                   '/usr/bin/es2gears_wayland >> gears-binary-hashes.txt; '
                   'sha256sum native-display-gears-info.so >> hashes.sha256')
    lock_check()
    mode = ('--rehearsal --seconds 10' if a.rehearsal else
            '--seconds '+('180' if a.plasma_probe else ('150' if a.prime_probe else '90'))
            +' --trial '+phone+'/native-display-trial.sh')
    command = 'cd '+shlex.quote(phone)+'; nohup sudo -n python3 -u display-trial-supervisor.py --execute '+mode
    command += ' > supervisor.log 2>&1 < /dev/null & echo $!'
    pid = remote(command).strip()
    print('ARMED_RUN', a.label, 'remote_pid', pid, flush=True)
    deadline = time.monotonic() + (150 if a.rehearsal else (300 if a.plasma_probe else 240))
    after = None
    while time.monotonic() < deadline:
        time.sleep(6)
        try:
            boot_id = remote('cat /proc/sys/kernel/random/boot_id', timeout=10).strip()
            if boot_id != before['boot_id']:
                candidate = identity()
                after = candidate
                if all(candidate['session'].values()) and 'simple-framebuffer' in candidate['drm'].values():
                    break
        except (subprocess.SubprocessError, ValueError):
            pass
    for name in ('supervisor.log', 'trial.log', 'kms.log', 'prime.log', 'prime-display.log',
                 'egl-render.log', 'egl-display.log', 'shared-render.log', 'dmesg.txt',
                 'dmesg-follow.txt', 'dmesg-after-overlay.txt', 'plasma-baseline.json', 'plasma-native.json',
                 'plasma-baseline-gears.log', 'plasma-native-gears.log', 'plasma-baseline-support.log',
                 'plasma-native-support.log', 'plasma-native-drm-state.txt', 'plasma-start.log',
                 'gears-binary-hashes.txt'):
        try:
            # The root trial inherits umask 077, so its logs are deliberately
            # not readable by the SSH account without sudo.
            content = remote('sudo -n cat '+shlex.quote(phone+'/'+name), timeout=15)
            (local/name).write_text(content)
        except subprocess.SubprocessError:
            pass
    if after:
        for name, command in (
            ('dmesg-after-reset.txt', 'sudo -n dmesg'),
            ('pstore-after-reset.txt', 'sudo -n sh -c '+shlex.quote(
                'for f in /sys/fs/pstore/*; do [ -f "$f" ] || continue; '
                'echo "PSTORE $f"; cat "$f"; done'))):
            try:
                (local/name).write_text(remote(command, timeout=20))
            except subprocess.SubprocessError:
                pass
    state['after'] = after
    state['automatic_return_verified'] = bool(after and after['boot_sha256'] == before['boot_sha256']
                                               and after['build_id'] == before['build_id']
                                               and all(after['session'].values())
                                               and 'simple-framebuffer' in after['drm'].values())
    state['rehearsal_reset_log_seen'] = (local/'supervisor.log').is_file() and \
        'DISPLAY_TRIAL_WATCHDOG_RESET_PENDING' in (local/'supervisor.log').read_text()
    if not a.rehearsal:
        kms_log = (local/'kms.log').read_text() if (local/'kms.log').exists() else ''
        kernel_log = (local/'dmesg.txt').read_text() if (local/'dmesg.txt').exists() else ''
        state['native_checks'], state['native_framebuffer_address'] = analyse_native(kms_log, kernel_log)
        state['native_hardware_verified'] = all(state['native_checks'].values())
        reply = re.search(r'J701F_PANEL_DCS_POWER_MODE result=0 value=(0x[0-9a-f]{2})\b', kernel_log)
        state['panel_power_mode'] = reply.group(1) if reply else None
        state['pll_initialization'] = analyse_pll(kernel_log)
        prime_log = (local/'prime.log').read_text() if (local/'prime.log').exists() else ''
        state['prime_probe'] = analyse_prime(prime_log)
        display_log = (local/'prime-display.log').read_text() if (local/'prime-display.log').exists() else ''
        state['display_gbm_probe'] = analyse_prime(display_log)
        state['egl_contexts'] = {}
        for kind in ('render', 'display'):
            path = local/('egl-'+kind+'.log')
            state['egl_contexts'][kind] = analyse_egl(path.read_text() if path.exists() else '')
        path = local/'shared-render.log'
        state['shared_buffer_render'] = analyse_shared_render(path.read_text() if path.exists() else '')
        if a.plasma_probe:
            state['plasma'] = {}
            for kind in ('baseline', 'native'):
                data_path = local/('plasma-'+kind+'.json')
                measurement = json.loads(data_path.read_text()) if data_path.exists() else {}
                read_log = lambda suffix: ((local/('plasma-'+kind+suffix)).read_text()
                                           if (local/('plasma-'+kind+suffix)).exists() else '')
                state['plasma'][kind] = analyse_plasma(measurement, read_log('-gears.log'), read_log('-support.log'))
            baseline, native = state['plasma']['baseline'], state['plasma']['native']
            state['plasma']['same_surface_comparison'] = bool(baseline['measurement_valid']
                    and native['measurement_valid'] and baseline['egl_size'] == native['egl_size'])
            policies = []
            for kind in ('baseline', 'native'):
                data_path = local/('plasma-'+kind+'.json')
                measurement = json.loads(data_path.read_text()) if data_path.exists() else {}
                policies.append(measurement.get('clock_policy', {}))
                dimensions = measurement.get('screenshot_dims', '').split()
                if measurement.get('screenshot_status') == 0 and len(dimensions) == 4 \
                        and all(value.isdigit() for value in dimensions):
                    width, height, stride, fmt = map(int, dimensions)
                    if 0 < width <= 1280 and 0 < height <= 1280 and width*4 <= stride <= 5120 and fmt in (5, 6):
                        raw = local/('plasma-'+kind+'.raw')
                        transfer = ['scp'] + SSH[1:-1] + [SSH[-1]+':'+phone+'/'+raw.name, str(raw)]
                        copied = subprocess.run(transfer, timeout=30, capture_output=True)
                        if copied.returncode == 0 and raw.stat().st_size == stride*height:
                            subprocess.run(['python3', str(ROOT/'tools/raw-to-png.py'), str(raw),
                                            str(raw.with_suffix('.png')), str(width), str(height), str(stride)], check=True)
                            state['plasma'][kind]['screenshot_png'] = str(raw.with_suffix('.png'))
            state['plasma']['same_clock_policy'] = bool(policies[0] and policies[0] == policies[1])
            state['plasma']['comparison_valid'] = (state['plasma']['same_surface_comparison']
                                                   and state['plasma']['same_clock_policy'])
            state['plasma']['native_to_baseline_fps_ratio'] = (
                native['median_app_swap_fps']/baseline['median_app_swap_fps']
                if state['plasma']['comparison_valid'] else None)
    (local/'result.json').write_text(json.dumps(state, indent=2)+'\n')
    print(json.dumps({'result':str(local/'result.json'), 'automatic_return_verified':state['automatic_return_verified']}))
    require(state['automatic_return_verified'] and state['rehearsal_reset_log_seen'],
            'Automatic reset/return not proved; inspect phone and saved logs before proceeding')
    if not a.rehearsal:
        require(state['native_hardware_verified'],
                'Phone returned safely; native hardware checks incomplete. Inspect saved trial/KMS/kernel logs')
        if a.plasma_probe:
            require(state['plasma']['baseline']['measurement_valid'] and state['plasma']['native']['measurement_valid'],
                    'Phone returned safely; Plasma measurement incomplete. Inspect captured GUI logs')
            require(state['plasma']['comparison_valid'],
                    'Phone returned safely; geometry or clock policy differs, so FPS cannot be directly compared')


if __name__ == '__main__':
    main()
