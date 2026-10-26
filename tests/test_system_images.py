import contextlib
import importlib.util
import io
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


builder = load('system_builder_test', 'build-system.py')
flasher = load('system_flasher_test', 'flash-system.py')


class SparseTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        patch = mock.patch.object(builder, 'DATA_BYTES', 12288)
        patch.start(); self.addCleanup(patch.stop)

    def fixture(self):
        raw = self.root / 'raw'
        with raw.open('wb') as file:
            file.write(b'A' * 4096)
            file.seek(8192); file.write(b'B' * 4096)
        encoded = self.root / 'sparse'
        encoded.write_bytes(struct.pack('<IHHHHIIII', 0xed26ff3a, 1, 0, 28, 12, 4096, 3, 3, 0)
                            + struct.pack('<HHII', 0xcac1, 0, 1, 4108) + b'A' * 4096
                            + struct.pack('<HHII', 0xcac2, 0, 1, 16) + b'\0' * 4
                            + struct.pack('<HHII', 0xcac1, 0, 1, 4108) + b'B' * 4096)
        return encoded, raw

    def test_exact_roundtrip_with_holes_between_raw_chunks(self):
        encoded, raw = self.fixture()
        self.assertEqual(builder.sparse_info(encoded)['expanded_bytes'], 12288)
        builder.verify_sparse_roundtrip(encoded, raw)

    def test_corrupt_raw_or_fill_data_refused(self):
        encoded, raw = self.fixture()
        with raw.open('r+b') as file: file.seek(4200); file.write(b'C')
        with self.assertRaisesRegex(ValueError, 'fill/skip'):
            builder.verify_sparse_roundtrip(encoded, raw)
        encoded, raw = self.fixture()
        with raw.open('r+b') as file: file.seek(8200); file.write(b'C')
        with self.assertRaisesRegex(ValueError, 'RAW'):
            builder.verify_sparse_roundtrip(encoded, raw)

    def test_truncated_chunk_and_trailing_payload_refused(self):
        encoded, _ = self.fixture()
        content = encoded.read_bytes()
        for invalid in (content[:-1], content + b'extra'):
            encoded.write_bytes(invalid)
            with self.assertRaises(ValueError): builder.sparse_info(encoded)

    def test_expanded_partition_overflow_refused(self):
        encoded, _ = self.fixture()
        content = bytearray(encoded.read_bytes())
        struct.pack_into('<I', content, 16, 4)
        encoded.write_bytes(content)
        with self.assertRaisesRegex(ValueError, 'capacity'):
            builder.sparse_info(encoded)

    def samsung_report(self):
        return """Free blocks: 1
Group 0: (Blocks 0-2) csum 0x1234
  1 free blocks, 0 free inodes
  Free blocks: 1
"""

    def test_samsung_raw_skip_and_zero_allocated_metadata(self):
        image = self.root / 'ext4'
        # Block zero is allocated zero metadata; it MUST be RAW, not skipped.
        image.write_bytes(bytes(8192) + b'B' * 4096)
        encoded = self.root / 'samsung'
        builder.write_samsung_sparse(image, encoded, self.samsung_report())
        info = builder.sparse_info(encoded)
        self.assertEqual(info['encoding'], 'samsung-j701f-raw-skip')
        self.assertEqual(info['chunk_types'], {'0xcac1': 2, '0xcac3': 1})
        self.assertEqual(encoded.read_bytes()[32:48], struct.pack('<HHIII', 0xcac1, 0, 1, 4112, 0x55ca))
        builder.verify_sparse_roundtrip(encoded, image)
        with image.open('r+b') as file: file.seek(4096); file.write(b'C')
        with self.assertRaisesRegex(ValueError, 'fill/skip'):
            builder.verify_sparse_roundtrip(encoded, image)

    def test_allocation_map_bounds_completeness_and_totals(self):
        valid = self.samsung_report()
        self.assertEqual(builder.ext4_free_ranges(valid, 3), [(1, 2)])
        for invalid in (valid.replace('Free blocks: 1', 'Free blocks: 2', 1),
                        valid.replace('  Free blocks: 1', '  Free blocks: 1, 1'),
                        valid.replace('  Free blocks: 1', '  Free blocks: 3'),
                        valid.replace('Blocks 0-2', 'Blocks 1-2'),
                        valid.replace('1 free blocks,', '2 free blocks,')):
            with self.assertRaises(ValueError): builder.ext4_free_ranges(invalid, 3)

    def test_samsung_extension_and_fill_chunks_refused(self):
        image = self.root / 'ext4'; image.write_bytes(bytes(12288))
        encoded = self.root / 'samsung'
        builder.write_samsung_sparse(image, encoded, self.samsung_report())
        content = encoded.read_bytes()
        for offset in (28, 44):
            invalid = bytearray(content); invalid[offset] ^= 1; encoded.write_bytes(invalid)
            with self.assertRaisesRegex(ValueError, 'extension'): builder.sparse_info(encoded)
        invalid = bytearray(content); struct.pack_into('<H', invalid, 32, 0xcac2)
        encoded.write_bytes(invalid)
        with self.assertRaisesRegex(ValueError, 'extension/type'): builder.sparse_info(encoded)


