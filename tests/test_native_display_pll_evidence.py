"""First-PLL evidence must not turn a successful retry into a clean start."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('pll_trial', ROOT / 'tools/run-native-display-trial.py')
TRIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRIAL)
FRESH = ('exynos-dsi 14800000.dsi: J701F PLL completion=1 mask_before=0xb77fffff '
         'mask_now=0x077b7fff link_before=0x00100001 link_now=0x01100001 '
         'pll_before=0x00006371 reset_done=1\n')


class PllEvidenceTests(unittest.TestCase):
    def test_actual_diagnostic_baseline_rejects_first_init_despite_successful_retry(self):
        path = ROOT / 'build/kernel/display-runtime/runs/native-dsimdiag2-01/dmesg.txt'
        if not path.exists():
            self.skipTest('archived phone diagnostic log absent')
        result = TRIAL.analyse_pll(path.read_text())
        self.assertEqual(len(result['attempts']), 2)
        self.assertFalse(result['first_init_verified'])
        self.assertFalse(result['attempts'][0]['completion'])
        self.assertTrue(result['attempts'][1]['completion'])

    def test_synthetic_fresh_completion_with_locked_link_is_separate_pass(self):
        result = TRIAL.analyse_pll(FRESH)
        self.assertTrue(result['first_init_verified'])
        self.assertEqual(result['status'], 'first-init-verified')

    def test_inherited_pll_missing_reset_unlocked_link_and_later_errors_rejected(self):
        for log in (FRESH.replace('pll_before=0x00006371', 'pll_before=0x00806371'),
                    FRESH.replace('reset_done=1', 'reset_done=0'),
                    FRESH.replace('link_now=0x01100001', 'link_now=0x00100001'),
                    FRESH+'exynos-dsi 14800000.dsi: PLL failed to stabilize\n'):
            with self.subTest(log=log):
                self.assertFalse(TRIAL.analyse_pll(log)['first_init_verified'])

    def test_missing_observations_are_not_hardware_success(self):
        self.assertEqual(TRIAL.analyse_pll('clock aud_pll: 98304019 Hz')['status'], 'not-observed')
        self.assertFalse(TRIAL.analyse_pll('J701F PLL completion=1')['first_init_verified'])


if __name__ == '__main__':
    unittest.main()
