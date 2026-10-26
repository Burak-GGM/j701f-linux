#!/usr/bin/env python3
"""Open the J701F USB serial shell using Python's standard library. Ctrl+] exits."""
import argparse
import base64
import hashlib
import os
from pathlib import Path
import select
import secrets
import shlex
import sys
import termios
import time
import tty

SERIAL = 'J701F-LINUX-CONSOLE'
REMOTE_BUSYBOX = '/bin/busybox'


def serial_settings(fd):
    settings = termios.tcgetattr(fd)
    settings[0] = 0
    settings[1] = 0
    settings[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    settings[3] = 0
    settings[4] = settings[5] = termios.B115200
    settings[6][termios.VMIN] = 1
    settings[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, settings)


def send_bytes(fd, data, timeout=10):
    end = time.monotonic()+timeout
    while data:
        if time.monotonic() >= end:
            raise TimeoutError('Timed out writing the USB serial port')
        _, ready, _ = select.select([], [fd], [], 0.2)
        if ready:
            try:
                data = data[os.write(fd, data):]
            except BlockingIOError:
                pass


def read_marker(fd, marker, timeout=15):
    end = time.monotonic()+timeout
    data = bytearray()
    while time.monotonic() < end:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if ready:
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                continue
            if not chunk:
                error = OSError('USB serial port disconnected')
                error.partial_output = bytes(data)
                raise error
            data.extend(chunk)
            if marker in data:
                return bytes(data)
            if len(data) > 256*1024:
                raise ValueError('Unexpectedly large serial response')
    error = TimeoutError('No response from the phone shell. Close other serial terminals and reconnect.')
    error.partial_output = bytes(data)
    raise error


def marker_command(marker):
    # Split the token so the echoed command cannot impersonate its output.
    half = len(marker)//2
    return f"printf '\\n%s%s\\n' '{marker[:half]}' '{marker[half:]}'\n"


def command_session(fd, script, required_text, timeout=20):
    """Run a locally supplied diagnostic script with framed output and echo recovery."""
    token = secrets.token_hex(10)
    ready = 'J701F_READY_' + token
    begin = 'J701F_BEGIN_' + token
    end = 'J701F_END_' + token
    # Wake getty; then wait for the shell to acknowledge a split marker.
    for attempt in range(4):
        send_bytes(fd, b'\r' + marker_command(ready).encode())
        try:
            read_marker(fd, ready.encode(), 3)
            break
        except TimeoutError:
            if attempt == 3:
                raise
    send_bytes(fd, b'stty -echo\n' + marker_command(ready + '_QUIET').encode())
    read_marker(fd, (ready + '_QUIET').encode())
    # A heredoc keeps multi-line shell control flow out of the interactive parser.
    script = marker_command(begin) + "/bin/sh <<'J701F_SCRIPT_" + token + "'\n" + script
    script += '\nJ701F_SCRIPT_' + token + '\nstty echo\n' + marker_command(end)
    try:
        send_bytes(fd, script.encode())
        response = read_marker(fd, end.encode(), timeout)
        if begin.encode() not in response:
            raise ValueError('Probe output framing is incomplete')
        output = response.split(begin.encode(),1)[1].split(end.encode(),1)[0]
        text = output.decode(errors='replace').replace('\r','').strip()
        if required_text not in text:
            raise ValueError('Diagnostic output is incomplete:\n' + text)
        return text
    except OSError as exc:
        partial = getattr(exc, 'partial_output', b'')
        if begin.encode() in partial:
            partial = partial.split(begin.encode(), 1)[1]
        report = Path(__file__).resolve().parents[1] / 'build/phone-display-interrupted.txt'
        report.parent.mkdir(exist_ok=True)
        report.write_text(str(exc) + '\n' + partial.decode(errors='replace').replace('\r',''))
        raise OSError(f'{exc}. Partial output saved in {report}') from None
    finally:
        # Cancel an incomplete heredoc and restore echo if the transfer timed out.
        try:
            send_bytes(fd, b'\x03stty echo\n', 1)
        except (OSError, termios.error):
            pass


def probe_session(fd, payload, display_test=False, activate_test=False, swap_rb=False, terminal_test=False):
    if len(payload) > 64*1024:
        raise ValueError('Probe exceeds 64 KiB limit')
    token = secrets.token_hex(10)
    remote = '/tmp/j701f-fb-probe-' + token
    encoded = base64.encodebytes(payload).decode()
    digest = hashlib.sha256(payload).hexdigest()
    busybox = shlex.quote(REMOTE_BUSYBOX)
    script = f"{busybox} base64 -d > {shlex.quote(remote)} <<'J701F_PAYLOAD_{token}'\n"
    script += encoded + f'J701F_PAYLOAD_{token}\n'
    script += f'probe_sum=$({busybox} sha256sum {remote})\n'
    script += f'if [ "${{probe_sum%% *}}" = {digest} ]; then\n'
    mode = '--test' if terminal_test else '--test-swap-rb' if swap_rb else '--test-activate' if activate_test else '--test' if display_test else '--info'
    if display_test:
        # The flashed image now draws continuously. Pause only its known helper
        # so it cannot overwrite this test, and resume it when the script exits.
        script += '''  paused_pids=''
  resume_heartbeat() { for paused_pid in $paused_pids; do kill -CONT "$paused_pid" 2>/dev/null; done; }
  trap resume_heartbeat EXIT INT TERM
  for proc_exe in /proc/[0-9]*/exe; do
    target=$(/bin/busybox readlink "$proc_exe") || continue
    case "$target" in /bin/fb-heartbeat|/bin/ondevice-terminal) ;; *) continue ;; esac
    proc_dir=${proc_exe%/exe}; heartbeat_pid=${proc_dir##*/}
    if kill -STOP "$heartbeat_pid"; then
      paused_pids="$paused_pids $heartbeat_pid"
      printf 'Temporarily paused boot heartbeat PID %s\\n' "$heartbeat_pid"
    fi
  done
'''
    if terminal_test:
        script += '''  mkdir -p /dev/input
  for event_node in /sys/class/input/event*; do
    [ -r "$event_node/dev" ] || continue
    event_name=${event_node##*/}
    [ ! -c "/dev/input/$event_name" ] || continue
    event_dev=$(cat "$event_node/dev")
    event_major=${event_dev%:*}; event_minor=${event_dev#*:}
    case "$event_major:$event_minor" in *[!0-9:]*|:*) continue ;; esac
    mknod -m 600 "/dev/input/$event_name" c "$event_major" "$event_minor"
  done
'''
    script += f'  chmod 700 {remote}\n  {remote} {mode} /dev/fb0\n'
    script += '  helper_status=$?\n  printf "Helper exit status: %s\\n" "$helper_status"\n'
    script += 'else\n  printf "ERROR: probe transfer checksum mismatch\\n"\nfi\n'
    script += f'{busybox} rm -f {remote}\n'
    return command_session(fd, script, 'ONDEVICE TERMINAL TEST COMPLETE' if terminal_test else 'Layout validation:', 200 if terminal_test else 20)


def diagnostics(port):
    root = Path(__file__).resolve().parents[1]
    script = (root / 'tools/display-diagnostics.sh').read_text()
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    saved = termios.tcgetattr(fd)
    try:
        serial_settings(fd)
        output = command_session(fd, script, 'DISPLAY DIAGNOSTICS COMPLETE')
        report = root / 'build/phone-display-diagnostics.txt'
        report.write_text(output + '\n')
        print(output)
        print(f'\nSaved {report}. Display diagnostics only read device information.')
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSANOW, saved)
        except (OSError, termios.error):
            pass
        os.close(fd)


