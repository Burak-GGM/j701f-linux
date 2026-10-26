"""Avoid counting firmware scanout or incomplete logs as native-display proof."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('trial_evidence', ROOT/'tools/run-native-display-trial.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

KMS = 'NATIVE_MODESET_OK\nNATIVE_FLIPS_OK count=120 elapsed=1.99 event_rate=59.8\n'
# Deliberately synthetic parser data, never a phone performance result.
NATIVE = '''J701F_PANEL_DCS_POWER_MODE result=0 value=0x9c
j701f-display-info: DECON VIDW_ADD0 offset=0x880 value=0xb2000000
j701f-display-info: DSIM RESOL offset=0x20 value=0x050002d0
j701f-display-info: DSIM HPORCH offset=0x28 value=0x00380030
j701f-display-info: SYSMMU CTRL offset=0x0 value=0x00000000
'''


class EvidenceTests(unittest.TestCase):
    def test_startup_wait_does_not_mistake_early_empty_stamps_for_safe_reset(self):
        states = [{'uptime': '50', 'pending': ['j701f-gpufreq.pending']},
                  {'uptime': '225', 'pending': []}, {'uptime': '245', 'pending': []}]
        with patch.object(tool, 'identity', side_effect=states) as read, \
             patch.object(tool.time, 'sleep') as sleep, patch('builtins.print'):
            final = tool.wait_startup_guards({'uptime': '30', 'pending': []})
        self.assertEqual(final['uptime'], '245')
        self.assertEqual(read.call_count, 3)
        self.assertEqual(sleep.call_count, 3)

    def test_persistent_startup_stamp_refuses_trial_even_after_minimum_uptime(self):
        pending = {'uptime': '1000', 'pending': ['j701f-gpufreq.pending']}
        with patch.object(tool, 'identity', return_value=pending), \
             patch.object(tool.time, 'sleep'), patch('builtins.print'):
            with self.assertRaisesRegex(RuntimeError, 'no trial armed'):
                tool.wait_startup_guards(pending)

    def test_complete_synthetic_native_signature(self):
        checks, address = tool.analyse_native(KMS, NATIVE)
        self.assertTrue(all(checks.values()))
        self.assertEqual(address, '0xb2000000')

    def test_firmware_framebuffer_is_not_native_even_with_good_link_values(self):
        checks, _ = tool.analyse_native(KMS, NATIVE.replace('0xb2000000', '0x67000000'))
        self.assertFalse(checks['native_framebuffer_address'])

    def test_observed_panel_replies_share_core_state_without_guessing_bit7(self):
        for value in ('0x9c', '0x1c'):
            checks, _ = tool.analyse_native(KMS, NATIVE.replace('0x9c', value))
            self.assertTrue(checks['panel_dcs_answer'])

    def test_transport_success_without_requested_panel_state_is_rejected(self):
        for value in ('0x00', '0xff', '0x18', '0x14', '0x0c', '0x3c', '0x5c', '0x19c'):
            with self.subTest(value=value):
                checks, _ = tool.analyse_native(KMS, NATIVE.replace('0x9c', value))
                self.assertFalse(checks['panel_dcs_answer'])

    def test_failed_read_or_missing_flips_or_wrong_timing_invalidates(self):
        cases = [(KMS, NATIVE.replace('result=0', 'result=-110')),
                 (KMS.replace('count=120', 'count=12'), NATIVE),
                 (KMS, NATIVE.replace('0x00380030', '0x002e0027')),
                 (KMS, NATIVE.replace('value=0x00000000', 'value=0x00000001')),
                 ('', ''), (KMS, NATIVE[:100])]
        for kms, log in cases:
            with self.subTest(log=log):
                checks, _ = tool.analyse_native(kms, log)
                self.assertFalse(all(checks.values()))

    @unittest.skipUnless((ROOT/'build/kernel/ea8061s-prototype/phone-display-state.txt').exists(),
                         'Read-only firmware capture unavailable')
    def test_real_old_firmware_capture_is_rejected(self):
        actual = (ROOT/'build/kernel/ea8061s-prototype/phone-display-state.txt').read_text()
        checks, _ = tool.analyse_native(KMS, actual)
        self.assertFalse(checks['native_framebuffer_address'])
        self.assertFalse(checks['panel_dcs_answer'])


if __name__ == '__main__':
    unittest.main()
