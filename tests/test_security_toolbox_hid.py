"""HID output must use explicit key press/release reports and bound input."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'system/security-toolbox/hid-send.py'
spec = importlib.util.spec_from_file_location('j701f_hid_send', SCRIPT)
hid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hid)


class HIDReports(unittest.TestCase):
    def test_press_release_and_final_release(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(hid.time, 'sleep'):
            path = str(Path(folder) / 'reports.bin')
            hid.send('aA!', path)
            data = Path(path).read_bytes()
        self.assertEqual(len(data), 3 * 16 + 8)
        self.assertEqual(data[:8], bytes((0, 0, 4, 0, 0, 0, 0, 0)))
        self.assertEqual(data[16:24], bytes((2, 0, 4, 0, 0, 0, 0, 0)))
        self.assertEqual(data[32:40], bytes((2, 0, 30, 0, 0, 0, 0, 0)))
        for start in (8, 24, 40, 48):
            self.assertEqual(data[start:start + 8], bytes(8))

    def test_invalid_or_long_input_never_opens_device(self):
        with patch('builtins.open', side_effect=AssertionError('device opened')):
            for value in ('', 'ö', '\x00', 'a' * 161):
                with self.assertRaises(ValueError):
                    hid.send(value)


if __name__ == '__main__':
    unittest.main()