def probe(port, display_test=False, activate_test=False, swap_rb=False, terminal_test=False):
    path = Path(__file__).resolve().parents[1] / ('build/ondevice-terminal-probe' if terminal_test else 'build/fb-heartbeat-probe')
    payload = path.read_bytes()
    # This entry point only transfers our statically built AArch64 probe to RAM.
    from recovery import elf_static
    elf_static(payload)
    action = 'three-minute touchscreen terminal test' if terminal_test else 'six-second display test' if display_test else 'framebuffer probe'
    print(f'Close other serial terminals first. Uploading a temporary RAM-only {action}.', flush=True)
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    saved = termios.tcgetattr(fd)
    try:
        serial_settings(fd)
        output = probe_session(fd, payload, display_test, activate_test, swap_rb, terminal_test)
        report = path.parent / ('phone-terminal-test.txt' if terminal_test else 'phone-display-swap-rb-test.txt' if swap_rb else 'phone-display-activation-test.txt' if activate_test else 'phone-display-test.txt' if display_test else 'phone-framebuffer.txt')
        report.write_text(output + '\n')
        print(output)
        if display_test:
            print(f'\nSaved {report}. Display updated temporarily; no phone partitions were changed.')
        else:
            print(f'\nSaved {report}. No display settings or phone partitions were changed.')
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSANOW, saved)
        except (OSError, termios.error):
            pass
        os.close(fd)


