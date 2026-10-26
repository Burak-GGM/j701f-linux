"""Adversarial checks for the built embedded diagnostic; never accesses a phone."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('embedded_package', ROOT / 'tools/package-embedded-mainline-diagnostic.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class EmbeddedContainerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader_dir = ROOT / os.environ.get('J701F_TEST_LOADER', 'build/kernel/uboot-j701f-embedded')
        if not (loader_dir / 'report.json').exists():
            raise unittest.SkipTest('Build the embedded loader first')
        cls.loader = (loader_dir / 'u-boot.bin').read_bytes()
        cls.info = json.loads((loader_dir / 'report.json').read_text())
        fit_dir = ROOT / os.environ.get('J701F_TEST_FIT', str(p.OUT))
        cls.fit = (fit_dir / 'mainline.itb').read_bytes()
        cls.stub = (p.stub_tool.OUT / 'stub-dtbh.img').read_bytes()
        cls.old = p.recovery.baseline()
        cls.data = p.package(cls.old, cls.loader, cls.fit, cls.stub, cls.info)

    def verify(self, data):
        return p.verify(data, self.old, self.loader, self.fit, self.stub, self.info)

    def test_complete_container(self):
        self.assertTrue(self.verify(self.data)['empty_android_ramdisk'])

    def test_changed_load_address(self):
        data = bytearray(self.data)
        struct.pack_into('<I', data, 12, 0x80000000)
        with self.assertRaisesRegex(ValueError, 'header change'):
            self.verify(bytes(data))

    def test_nonempty_android_ramdisk(self):
        image = p.recovery.Image(self.data)
        with self.assertRaisesRegex(ValueError, 'ramdisk'):
            self.verify(image.repack(b'wrong-firmware-initrd'))

    def test_corrupt_embedded_fit_with_valid_container_digest(self):
        image = p.recovery.Image(self.data)
        parts = dict(image.parts)
        loader = bytearray(parts['kernel'])
        loader[self.info['embedded_fit']['offset'] + 1024] ^= 1
        parts['kernel'] = bytes(loader)
        data = bytearray(self.data)
        data[image.offsets['kernel']:image.offsets['kernel'] + len(loader)] = loader
        data[576:596] = p.recovery.Image.digest(parts)
        with self.assertRaisesRegex(ValueError, 'kernel'):
            self.verify(bytes(data))

    def test_wrong_stub_revision_with_valid_digest(self):
        image = p.recovery.Image(self.data)
        parts = dict(image.parts)
        stub = bytearray(self.stub)
        struct.pack_into('<I', stub, 12 + 2 * 32 + 12, 4)
        parts['dt'] = bytes(stub)
        data = bytearray(self.data)
        data[image.offsets['dt']:image.offsets['dt'] + len(stub)] = stub
        data[576:596] = p.recovery.Image.digest(parts)
        with self.assertRaisesRegex(ValueError, 'dt'):
            self.verify(bytes(data))

    def test_truncated_image(self):
        with self.assertRaises(ValueError):
            self.verify(self.data[:4096])

    def test_monitor_does_not_cover_payload(self):
        info = json.loads(json.dumps(self.info))
        info['embedded_fit']['monitor_bytes'] = 38368
        with self.assertRaisesRegex(ValueError, 'bounds'):
            p.checked_inputs(self.loader, self.fit, self.stub, info)


if __name__ == '__main__':
    unittest.main()
