"""Reject S-BOOT table changes that could select a wrong hardware revision."""
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sboot_stub', ROOT / 'tools/prepare-sboot-stub.py')
stub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stub)


@unittest.skipUnless((ROOT / 'extracted/dtb').is_file(),
                     'extracted vendor DTBH table (make unpack, needs the user-supplied image) is required')
class StubTableChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = (ROOT / 'extracted/dtb').read_bytes()

    def test_original_selection_and_payloads_round_trip(self):
        entries = stub.parse_table(self.baseline)
        packed = stub.pack_table([blob for _, blob in entries])
        self.assertEqual(packed, self.baseline)

    def test_other_hardware_revision_rejected(self):
        data = bytearray(self.baseline)
        struct.pack_into('<I', data, 12 + 2 * 32 + 3 * 4, 4)
        with self.assertRaisesRegex(ValueError, 'selection keys'):
            stub.parse_table(data)

    def test_wrong_platform_rejected(self):
        data = bytearray(self.baseline); data[16] ^= 1
        with self.assertRaisesRegex(ValueError, 'selection keys'):
            stub.parse_table(data)

    def test_overlapping_payloads_rejected(self):
        data = bytearray(self.baseline)
        struct.pack_into('<I', data, 12 + 32 + 5 * 4, stub.PAGE)
        with self.assertRaisesRegex(ValueError, 'bounds/order'):
            stub.parse_table(data)

    def test_truncated_table_rejected(self):
        with self.assertRaisesRegex(ValueError, 'bounds/order'):
            stub.parse_table(self.baseline[:-stub.PAGE])

    def test_dtb_length_cannot_read_next_entry(self):
        data = bytearray(self.baseline)
        struct.pack_into('>I', data, stub.PAGE + 4, len(data))
        with self.assertRaisesRegex(ValueError, 'header/length'):
            stub.parse_table(data)

    def test_nonzero_tail_rejected(self):
        data = bytearray(self.baseline); data[-1] = 1
        with self.assertRaisesRegex(ValueError, 'tail padding'):
            stub.parse_table(data)


if __name__ == '__main__':
    unittest.main()
