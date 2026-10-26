"""Reject corrupt payloads, unsafe RAM plans and unintended container changes."""
import importlib.util
import gzip
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


fit = load('fit', 'build-mainline-fit.py')
container = load('container', 'package-mainline-diagnostic.py')


class MemoryPlans(unittest.TestCase):
    def test_oversized_kernel_cannot_cross_vendor_debug_memory(self):
        hw = json.loads((ROOT / 'kernel/j701f-hardware.json').read_text())
        with self.assertRaisesRegex(ValueError, 'reserved memory'):
            fit.layout(100 * 1024 * 1024, 0, 50000, 700000, hw)

    def test_unaligned_ram_base_rejected(self):
        hw = json.loads((ROOT / 'kernel/j701f-hardware.json').read_text())
        hw['memory']['memory@40000000'][1] += 4096
        with self.assertRaisesRegex(ValueError, '2 MiB aligned'):
            fit.layout(20 * 1024 * 1024, 0, 50000, 700000, hw)


class CompressedPayloadChecks(unittest.TestCase):
    def test_gzip_round_trip(self):
        raw = b'ARM64 kernel bytes' * 100
        fit.validate_payload(gzip.compress(raw, mtime=0), raw, 'gzip')

    def test_truncated_gzip_rejected(self):
        raw = b'kernel'
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            fit.validate_payload(gzip.compress(raw, mtime=0)[:-1], raw, 'gzip')

    def test_corrupt_gzip_checksum_rejected(self):
        raw = b'kernel'
        data = bytearray(gzip.compress(raw, mtime=0)); data[-8] ^= 1
        with self.assertRaisesRegex(ValueError, 'Invalid gzip'):
            fit.validate_payload(data, raw, 'gzip')

    def test_gzip_trailing_data_rejected(self):
        raw = b'kernel'
        with self.assertRaisesRegex(ValueError, 'trailing'):
            fit.validate_payload(gzip.compress(raw, mtime=0) + b'junk', raw, 'gzip')

    def test_second_gzip_member_rejected(self):
        raw = b'kernel'
        data = gzip.compress(raw, mtime=0)
        with self.assertRaisesRegex(ValueError, 'trailing'):
            fit.validate_payload(data + data, raw, 'gzip')

    def test_expansion_beyond_expected_size_rejected(self):
        with self.assertRaisesRegex(ValueError, 'oversized'):
            fit.validate_payload(gzip.compress(bytes(1024 * 1024), mtime=0), b'kernel', 'gzip')

    def test_wrong_decompressed_bytes_rejected(self):
        with self.assertRaisesRegex(ValueError, 'payload mismatch'):
            fit.validate_payload(gzip.compress(b'wrong!', mtime=0), b'kernel', 'gzip')


@unittest.skipUnless((fit.OUT / 'mainline.itb').exists(), 'Build RAM FIT first')
class PayloadChecks(unittest.TestCase):
    def test_truncated_fit_rejected(self):
        with self.assertRaisesRegex(ValueError, 'FIT header'):
            fit.fit_properties((fit.OUT / 'mainline.itb').read_bytes()[:-1])

    def test_corrupt_kernel_in_fit_rejected(self):
        data = bytearray((fit.OUT / 'mainline.itb').read_bytes())
        report = json.loads((fit.OUT / 'report.json').read_text())
        inputs = {name: ROOT / value['path'] for name, value in report['inputs'].items()}
        # Claude 2026-10-08: the default FIT is the preserved first-trial artifact.
        # Once the kernel Image is rebuilt it no longer contains the current bytes.
        import hashlib
        if hashlib.sha256(inputs['kernel'].read_bytes()).hexdigest() != report['inputs']['kernel']['sha256']:
            self.skipTest('default FIT predates the current kernel Image')
        # Corrupt an actual kernel payload byte, leaving the FIT structure intact.
        marker = inputs['kernel'].read_bytes()[:64]
        position = data.index(marker)
        data[position + 63] ^= 1
        with self.assertRaisesRegex(ValueError, 'payload mismatch'):
            fit.verify(bytes(data), inputs, report['layout'])


@unittest.skipUnless((fit.OUT / 'recovery-mainline-diagnostic.preview.img').exists(), 'Package preview first')
class ContainerChecks(unittest.TestCase):
    def test_changed_load_address_rejected(self):
        data = bytearray((fit.OUT / 'recovery-mainline-diagnostic.preview.img').read_bytes())
        data[12] ^= 1
        old = container.recovery.baseline()
        loader = (ROOT / 'build/kernel/uboot-j701f-diagnostic/u-boot.bin').read_bytes()
        payload = (fit.OUT / 'mainline.itb').read_bytes()
        with self.assertRaisesRegex(ValueError, 'Unexpected header change'):
            container.verify(bytes(data), old, loader, payload)


if __name__ == '__main__':
    unittest.main()
