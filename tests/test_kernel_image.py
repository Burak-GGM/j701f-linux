import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kernel_build', ROOT / 'tools/build-kernel.py')
kernel_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kernel_build)


class KernelHeaderTests(unittest.TestCase):
    def header(self, memory_size=4 * 1024 * 1024, flags=0):
        image = bytearray(4096)
        struct.pack_into('<3Q', image, 8, 0x80000, memory_size, flags)
        image[56:60] = b'ARM\x64'
        return image

    def check(self, image):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'Image'
            path.write_bytes(image)
            return kernel_build.check_image(path)

    def test_runtime_memory_reservation_can_exceed_file_size(self):
        info = self.check(self.header())
        self.assertEqual(info['bytes'], 4096)
        self.assertEqual(info['image_size'], 4 * 1024 * 1024)

    def test_non_arm_or_truncated_header_is_rejected(self):
        image = self.header()
        image[56] = 0
        for bad in (image, b'ARM\x64'):
            with self.assertRaisesRegex(ValueError, 'magic'):
                self.check(bad)

    def test_invalid_memory_bound_or_big_endian_target_is_rejected(self):
        for bad in (self.header(0), self.header(1024 * 1024 * 1024), self.header(flags=1)):
            with self.assertRaises(ValueError):
                self.check(bad)


if __name__ == '__main__':
    unittest.main()
