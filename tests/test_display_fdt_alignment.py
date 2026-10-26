"""libfdt rejects a valid blob at a misaligned address; check real build data."""
import ctypes
import ctypes.util
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT/'build/kernel/display-runtime'


@unittest.skipUnless((ART/'module/display-overlay-blob.h').exists(), 'Build overlay first')
class FdtAlignmentTests(unittest.TestCase):
    def test_compiled_embedded_blob_passes_real_libfdt_but_misaligned_copy_fails(self):
        lib = ctypes.util.find_library('fdt')
        if not lib:
            self.skipTest('Host libfdt unavailable')
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder)/'blob.c'
            src.write_text('#define __aligned(n) __attribute__((aligned(n)))\n'
                '#include "'+str(ART/'module/display-overlay-blob.h')+'"\n'
                'const void *blob(void) { return display_overlay_blob; }\n')
            shared = Path(folder)/'blob.so'
            subprocess.run(['cc', '-shared', '-fPIC', '-Wall', '-Wextra', '-Werror',
                            str(src), '-o', str(shared)], check=True, capture_output=True)
            compiled = ctypes.CDLL(str(shared))
            compiled.blob.restype = ctypes.c_void_p
            pointer = compiled.blob()
            self.assertEqual(pointer % 8, 0)
            fdt = ctypes.CDLL(lib)
            fdt.fdt_check_header.argtypes = [ctypes.c_void_p]
            fdt.fdt_check_header.restype = ctypes.c_int
            self.assertEqual(fdt.fdt_check_header(pointer), 0)
            blob = (ART/'display.dtbo').read_bytes()
            space = ctypes.create_string_buffer(len(blob)+16)
            aligned = (ctypes.addressof(space)+7) & ~7
            ctypes.memmove(aligned+1, blob, len(blob))
            self.assertNotEqual(fdt.fdt_check_header(aligned+1), 0)

    def test_actual_aarch64_module_symbol_and_rodata_have_required_alignment(self):
        ko = str(ART/'j701f-display-overlay.ko')
        symbols = subprocess.check_output(['readelf', '-sW', ko], text=True)
        match = re.search(r'^\s*\d+:\s*([0-9a-f]+)\s+\d+\s+OBJECT\s+LOCAL\s+DEFAULT\s+\d+\s+display_overlay_blob$',
                          symbols, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(int(match.group(1), 16) % 8, 0)
        sections = subprocess.check_output(['readelf', '-SW', ko], text=True)
        rodata = next(line for line in sections.splitlines() if '] .rodata ' in line)
        self.assertGreaterEqual(int(rodata.split()[-1]), 8)


if __name__ == '__main__':
    unittest.main()