class FlasherTests(unittest.TestCase):
    def invoke(self, arguments, fail_first=False):
        device = '/dev/bus/usb/001/007'
        with mock.patch.object(sys, 'argv', ['flash-system'] + arguments), \
             mock.patch.object(flasher, 'verify') as verification, \
             mock.patch.object(flasher, 'listed_devices', return_value=[device]) as discovery, \
             mock.patch.object(flasher.subprocess, 'run') as invocation, \
             contextlib.redirect_stdout(io.StringIO()):
            if fail_first:
                invocation.side_effect = subprocess.CalledProcessError(1, 'odin')
                with self.assertRaises(subprocess.CalledProcessError): flasher.main()
            else:
                flasher.main()
            return invocation.call_args_list, verification.call_count, discovery.call_count

    def test_default_dry_run_does_not_even_probe_usb(self):
        calls, verifications, discoveries = self.invoke([])
        self.assertEqual(calls, [])
        self.assertEqual(verifications, 1)
        self.assertEqual(discoveries, 0)

    def test_user_data_failure_never_flashes_boot(self):
        calls, _, _ = self.invoke(['--execute', '--device', '/dev/bus/usb/001/007', '--discard-existing-data'], True)
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].args[0][2].endswith('/userdata.tar'))

    def test_only_agreed_targets_and_reboot_only_on_boot(self):
        calls, _, _ = self.invoke(['--execute', '--device', '/dev/bus/usb/001/007', '--discard-existing-data', '--reboot'])
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].args[0][2].endswith('/userdata.tar'))
        self.assertTrue(calls[1].args[0][2].endswith('/boot.tar'))
        self.assertNotIn('--reboot', calls[0].args[0])
        self.assertEqual(calls[1].args[0][-1], '--reboot')
        for call in calls:
            self.assertFalse({'-e', '-b', '-s', '-c', '--repartition'} & set(call.args[0]))

    def test_explicit_execution_guards_before_validation(self):
        for arguments in (['--execute'], ['--execute', '--device', '/dev/bus/usb/001/007'],
                          ['--execute', '--device', '/dev/bus/usb/001/007;bad', '--discard-existing-data']):
            with mock.patch.object(sys, 'argv', ['flash-system'] + arguments), \
                 mock.patch.object(flasher, 'verify') as verification:
                with self.assertRaises(ValueError): flasher.main()
                verification.assert_not_called()

    def test_boot_only_resume_never_touches_data(self):
        calls, _, _ = self.invoke(['--execute', '--device', '/dev/bus/usb/001/007', '--boot-only'])
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].args[0][2].endswith('/boot.tar'))

    def test_staged_data_only_never_flashes_or_reboots_boot(self):
        calls, _, _ = self.invoke(['--execute', '--device', '/dev/bus/usb/001/007',
                                   '--discard-existing-data', '--data-only'])
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].args[0][2].endswith('/userdata.tar'))
        self.assertNotIn('--reboot', calls[0].args[0])
        with self.assertRaisesRegex(ValueError, 'must not reboot'):
            self.invoke(['--data-only', '--reboot'])

    def test_disappeared_device_stops_all_writes(self):
        with mock.patch.object(sys, 'argv', ['flash-system', '--execute', '--device', '/dev/bus/usb/001/007', '--discard-existing-data']), \
             mock.patch.object(flasher, 'verify'), \
             mock.patch.object(flasher, 'listed_devices', return_value=[]), \
             mock.patch.object(flasher.subprocess, 'run') as invocation, \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError): flasher.main()
            invocation.assert_not_called()


if __name__ == '__main__':
    unittest.main()
