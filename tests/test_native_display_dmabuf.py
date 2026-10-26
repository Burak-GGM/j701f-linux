"""CPU buffer-interpretation guards and synthetic shared-render evidence."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('shared_native_trial', ROOT / 'tools/run-native-display-trial.py')
TRIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRIAL)
SUCCESS = '''NATIVE_SHARED_BUFFER width=720 height=1280 format=XRGB8888 stride=2880 modifier=0
NATIVE_SHARED_RENDERER=Mali T830 (Panfrost)
NATIVE_SHARED_EGLIMAGE_IMPORT_OK
NATIVE_SHARED_GPU_RENDER_READBACK_OK pixels=4096
NATIVE_SHARED_CPU_BUFFER_OK pixels=4096
NATIVE_SHARED_FB_OBJECT_OK; buffer never attached to a plane
'''


class SharedRenderEvidenceTests(unittest.TestCase):
    def test_shared_gpu_write_is_separate_from_actual_scanout(self):
        result = TRIAL.analyse_shared_render(SUCCESS)
        self.assertTrue(result['shared_gpu_buffer_verified'])
        self.assertTrue(result['framebuffer_object_verified'])
        self.assertFalse(result['scanout_performed'])

    def test_every_required_stage_and_hardware_identity_is_required(self):
        for line in SUCCESS.splitlines()[:5]:
            with self.subTest(line=line):
                self.assertFalse(TRIAL.analyse_shared_render(SUCCESS.replace(line, ''))['shared_gpu_buffer_verified'])
        for old, new in [('Mali T830 (Panfrost)', 'llvmpipe'), ('stride=2880', 'stride=256'),
                         ('modifier=0', 'modifier=123'), ('pixels=4096', 'pixels=16')]:
            with self.subTest(old=old):
                self.assertFalse(TRIAL.analyse_shared_render(SUCCESS.replace(old, new))['shared_gpu_buffer_verified'])

    def test_gpu_bytes_without_fb_still_do_not_prove_display_compatibility(self):
        result = TRIAL.analyse_shared_render(SUCCESS.replace('NATIVE_SHARED_FB_OBJECT_OK', 'FB_FAILED'))
        self.assertTrue(result['shared_gpu_buffer_verified'])
        self.assertFalse(result['framebuffer_object_verified'])
        self.assertFalse(result['scanout_performed'])

    def test_missing_log_is_not_a_hardware_failure_or_success(self):
        self.assertEqual(TRIAL.analyse_shared_render('')['status'], 'not-run')


@unittest.skipUnless(shutil.which('clang'), 'clang required')
class ExportedByteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-exported-bytes-')
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        source = (ROOT / 'tools/native-display-dmabuf.c').read_text()
        function = source[source.index('static bool validate_exported_bytes('):
                          source.index('static bool driver_is(')]
        main = r'''
int main(int argc, char **argv)
{
    assert(argc == 2); int which = atoi(argv[1]);
    size_t length = 512 * EDGE, stride = 320;
    unsigned char *bytes = calloc(1, length); assert(bytes);
    for (unsigned y = 0; y < EDGE; y++) for (unsigned x = 0; x < EDGE; x++) {
        unsigned char *p = bytes + y * stride + x * 4;
        bool odd = (x + y) & 1;
        p[1] = odd ? 255 : 0; p[2] = odd ? 0 : 255;
        p[3] = 17; /* X is unused; it must not be compared as alpha. */
    }
    if (which == 1) bytes[2] ^= 1;
    if (which == 2) { bytes[0] = bytes[2]; bytes[2] = 0; }
    if (which == 3) length = (EDGE - 1) * stride + EDGE * 4 - 1;
    if (which == 4) stride += 4;
    if (which == 5) stride = SIZE_MAX;
    if (which == 6) stride = 0;
    bool ok = validate_exported_bytes(which == 7 ? NULL : bytes, length, stride);
    printf("%d\n", ok); free(bytes);
}
'''
        file = root / 'bytes.c'
        file.write_text('#include <assert.h>\n#include <stdbool.h>\n#include <stdint.h>\n'
                        '#include <stdio.h>\n#include <stdlib.h>\nenum { EDGE=64 };\n'+function+main)
        cls.binary = root / 'bytes'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', str(file), '-o', str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def run_case(self, case):
        return subprocess.check_output([str(self.binary), str(case)], text=True,
                                       env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0')).strip()

    def test_padded_stride_and_unused_alpha_are_supported(self):
        self.assertEqual(self.run_case(0), '1')

    def test_corrupted_or_wrong_channel_pixels_are_rejected(self):
        for case in (1, 2):
            with self.subTest(case=case):
                self.assertEqual(self.run_case(case), '0')

    def test_truncated_mapping_wrong_stride_and_overflow_are_rejected(self):
        for case in (3, 4, 5, 6, 7):
            with self.subTest(case=case):
                self.assertEqual(self.run_case(case), '0')


if __name__ == '__main__':
    unittest.main()
