import importlib.util
import os
from pathlib import Path
import pty
import re
import select
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('usb_console', ROOT / 'tools/usb-console.py')
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)


class DiagnosticsTests(unittest.TestCase):
    def test_disconnect_keeps_partial_serial_output(self):
        with mock.patch.object(console.select, 'select', return_value=([17], [], [])), \
             mock.patch.object(console.os, 'read', side_effect=[b'last driver message\n', b'']):
            with self.assertRaises(OSError) as raised:
                console.read_marker(17, b'NEVER')
        self.assertEqual(raised.exception.partial_output, b'last driver message\n')

    def test_diagnostic_script_runs_over_real_pty(self):
        master, slave = pty.openpty()
        console.serial_settings(master)
        shell = subprocess.Popen(['/bin/sh','-i'], stdin=slave, stdout=slave, stderr=slave,
                                 start_new_session=True)
        try:
            output = console.command_session(master, 'printf "REPORT COMPLETE\\n"\n', 'REPORT COMPLETE')
            self.assertIn('REPORT COMPLETE', output)
        finally:
            shell.kill(); shell.wait(timeout=3)
            os.close(master); os.close(slave)

    def test_ram_probe_transfer_and_cleanup_over_real_pty(self):
        with tempfile.TemporaryDirectory() as directory:
            wrapper = Path(directory)/'busybox-fixture'
            wrapper.write_text('#!/bin/sh\nexec "$@"\n')
            wrapper.chmod(0o755)
            master, slave = pty.openpty()
            console.serial_settings(master)
            shell = subprocess.Popen(['/bin/sh','-i'], stdin=slave, stdout=slave, stderr=slave,
                                     start_new_session=True)
            payload = b'#!/bin/sh\nprintf "Layout validation: simulated probe success\\n"\n'
            token = 'TEST_PROBE_TRANSFER'
            try:
                with mock.patch.object(console,'REMOTE_BUSYBOX',str(wrapper)), \
                     mock.patch.object(console.secrets,'token_hex',return_value=token):
                    output = console.probe_session(master,payload)
                self.assertIn('Layout validation: simulated probe success', output)
                self.assertFalse(Path('/tmp/j701f-fb-probe-'+token).exists())
            finally:
                shell.kill()
                shell.wait(timeout=3)
                os.close(master); os.close(slave)

    def test_port_detection_uses_usb_serial_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for n, serial in ((0, console.SERIAL), (1, 'unrelated-device')):
                device = root / 'usb' / str(n)
                (device / 'interface').mkdir(parents=True)
                (device / 'serial').write_text(serial)
                tty = root / 'tty' / f'ttyACM{n}'
                tty.mkdir(parents=True)
                (tty / 'device').symlink_to(device / 'interface')
            self.assertEqual(console.find_ports(root / 'tty'), ['/dev/ttyACM0'])

    def run_setup(self, function='acm', include_instances=True, reject_function=False):
        """All sysfs/device paths redirected to a disposable fixture, no phone I/O."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            gadget = root / 'sys/class/android_usb/android0'
            (gadget / f'f_{function}').mkdir(parents=True)
            for name in ('enable','idVendor','idProduct','bDeviceClass','bDeviceSubClass',
                         'bDeviceProtocol','iSerial','functions'):
                (gadget / name).write_text('INITIAL')
            if include_instances:
                (gadget / f'f_{function}/instances').write_text('0')
            tty = root / 'sys/class/tty/ttyGS0'
            tty.mkdir(parents=True)
            (tty / 'dev').write_text('1:3')
            (root / 'dev').mkdir()
            (root / 'dev/ttyGS0').symlink_to('/dev/null')
            (root / 'tmp').mkdir()
            (root / 'etc').mkdir()
            if not (ROOT / 'ramdisk/etc/usb-baseline.conf').is_file():
                self.skipTest('USB baseline extracted by make unpack is required')
            shutil.copyfile(ROOT / 'ramdisk/etc/usb-baseline.conf', root / 'etc/usb-baseline.conf')
            script = (ROOT / 'ramdisk/bin/usb-debug').read_text()
            script = re.sub(r'/(?:sys|etc|dev|tmp)/', lambda match: str(root)+match.group(0), script)
            if reject_function:
                script = script.replace('printf \'%s\\n\' "$2" > "$1"',
                                        'if [ "${1##*/}" = functions ]; then : > "$1"; '
                                        'else printf \'%s\\n\' "$2" > "$1"; fi')
            # Replace the serial session with an argument recorder; stop at respawn delay.
            script = script.replace('setsid getty ', 'printf "%s\\n" ')
            script = script.replace('sleep 1', 'exit 0')
            result = subprocess.run(['/bin/sh','-c',script], capture_output=True,text=True,timeout=5)
            attributes = {p.name:p.read_text().strip() for p in gadget.iterdir() if p.is_file()}
            return result, attributes

    def test_acm_setup_and_session_arguments(self):
        result, attrs = self.run_setup()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(attrs['functions'],'acm')
        self.assertEqual(attrs['enable'],'1')
        self.assertEqual(attrs['idVendor'],'04e8')
        self.assertEqual(attrs['idProduct'],'6860')
        self.assertIn('/bin/usb-shell',result.stdout)
        self.assertIn('ttyGS0',result.stdout)

    def test_acm0_variant_discovered(self):
        result, attrs = self.run_setup('acm0')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(attrs['functions'],'acm0')

    def test_missing_acm_does_not_enable_gadget(self):
        result, attrs = self.run_setup(include_instances=False)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(attrs['enable'],'INITIAL')
        self.assertIn('No ACM function', result.stdout)

    def test_silently_rejected_function_stays_disabled(self):
        result, attrs = self.run_setup(reject_function=True)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(attrs['enable'],'0')
        self.assertIn('Function rejected', result.stdout)

    def test_real_aarch64_getty_starts_login_after_enter(self):
        qemu = shutil.which('qemu-aarch64') or shutil.which('qemu-aarch64-static')
        if not qemu:
            self.skipTest('QEMU user emulator absent')
        if not (ROOT / 'ramdisk/bin/busybox').is_file():
            self.skipTest('static BusyBox prepared by make busybox is required')
        with tempfile.TemporaryDirectory() as directory:
            login = Path(directory) / 'test-login'
            login.write_text('#!/bin/sh\nprintf "J701F-GETTY-TEST-OK\\n"\n')
            login.chmod(0o755)
            master, slave = pty.openpty()
            proc = subprocess.Popen([qemu, str(ROOT/'ramdisk/bin/busybox'), 'getty',
                                     '-L','-n','-w','-l',str(login),'0',os.ttyname(slave),'vt100'],
                                    start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            output = b''
            try:
                deadline = time.monotonic()+5
                send_at = time.monotonic()+0.15
                while time.monotonic()<deadline and b'J701F-GETTY-TEST-OK' not in output:
                    if time.monotonic()>=send_at:
                        os.write(master,b'\r')
                        send_at = time.monotonic()+0.3
                    ready,_,_ = select.select([master],[],[],0.05)
                    if ready:
                        output += os.read(master,4096)
                self.assertIn(b'J701F-GETTY-TEST-OK',output)
            finally:
                if proc.poll() is None: proc.terminate()
                proc.communicate(timeout=3)
                os.close(master); os.close(slave)


if __name__ == '__main__':
    unittest.main()
