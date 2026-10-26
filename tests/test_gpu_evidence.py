"""Do not turn inconsistent or malformed vendor readings into GPU port data."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gpu_evidence', ROOT / 'tools/j701f-gpu-evidence.py')
gpu = importlib.util.module_from_spec(spec); spec.loader.exec_module(gpu)

READING = '''GPU_PATH=/sys/devices/11400000.mali
ATTRIBUTE=clock
0
ATTRIBUTE=vol
662500
ATTRIBUTE=power_state
0
ATTRIBUTE=asv_table
GPU, vol, min, max, down_stay, mif, int, cpu
450, 637500, 78, 85, 1, 451000, 200000, 0
343, 600000, 78, 85, 1, 275000, 134000, 0
ATTRIBUTE=dvfs_table
450 343
'''


class ObservationChecks(unittest.TestCase):
    def test_units_and_off_state_preserved(self):
        result = gpu.observations(READING)
        self.assertFalse(result['power_on'])
        self.assertEqual(result['current_microvolt'], 662500)
        self.assertEqual(result['vendor_asv_rows'][1]['frequency_hz'], 343000000)

    def test_conflicting_tables_rejected(self):
        with self.assertRaisesRegex(ValueError, 'tables disagree'):
            gpu.observations(READING.replace('450 343\n', '450 400\n'))

    def test_malformed_asv_row_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Malformed ASV'):
            gpu.observations(READING.replace('343, 600000,', '343, unknown,'))

    def test_missing_supply_reading_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing GPU observation: vol'):
            gpu.observations(READING.replace('ATTRIBUTE=vol\n662500\n', ''))


if __name__ == '__main__':
    unittest.main()
