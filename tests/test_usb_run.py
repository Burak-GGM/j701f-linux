"""tools/usb-run.py: the command it sends and how it reads the answer (host only).

Written by Claude 2026-10-27. The round trip is checked by running the generated
command in a local shell, as the phone's serial shell would.
"""
import base64
import importlib.util
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('usb_run', ROOT / 'tools/usb-run.py')
usb_run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usb_run)


class UsbRunTests(unittest.TestCase):
    def test_long_script_is_sent_in_short_lines(self):
        script = ('echo ' + 'x' * 5000 + '\n').encode()
        command = usb_run.remote_command(script, [], 'abc123')
        self.assertTrue(all(len(line) < 800 for line in command.splitlines()))

    @unittest.skipUnless(shutil.which('busybox') or shutil.which('base64'), 'base64 needed')
    def test_round_trip_in_a_local_shell(self):
        script = b'echo "hi $WHO"\nprintf "a\\nb\\n"\nexit 3\n'
        command = usb_run.remote_command(script, [('WHO', 'phone')], 'tok1')
        # The phone has "busybox base64"; locally use the coreutils one.
        command = command.replace('busybox base64', 'base64')
        out = subprocess.run(['sh', '-c', command], capture_output=True, text=True).stdout
        text, status = usb_run.parse('\n' + out, 'tok1')
        self.assertEqual(text, 'hi phone\na\nb')
        self.assertEqual(status, 3)

    def test_unframed_output_is_an_error(self):
        with self.assertRaises(ValueError):
            usb_run.parse('j701f-mainline # nothing here', 'tok2')


if __name__ == '__main__':
    unittest.main()
