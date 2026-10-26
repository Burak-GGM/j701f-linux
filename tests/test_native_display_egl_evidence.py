"""Synthetic renderer evidence never claims an actual GPU frame or scanout."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('native_egl_trial', ROOT / 'tools/run-native-display-trial.py')
TRIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRIAL)
PANFROST = '''NATIVE_EGL_PATH=render DRM_DRIVER=panfrost
NATIVE_EGL_RENDERER=Mali T830 (Panfrost)
NATIVE_EGL_PANFROST_T830=1
NATIVE_EGL_CONTEXT_READY; no draw or scanout performed
'''


class EglEvidenceTests(unittest.TestCase):
    def test_context_identity_never_claims_a_rendered_frame(self):
        result = TRIAL.analyse_egl(PANFROST)
        self.assertEqual(result['status'], 'context-ready')
        self.assertTrue(result['panfrost_t830_context'])
        self.assertFalse(result['draw_verified'])
        self.assertFalse(result['scanout_performed'])

    def test_software_context_is_distinct_from_panfrost_context(self):
        log = PANFROST.replace('PATH=render DRM_DRIVER=panfrost', 'PATH=display DRM_DRIVER=exynos')
        log = log.replace('Mali T830 (Panfrost)', 'llvmpipe (LLVM 22.1, 128 bits)').replace('T830=1', 'T830=0')
        result = TRIAL.analyse_egl(log)
        self.assertEqual(result['status'], 'context-ready')
        self.assertEqual(result['path'], 'display')
        self.assertFalse(result['panfrost_t830_context'])

    def test_marker_without_corresponding_renderer_or_ready_context_is_insufficient(self):
        for log in ('NATIVE_EGL_PANFROST_T830=1\n',
                    PANFROST.replace('NATIVE_EGL_CONTEXT_READY', 'FAILED'),
                    PANFROST.replace('Mali T830 (Panfrost)', 'llvmpipe'),
                    PANFROST.replace('NATIVE_EGL_PATH=render DRM_DRIVER=panfrost', '')):
            with self.subTest(log=log):
                self.assertFalse(TRIAL.analyse_egl(log)['panfrost_t830_context'])

    def test_missing_or_failed_context_stays_unverified(self):
        self.assertEqual(TRIAL.analyse_egl('')['status'], 'not-run')
        self.assertEqual(TRIAL.analyse_egl('EGL initialization failed: 0x3001')['status'], 'inconclusive')


if __name__ == '__main__':
    unittest.main()
