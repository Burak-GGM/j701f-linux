import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import recovery
spec = importlib.util.spec_from_file_location('cpu_trial', ROOT / 'tools/boot-cpu-trial.py')
trial = importlib.util.module_from_spec(spec); spec.loader.exec_module(trial)


class BootTrialTests(unittest.TestCase):
    def fixture(self):
        parts = dict(kernel=bytes(56) + b'ARM\x64' + bytes(4), ramdisk=b'ramdisk', second=b'', dt=b'DTBHtest')
        header = bytearray(2048); header[:8] = b'ANDROID!'
        struct.pack_into('<10I', header, 8, len(parts['kernel']), 0x10008000,
                         len(parts['ramdisk']), 0x11000000, 0, 0x10f00000,
                         0x10000100, 2048, len(parts['dt']), 0)
        header[576:596] = recovery.Image.digest(parts)
        image = bytes(header)
        for part in parts.values():
            image += part + bytes(recovery.align(len(part), 2048) - len(part))
        image += b'SEANDROIDENFORCE'
        backup = image + b'preserved partition tail' + bytes(100)
        return image, backup

    def test_preserves_payload_and_partition_tail_exactly(self):
        image, backup = self.fixture()
        patched = trial.patch_boot(backup, image, len(backup))
        self.assertEqual(patched[:64], backup[:64])
        self.assertEqual(patched[576:], backup[576:])
        self.assertEqual(recovery.Image(patched[:len(image)]).metadata()['cmdline'], 'zswap.enabled=0')

    def test_wrong_live_image_or_capacity_refused(self):
        image, backup = self.fixture()
        with self.assertRaisesRegex(ValueError, 'capacity'):
            trial.patch_boot(backup, image, len(backup) + 1)
        damaged = bytearray(backup); damaged[2050] ^= 1
        with self.assertRaisesRegex(ValueError, 'differs'):
            trial.patch_boot(bytes(damaged), image, len(backup))

    def test_existing_primary_or_extra_cmdline_refused(self):
        image, backup = self.fixture()
        for offset in (64, 608):
            changed = bytearray(image); changed[offset:offset+2] = b'x\0'
            with self.assertRaisesRegex(ValueError, 'command line'):
                trial.patch_boot(bytes(changed) + backup[len(image):], bytes(changed), len(backup))


if __name__ == '__main__':
    unittest.main()