def find_ports(sys_tty=Path('/sys/class/tty')):
    ports = []
    for node in sorted(sys_tty.glob('ttyACM*')):
        device = (node / 'device').resolve()
        for parent in (device, *device.parents):
            serial = parent / 'serial'
            if serial.is_file():
                if serial.read_text().strip() == SERIAL:
                    ports.append('/dev/' + node.name)
                break
    return ports


def connect(port):
    if not sys.stdin.isatty():
        raise ValueError('Run this command in an interactive host terminal.')
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    host_settings = termios.tcgetattr(sys.stdin)
    device_settings = None
    try:
        device_settings = termios.tcgetattr(fd)
        serial_settings(fd)
        print(f'Opening {port}. Press Enter for the shell; Ctrl+] exits locally.', flush=True)
        tty.setraw(sys.stdin.fileno())
        pending = bytearray(b'\r')
        while True:
            readable, writable, _ = select.select([fd, sys.stdin], [fd] if pending else [], [])
            if fd in writable:
                try:
                    sent = os.write(fd, pending)
                    del pending[:sent]
                except BlockingIOError:
                    pass
            if fd in readable:
                try:
                    data = os.read(fd, 4096)
                except BlockingIOError:
                    continue
                if not data:
                    break
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            if sys.stdin in readable:
                data = os.read(sys.stdin.fileno(), 4096)
                if not data or b'\x1d' in data:
                    break
                pending.extend(data)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, host_settings)
        if device_settings is not None:
            try:
                termios.tcsetattr(fd, termios.TCSANOW, device_settings)
            except OSError:
                pass
        os.close(fd)
        print('\nUSB console closed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='List matching ports without opening them')
    parser.add_argument('--device', help='Explicit serial device, for example /dev/ttyACM0')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--probe-framebuffer', action='store_true', help='Upload a RAM-only read-only framebuffer probe and save its output')
    actions.add_argument('--test-display', action='store_true', help='Activate the current framebuffer mode, run six heartbeat frames from RAM and save the output')
    actions.add_argument('--test-display-activation', action='store_true', help='Alias for --test-display; current-mode activation is now included in both tests and normal boot')
    actions.add_argument('--test-display-swap-rb', action='store_true', help='Run a RAM-only six-frame test with red and blue rendering channels exchanged')
    actions.add_argument('--test-terminal', action='store_true', help='Run the RAM-only touchscreen terminal and real shell for three minutes')
    actions.add_argument('--display-diagnostics', action='store_true', help='Read panel, backlight, framebuffer and kernel display information')
    args = parser.parse_args()
    ports = find_ports()
    if args.list:
        print('\n'.join(ports) if ports else 'No J701F Linux USB serial port detected.')
        return
    port = args.device
    if not port:
        if len(ports) != 1:
            raise ValueError('Expected one J701F port. Boot the new recovery, reconnect USB, and run --list. '
                             'Use --device /dev/ttyACM<N> if automatic identification fails.')
        port = ports[0]
    if args.display_diagnostics:
        diagnostics(port)
    elif args.probe_framebuffer or args.test_display or args.test_display_activation or args.test_display_swap_rb or args.test_terminal:
        probe(port, args.test_display or args.test_display_activation or args.test_display_swap_rb or args.test_terminal, args.test_display_activation, args.test_display_swap_rb, args.test_terminal)
    else:
        connect(port)


if __name__ == '__main__':
    try:
        main()
    except (OSError, termios.error, ValueError, KeyboardInterrupt) as exc:
        raise SystemExit(f'USB console: {exc}')
