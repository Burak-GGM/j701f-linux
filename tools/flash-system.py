#!/usr/bin/env python3
"""Verified BOOT/USERDATA installer; default prints a plan and never flashes."""
import argparse
import importlib.util
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def commands(device, boot_only=False, reboot=False, data_only=False):
    tool = str(ROOT / 'tools/odin4')
    directory = ROOT / 'build/system'
    result = []
    if not boot_only:
        result.append([tool, '-a', str(directory / 'userdata.tar'), '-d', device])
    if data_only: return result
    final = [tool, '-a', str(directory / 'boot.tar'), '-d', device]
    if reboot: final.append('--reboot')
    result.append(final)
    return result


def listed_devices():
    result = subprocess.run([str(ROOT / 'tools/odin4'), '-l'], check=True,
                            capture_output=True, text=True, timeout=15)
    return re.findall(r'(?m)^\s*(/dev/bus/usb/[0-9]{3}/[0-9]{3})\s*$', result.stdout)


def verify():
    spec = importlib.util.spec_from_file_location('builder', ROOT / 'tools/build-system.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.verify_bundle()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='Actually write the verified images')
    parser.add_argument('--device', help='Exact Download Mode USB path from tools/odin4 -l')
    parser.add_argument('--discard-existing-data', action='store_true', help='Acknowledge replacement of Android DATA and internal-storage files')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--data-only', action='store_true', help='Write DATA only, then return to recovery for read-back validation')
    selection.add_argument('--boot-only', action='store_true', help='Resume BOOT step after DATA was already successfully flashed')
    parser.add_argument('--reboot', action='store_true', help='Request normal reboot only after the final BOOT flash')
    args = parser.parse_args()
    if args.data_only and args.reboot:
        raise ValueError('--data-only must not reboot into the unchanged Android BOOT')
    if args.execute:
        if not args.device or not re.fullmatch(r'/dev/bus/usb/[0-9]{3}/[0-9]{3}', args.device):
            raise ValueError('Execution needs an explicit Odin-listed --device path')
        if not args.boot_only and not args.discard_existing_data:
            raise ValueError('Writing DATA needs --discard-existing-data. This replaces Android data and internal-storage files.')
    elif args.device and not re.fullmatch(r'/dev/bus/usb/[0-9]{3}/[0-9]{3}', args.device):
        raise ValueError('Invalid device path')
    verify()
    device = args.device or '/dev/bus/usb/BBB/DDD'
    steps = commands(device, args.boot_only, args.reboot, args.data_only)
    print('Target handset: SM-J701F / j7velte. Confirm this on the physical phone before execution.', flush=True)
    print('Targets: ' + ('BOOT only (resume)' if args.boot_only else 'USERDATA only (staged trial)' if args.data_only else 'USERDATA first, then BOOT'), flush=True)
    print('RECOVERY, SYSTEM, PIT, Samsung early bootloader, EFS and modem are not included.', flush=True)
    print('Experimental BOOT/DATA system. Hardware results are recorded in docs/hardware-status.md.', flush=True)
    if not args.boot_only:
        print('DATA contents, including Android internal-storage files, will be replaced. This project has a verified BOOT backup, not a DATA backup.', flush=True)
    for command in steps: print(shlex.join(command), flush=True)
    if not args.execute:
        print('PLAN ONLY. No USB tool was invoked and no partition was written.', flush=True)
        return
    for index, command in enumerate(steps):
        verify()
        if args.device not in listed_devices():
            raise ValueError('Selected Download Mode device is no longer listed. No further writes were attempted; if DATA succeeded, resume with --boot-only after reconnecting.')
        print(f'Flashing step {index + 1}/{len(steps)}: {Path(command[2]).name}', flush=True)
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError:
            print('STOPPED: this partition may be partially written. Do not treat upload or close errors as success.', flush=True)
            if Path(command[2]).name == 'userdata.tar':
                print('BOOT was not attempted. Do not resume with --boot-only until DATA has succeeded and been verified.', flush=True)
            raise
    print('Flash tools returned success. This is not a boot or partition read-back verification.', flush=True)
    if not args.reboot:
        print('No automatic reboot requested. Leave Download Mode manually when ready.', flush=True)


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        raise SystemExit(f'System flash: {error}')
