#!/usr/bin/env python3
"""One bounded Plasma measurement inside the proved display watchdog trial.

Not a launcher/service. No configuration, runlevel or boot image is written.
The native phase restarts existing SDDM; the parent watchdog always resets.
"""
import argparse
import json
import os
from pathlib import Path
import pty
import pwd
import re
import select
import signal
import stat
import subprocess
import time


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def command(argv, **kwargs):
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=10, **kwargs)


def session():
    pids = command(['pidof', 'kwin_wayland']).stdout.split()
    require(len(pids) == 1 and pids[0].isdigit(), 'Exactly one compositor required')
    pid = int(pids[0])
    root = Path('/proc') / str(pid)
    user = pwd.getpwnam('burak-alpine')
    require(user.pw_uid == 1000 and root.stat().st_uid == user.pw_uid,
            'Expected owner compositor')
    groups = os.getgrouplist(user.pw_name, user.pw_gid)
    identity = dict(user=user.pw_uid, group=user.pw_gid, extra_groups=groups)
    environ = dict(item.split('=', 1) for item in root.joinpath('environ').read_bytes()
                   .decode().split('\0') if '=' in item)
    # Claude 2026-10-10: the compositor's own environment has no WAYLAND_DISPLAY
    # (it creates the socket); the first trial stopped here. Fill what is missing
    # from the owner's plasmashell, which is a client of that compositor.
    for shell in command(['pidof', 'plasmashell']).stdout.split():
        other = Path('/proc') / shell
        if shell.isdigit() and other.stat().st_uid == user.pw_uid:
            for item in other.joinpath('environ').read_bytes().decode().split('\0'):
                if '=' in item:
                    environ.setdefault(*item.split('=', 1))
            break
    env = dict(HOME=user.pw_dir, USER=user.pw_name, LOGNAME=user.pw_name,
               PATH='/usr/local/bin:/usr/bin:/bin', LANG='C.UTF-8', QT_QPA_PLATFORM='wayland')
    for key in ('XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
        require(key in environ, 'Session variable missing: '+key)
        env[key] = environ[key]
    require(env['XDG_RUNTIME_DIR'] == '/run/user/1000' and
            re.fullmatch(r'wayland-[0-9]+', env['WAYLAND_DISPLAY']), 'Unexpected Wayland endpoint')
    endpoint = Path(env['XDG_RUNTIME_DIR']) / env['WAYLAND_DISPLAY']
    require(stat.S_ISSOCK(endpoint.stat().st_mode) and endpoint.stat().st_uid == user.pw_uid,
            'Expected owner Wayland socket')
    scope = root.joinpath('cgroup').read_text().strip()
    match = re.fullmatch(r'0::/(c[0-9]+)', scope)
    require(match is not None, 'Expected local SDDM scope')
    identifier = match.group(1)
    details = command(['loginctl', 'show-session', identifier, '-p', 'Type', '-p', 'Service']).stdout
    require('Type=wayland' in details and
            ('Service=sddm\n' in details or 'Service=sddm-autologin\n' in details),
            'Expected SDDM Wayland session')
    return pid, identifier, env, identity


def sample_gears(env, identity, seconds=26):
    master, slave = pty.openpty()
    process = None
    data = bytearray()
    app_env = dict(env, LD_PRELOAD=str(Path('native-display-gears-info.so').resolve()))
    try:
        process = subprocess.Popen(['/usr/bin/es2gears_wayland'], env=app_env, **identity,
                                   stdin=subprocess.DEVNULL, stdout=slave, stderr=slave,
                                   start_new_session=True, close_fds=True)
        os.close(slave)
        slave = -1
        started = last_activity = time.monotonic()
        while process.poll() is None and time.monotonic()-started < seconds:
            if time.monotonic()-last_activity > 4:
                command(['/usr/bin/qdbus6', 'org.freedesktop.ScreenSaver', '/ScreenSaver',
                         'org.freedesktop.ScreenSaver.SimulateUserActivity'], env=env, **identity)
                last_activity = time.monotonic()
            if select.select([master], [], [], 0.2)[0]:
                try:
                    chunk = os.read(master, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                data.extend(chunk)
                require(len(data) <= 262144, 'Benchmark output unexpectedly large')
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
        os.close(master)
        if slave >= 0:
            os.close(slave)
    return data.decode(errors='replace')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('baseline', 'native'))
    args = parser.parse_args()
    require(os.geteuid() == 0 and os.environ.get('J701F_DISPLAY_TRIAL_ARMED') == '1',
            'Only inside armed root display trial')
    supervisor = os.environ.get('J701F_DISPLAY_SUPERVISOR_PID', '')
    require(supervisor.isdigit(), 'Watchdog supervisor missing')
    parent = Path('/proc') / str(os.getppid()) / 'status'
    require(re.search(r'^PPid:\s+'+supervisor+r'\s*$', parent.read_text(), re.M),
            'Trial must remain a child of watchdog supervisor')
    os.kill(int(supervisor), 0)
    out = Path('plasma-'+args.mode+'.json')
    result = dict(mode=args.mode, completed=False, scanout_copy_verified_absent=False,
                  physical_appearance='unseen')
    try:
        if args.mode == 'native':
            # Only service runtime changes. Existing session/autologin config
            # stays intact, and no native path is enabled on the next boot.
            command(['rc-service', 'sddm', 'zap'])
            start = command(['rc-service', 'sddm', 'start'])
            Path('plasma-start.log').write_text(start.stdout)
            for attempt in range(35):
                if command(['pidof', 'kwin_wayland']).returncode == 0 and \
                        command(['pidof', 'plasmashell']).returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError('Native Plasma did not start in time')
            time.sleep(15)  # Let session startup finish before measuring.
        pid, identifier, env, identity = session()
        require(command(['loginctl', 'unlock-session', identifier]).returncode == 0,
                'Session unlock failed')
        require(command(['/usr/bin/kscreen-doctor', '--dpms', 'on'], env=env, **identity).returncode == 0,
                'Output could not be woken')
        require(command(['/usr/bin/qdbus6', 'org.freedesktop.ScreenSaver', '/ScreenSaver',
                         'org.freedesktop.ScreenSaver.SimulateUserActivity'], env=env, **identity).returncode == 0,
                'Could not keep benchmark visible')
        time.sleep(2)  # Allow the asynchronous wake/modeset to finish.
        command(['/usr/bin/qdbus6', 'org.kde.plasmashell', '/Mobile',
                 'org.kde.plasmashell.closeActionDrawer'], env=env, **identity)
        support = command(['/usr/bin/qdbus6', 'org.kde.KWin', '/KWin',
                           'org.kde.KWin.supportInformation'], env=env, **identity)
        require(support.returncode == 0, 'Compositor information unavailable')
        Path('plasma-'+args.mode+'-support.log').write_text(support.stdout)
        outputs = command(['/usr/bin/kscreen-doctor', '-j'], env=env, **identity)
        require(outputs.returncode == 0, 'Output information unavailable')
        result['outputs'] = json.loads(outputs.stdout)
        result['kwin_pid'] = pid
        result['clock_policy'] = {}
        for name, path in (
            ('cpu_min_khz', '/sys/devices/system/cpu/cpufreq/policy0/scaling_min_freq'),
            ('cpu_max_khz', '/sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq'),
            ('cpu_governor', '/sys/devices/system/cpu/cpufreq/policy0/scaling_governor'),
            ('gpu_min_hz', '/sys/class/devfreq/11400000.gpu/min_freq'),
            ('gpu_max_hz', '/sys/class/devfreq/11400000.gpu/max_freq')):
            result['clock_policy'][name] = Path(path).read_text().strip()
        result['load_before'] = Path('/proc/loadavg').read_text().strip()
        result['drm_devices'] = {p.name: (p/'device/driver').resolve().name
                                 for p in Path('/sys/class/drm').glob('card[0-9]*')
                                 if re.fullmatch(r'card[0-9]+', p.name) and (p/'device/driver').exists()}
        result['kwin_drm_fds'] = []
        for fd in (Path('/proc')/str(pid)/'fd').iterdir():
            try:
                target = os.readlink(fd)
                if re.fullmatch(r'/dev/dri/(card[0-9]+|renderD[0-9]+)', target):
                    result['kwin_drm_fds'].append(target)
            except FileNotFoundError:
                pass
        if args.mode == 'native':
            require('simple-framebuffer' not in result['drm_devices'].values(), 'Firmware DRM still present')
            cards = [name for name, driver in result['drm_devices'].items() if driver == 'exynos-drm']
            require(len(cards) == 1 and '/dev/dri/'+cards[0] in result['kwin_drm_fds'],
                    'Compositor has not opened native DRM device')
            minor = os.minor(os.stat('/dev/dri/'+cards[0]).st_rdev)
            state = Path('/sys/kernel/debug/dri')/str(minor)/'state'
            current = state.read_text()
            Path('plasma-native-drm-state.txt').write_text(current)
            result['native_active_state'] = bool(re.search(r'^\s*active=1\s*$', current, re.M)
                                                 and re.search(r'^\s*fb=[1-9][0-9]*\s*$', current, re.M))
            require(result['native_active_state'], 'Native CRTC/framebuffer is not active')
        screenshot = Path('/home/burak-alpine/.local/bin/kwin-screenshot')
        if screenshot.is_file():
            capture = command([str(screenshot), str(Path('plasma-'+args.mode+'.raw').resolve())],
                              env=env, **identity)
            result['screenshot_status'] = capture.returncode
            result['screenshot_dims'] = capture.stdout.strip()
        backlight = Path('/sys/class/backlight/j701f-panel/brightness')
        previous = backlight.read_text() if backlight.exists() else None
        result['software_backlight_before'] = previous.strip() if previous else None
        try:
            if previous is not None:
                backlight.write_text('255\n')
            time.sleep(2)
            log = sample_gears(env, identity)
            Path('plasma-'+args.mode+'-gears.log').write_text(log)
        finally:
            if previous is not None and backlight.exists():
                backlight.write_text(previous)
        # Claude 2026-10-10 (roadmap 2, B.3): the native panel driver now has its
        # own backlight device. Step through a few levels, note whether each
        # write was accepted and whether the kernel logged a DSI complaint, and
        # end at full brightness. What the panel shows is not seen from here.
        if args.mode == 'native' and backlight.exists():
            steps = []
            marker = len(command(['dmesg']).stdout)
            for level in (128, 20, 1, 200, 255):
                entry = dict(level=level)
                try:
                    backlight.write_text('%d\n' % level)
                    time.sleep(1.5)
                    entry['read_back'] = backlight.read_text().strip()
                except OSError as error:
                    entry['error'] = str(error)
                steps.append(entry)
            result['native_backlight'] = dict(
                device=str((backlight.parent/'device').resolve()),
                max=(backlight.parent/'max_brightness').read_text().strip(),
                steps=steps,
                kernel_messages=[line for line in command(['dmesg']).stdout[marker:].splitlines()
                                 if re.search(r'dsi|panel|ea8061|decon', line, re.I)][-20:])
        # Claude 2026-10-10 (roadmap 2, B.4): one screen-off / screen-on cycle
        # through the compositor, then a short benchmark to see that frames
        # flow again. Panel power is taken away and given back by the driver.
        if args.mode == 'native':
            cycle = dict()
            marker = len(command(['dmesg']).stdout)
            active = lambda: bool(re.search(r'^\s*active=1\s*$', state.read_text(), re.M))
            cycle['off_status'] = command(['/usr/bin/kscreen-doctor', '--dpms', 'off'], env=env, **identity).returncode
            time.sleep(5)
            cycle['active_while_off'] = active()
            cycle['on_status'] = command(['/usr/bin/kscreen-doctor', '--dpms', 'on'], env=env, **identity).returncode
            command(['/usr/bin/qdbus6', 'org.freedesktop.ScreenSaver', '/ScreenSaver',
                     'org.freedesktop.ScreenSaver.SimulateUserActivity'], env=env, **identity)
            time.sleep(4)
            cycle['active_after_on'] = active()
            cycle['gears_after_on'] = re.findall(r'= ([0-9.]+) FPS', sample_gears(env, identity, seconds=12))
            cycle['kernel_messages'] = [line for line in command(['dmesg']).stdout[marker:].splitlines()
                                        if re.search(r'dsi|panel|ea8061|decon|exynos-drm', line, re.I)][-25:]
            result['native_blank_cycle'] = cycle
        result['completed'] = True
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        out.write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
