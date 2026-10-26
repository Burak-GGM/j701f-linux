"""Synthetic evidence-parser cases; never presented as GPU hardware results."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('native_prime_trial', ROOT / 'tools/run-native-display-trial.py')
TRIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRIAL)
BUFFER = ('NATIVE_PRIME_ALLOCATOR render\n'
          'NATIVE_PRIME_BUFFER width=720 height=1280 format=XRGB8888 stride=2880 modifier=0\n')
SUCCESS = BUFFER + 'NATIVE_PRIME_IMPORT_OK\nNATIVE_PRIME_SCANOUT_OBJECT_OK\n'


class PrimeEvidenceTests(unittest.TestCase):
    def test_object_creation_does_not_claim_scanout_or_desktop_performance(self):
        for allocator in ('render', 'display'):
            with self.subTest(allocator=allocator):
                result = TRIAL.analyse_prime(SUCCESS.replace('ALLOCATOR render', 'ALLOCATOR '+allocator))
                self.assertEqual(result['status'], 'framebuffer-object-ready')
                self.assertEqual(result['allocator'], allocator)
                self.assertTrue(result['import_verified'])
                self.assertTrue(result['framebuffer_object_verified'])
                self.assertFalse(result['scanout_performed'])

    def test_contiguous_import_rejection_is_separate_from_native_modeset(self):
        result = TRIAL.analyse_prime(BUFFER + 'NATIVE_PRIME_IMPORT_REJECTED errno=22\n')
        self.assertEqual((result['status'], result['rejected_stage'], result['errno']),
                         ('rejected', 'IMPORT', 22))
        self.assertFalse(result['import_verified'])
        self.assertFalse(result['framebuffer_object_verified'])

    def test_framebuffer_rejection_retains_successful_import(self):
        result = TRIAL.analyse_prime(BUFFER + 'NATIVE_PRIME_IMPORT_OK\n'
                                    'NATIVE_PRIME_FB_REJECTED errno=22\n')
        self.assertTrue(result['import_verified'])
        self.assertFalse(result['framebuffer_object_verified'])
        self.assertEqual(result['rejected_stage'], 'FB')

    def test_missing_geometry_bad_stride_and_tiled_modifier_are_inconclusive(self):
        for log in ('', 'NATIVE_PRIME_SCANOUT_OBJECT_OK\n',
                    SUCCESS.replace('stride=2880', 'stride=100'),
                    SUCCESS.replace('modifier=0', 'modifier=123')):
            with self.subTest(log=log):
                result = TRIAL.analyse_prime(log)
                self.assertFalse(result['import_verified'])
                self.assertFalse(result['framebuffer_object_verified'])
                self.assertFalse(result['scanout_performed'])


if __name__ == '__main__':
    unittest.main()
