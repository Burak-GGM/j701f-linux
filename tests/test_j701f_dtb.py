"""Ensure the RAM diagnostic rejects unsafe memory/storage changes."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('board_dtb', ROOT / 'tools/build-j701f-dtb.py')
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)


@unittest.skipUnless(board.DTB.exists() and shutil.which('fdtput'), 'Build diagnostic DTB first')
class DiagnosticSafety(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='j701f-dtb-test-')
        self.addCleanup(self.temporary.cleanup)
        self.dtb = Path(self.temporary.name) / 'test.dtb'
        shutil.copyfile(board.DTB, self.dtb)

    def test_unprotected_modem_memory_rejected(self):
        subprocess.run(['fdtput', '-r', str(self.dtb), '/reserved-memory/modem-if@b0000000'], check=True)
        with self.assertRaisesRegex(ValueError, 'reservation is unprotected'):
            board.verify(self.dtb)

    def test_storage_accidentally_enabled_rejected(self):
        subprocess.run(['fdtput', '-t', 's', str(self.dtb), '/soc@0/mmc@13540000',
                        'status', 'okay'], check=True)
        with self.assertRaisesRegex(ValueError, 'disable storage'):
            board.verify(self.dtb)

    def test_wrong_memory_capacity_rejected(self):
        subprocess.run(['fdtput', '-t', 'x', str(self.dtb), '/memory@40000000', 'reg',
                        '0', '40000000', '3e400000', '0', '80000000', '80000000'], check=True)
        with self.assertRaisesRegex(ValueError, 'measured J701F banks'):
            board.verify(self.dtb)

    def test_wrong_normal_restart_reason_rejected(self):
        subprocess.run(['fdtput', '-t', 'x', str(self.dtb),
                        '/soc@0/system-controller@10480000/reboot-mode',
                        'mode-normal', '12345674'], check=True)
        with self.assertRaisesRegex(ValueError, 'Normal restart reason'):
            board.verify(self.dtb)

    def test_gpu_clock_provider_accidentally_enabled_rejected(self):
        subprocess.run(['fdtput', '-t', 's', str(self.dtb), '/soc@0/clock-controller@11460000',
                        'status', 'okay'], check=True)
        with self.assertRaisesRegex(ValueError, 'powered-domain clocks'):
            board.verify(self.dtb)

    def test_gpu_supply_cannot_be_replaced_with_an_unrelated_rail(self):
        buck1 = board.prop(self.dtb, '/soc@0/i2c@10510000/pmic@66/regulators/buck1', 'phandle')[0]
        subprocess.run(['fdtput', '-t', 'x', str(self.dtb), '/soc@0/gpu@11400000',
                        'mali-supply', hex(buck1)], check=True)
        with self.assertRaisesRegex(ValueError, 'BUCK2 mapping'):
            board.verify(self.dtb)


if __name__ == '__main__':
    unittest.main()
