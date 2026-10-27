#!/usr/bin/env python3
"""Run a local shell script on the phone over the USB serial shell.

Written by Claude 2026-10-27, for when the phone has no network or SSH (a fresh
release, a recovery with Wi-Fi off). The script is sent base64-encoded in short
lines, so terminal line limits and shell continuation prompts do not matter,
runs as the serial shell's user (root), and its output and exit status are
returned. Works with the installed system and with the project's RAM recovery.

  tools/usb-run.py SCRIPT [NAME=VALUE ...] [--timeout SECONDS]
"""
import argparse
import base64
import importlib.util
import os
from pathlib import Path
import re
import secrets
import sys
import termios

ROOT = Path(__file__).resolve().parents[1]
CHUNK = 700


def console():
    spec = importlib.util.spec_from_file_location('j701f_usb_console', ROOT / 'tools/usb-console.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def remote_command(script, env, token):
    """The shell text that rebuilds the script on the phone, runs it and frames the result."""
    data = base64.b64encode(script).decode()
    tmp = f'/tmp/usb-run-{token}'
    lines = [f': > {tmp}.b64']
    lines += [f"printf %s '{data[i:i + CHUNK]}' >> {tmp}.b64" for i in range(0, len(data), CHUNK)]
    assigns = ' '.join(f"{name}='{value}'" for name, value in env)
    lines += [
        f'busybox base64 -d {tmp}.b64 > {tmp}.sh',
        f"printf '\\n%s\\n' 'USB_RUN_BEGIN_{token}'",
        f'{assigns} sh {tmp}.sh; rc=$?'.strip(),
        f"printf '\\n%s=%s\\n' 'USB_RUN_EXIT_{token}' \"$rc\"",
        f'rm -f {tmp}.b64 {tmp}.sh',
    ]
    return '\n'.join(lines) + '\n'


def parse(output, token):
    """(script output, exit status) from the framed session output."""
    match = re.search(rf'\nUSB_RUN_BEGIN_{token}\r?\n(.*)\r?\nUSB_RUN_EXIT_{token}=(\d+)', output, re.S)
    if not match:
        raise ValueError('no framed result from the phone')
    # The exit marker is printed after a newline of its own: drop that one.
    return match.group(1).rstrip('\r\n'), int(match.group(2))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('script', type=Path)
    parser.add_argument('env', nargs='*', help='NAME=VALUE pairs set for the script')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    env = []
    for item in args.env:
        name, sep, value = item.partition('=')
        if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) or "'" in value:
            parser.error(f'bad NAME=VALUE: {item!r}')
        env.append((name, value))
    usb = console()
    ports = usb.find_ports(serials=(usb.SERIAL, usb.MAINLINE_SERIAL))
    if len(ports) != 1:
        raise SystemExit(f'expected one J701F serial port, found {ports}')
    token = secrets.token_hex(6)
    command = remote_command(args.script.read_bytes(), env, token)
    fd = os.open(ports[0], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    saved = termios.tcgetattr(fd)
    try:
        usb.serial_settings(fd)
        output = usb.command_session(fd, command, f'USB_RUN_EXIT_{token}=', args.timeout)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, saved)
        os.close(fd)
    text, status = parse(output, token)
    sys.stdout.write(text.replace('\r\n', '\n') + '\n')
    return status


if __name__ == '__main__':
    sys.exit(main())
