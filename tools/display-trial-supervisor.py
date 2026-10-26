#!/usr/bin/env python3
"""Phone-side bounded display experiment. Always resets into unchanged BOOT.

Not a service. Run detached as root after taking the coordination phone lock.
The watchdog fd stays open, is never inherited by the experiment, and is never
magic-closed. First run --rehearsal (no display changes) to prove real reset.
"""
import argparse
import array
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import time

WDIOC_SETTIMEOUT = 0xC0045706  # Linux _IOWR('W', 6, int)
WDIOC_GETTIMEOUT = 0x80045707  # Linux _IOR('W', 7, int)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute', action='store_true', required=True)
    p.add_argument('--seconds', type=int, default=90)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--rehearsal', action='store_true')
    mode.add_argument('--trial', type=Path)
    a = p.parse_args()
    if os.geteuid() != 0 or not 10 <= a.seconds <= 180:
        raise SystemExit('Root and a deadline of 10..180 seconds required')
    machine = Path('/sys/firmware/devicetree/base/compatible').read_bytes().split(b'\0')
    if b'samsung,j7velte' not in machine or not os.uname().release.startswith('7.1.13-'):
        raise SystemExit('Expected J701F mainline system')
    keep = Path('/sys/module/s3c2410_wdt/parameters/keep_on_shutdown')
    if keep.read_text().strip() not in ('Y', '1'):
        raise SystemExit('Watchdog must survive a stuck shutdown')
    if a.trial:
        a.trial = a.trial.resolve(strict=True)
        if not a.trial.is_file():
            raise SystemExit('Trial script missing')
    # Ignore connection/process-group loss. SIGKILL still stops feeding the
    # hardware, so it resets the unchanged known-good BOOT image.
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    os.sync()
    fd = os.open('/dev/watchdog', os.O_WRONLY | os.O_CLOEXEC)
    timeout = array.array('i', [15])
    fcntl.ioctl(fd, WDIOC_SETTIMEOUT, timeout, True)
    fcntl.ioctl(fd, WDIOC_GETTIMEOUT, timeout, True)
    if not 5 <= timeout[0] <= 30:
        raise SystemExit('Unexpected watchdog timeout; no display changes started')
    os.write(fd, b'.')
    print(f'DISPLAY_TRIAL_ARMED deadline={a.seconds}s watchdog={timeout[0]}s '
          f'boot_id={Path("/proc/sys/kernel/random/boot_id").read_text().strip()}', flush=True)
    child = None
    started = time.monotonic()
    if a.trial:
        env = dict(os.environ, J701F_DISPLAY_TRIAL_ARMED='1',
                   J701F_DISPLAY_SUPERVISOR_PID=str(os.getpid()))
        child = subprocess.Popen(['/bin/sh', str(a.trial)], start_new_session=True,
                                 close_fds=True, env=env)
    while time.monotonic() - started < a.seconds:
        if child is not None and child.poll() is not None:
            print(f'DISPLAY_TRIAL_CHILD_EXIT status={child.returncode}', flush=True)
            break
        os.write(fd, b'.')
        time.sleep(1)
    # Leave fd open and stop all feeding. No orderly reboot hook can clear or
    # mask the result: the rehearsal and real trial use the same hardware reset.
    print('DISPLAY_TRIAL_END: syncing then ceasing watchdog keepalives', flush=True)
    os.sync()
    print('DISPLAY_TRIAL_WATCHDOG_RESET_PENDING', flush=True)
    # The hardware reset does not run filesystem shutdown hooks. Persist the
    # final marker too, not only the messages preceding the first sync.
    os.sync()
    while True:
        time.sleep(1)


if __name__ == '__main__':
    main()
