"""Regression checks for firmware packaging and recovery-only boundaries."""
import gzip
import io
import lzma
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import recovery as r


@unittest.skipUnless((r.ROOT / 'original/OrangeFox-recovery.img').is_file()
                     and (r.ROOT / 'build/recovery.img').is_file(),
                     'the user-supplied OrangeFox image and a stage-1 build (make) are required')
class RecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = r.baseline()
        cls.built = (r.ROOT / 'build/recovery.img').read_bytes()

    def test_original_roundtrip(self):
        self.assertEqual(self.old.repack(self.old.parts['ramdisk']), self.old.data)

    def test_header_and_payload_preservation(self):
        new = r.verify_image(self.built)
        changes = {i for i, (a, b) in enumerate(zip(self.old.header, new.header)) if a != b}
        self.assertTrue(changes <= set(range(16, 20)) | set(range(576, 596)))
        for name in ('kernel', 'dt', 'second'):
            self.assertEqual(self.old.parts[name], new.parts[name])

    def test_wrong_address_rejected_even_with_valid_id(self):
        data = bytearray(self.built)
        data[12] ^= 1  # Boot ID does not cover header load addresses.
        with self.assertRaisesRegex(ValueError, 'Header bytes changed'):
            r.verify_image(bytes(data))

    def test_corrupt_kernel_rejected(self):
        data = bytearray(self.built)
        data[self.old.page + 1000] ^= 1
        with self.assertRaisesRegex(ValueError, 'SHA-1 mismatch'):
            r.Image(bytes(data))

    def test_changed_kernel_rejected_even_with_new_digest(self):
        new = r.Image(self.built)
        new.parts['kernel'] = new.parts['kernel'][:-1] + bytes([new.parts['kernel'][-1] ^ 1])
        with self.assertRaisesRegex(ValueError, 'kernel changed'):
            r.verify_image(new.repack(new.parts['ramdisk']))

    def test_truncation_and_unknown_trailer_rejected(self):
        for data in (self.built[:2048], self.built[:-1], self.built+b'AVBf'):
            with self.assertRaises(ValueError):
                r.Image(data)

    def test_modern_header_rejected(self):
        data = bytearray(self.built)
        struct.pack_into('<I', data, 40, 2)
        with self.assertRaisesRegex(ValueError, 'legacy dt_size'):
            r.Image(bytes(data))

    def test_nonzero_padding_rejected(self):
        data = bytearray(self.built)
        data[self.old.page + len(self.old.parts['kernel'])] = 1
        with self.assertRaisesRegex(ValueError, 'padding'):
            r.Image(bytes(data))

    def test_initramfs_nodes_ownership_and_compression(self):
        raw = lzma.decompress(r.Image(self.built).parts['ramdisk'])
        r.validate_ramdisk(raw)
        self.assertEqual(raw, gzip.decompress((r.ROOT / 'build/ramdisk.cpio.gz').read_bytes()))
        entries = {n: (v, d) for n, v, d in r.cpio_entries(raw)}
        self.assertEqual(entries['dev/console'][0][9:11], [5, 1])
        self.assertEqual(entries['init'][0][1], stat.S_IFREG | 0o755)
        self.assertEqual(entries['bin/sh'][1], b'busybox')

    def test_unsafe_cpio_rejected(self):
        for name in ('/etc/passwd', '../escape'):
            raw = r.cpio_record(name) + r.cpio_record('TRAILER!!!')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                list(r.cpio_entries(raw))

    def test_static_aarch64_and_wrong_architecture(self):
        data = bytearray((r.ROOT / 'ramdisk/bin/busybox').read_bytes())
        r.elf_static(data)
        struct.pack_into('<H', data, 18, 62)
        with self.assertRaisesRegex(ValueError, 'AArch64'):
            r.elf_static(data)

    def test_dynamic_binary_rejected(self):
        data = bytearray((r.ROOT / 'ramdisk/bin/busybox').read_bytes())
        offset = struct.unpack_from('<Q', data, 32)[0]
        struct.pack_into('<I', data, offset, 3)
        with self.assertRaisesRegex(ValueError, 'PT_DYNAMIC/PT_INTERP'):
            r.elf_static(data)

    def test_tar_rejects_extra_or_wrong_partition_or_symlink(self):
        for names in (['recovery.img', 'boot.img'], ['boot.img'], ['../recovery.img'], ['recovery.img', 'recovery.img']):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'bad.tar'
                with tarfile.open(path, 'w') as archive:
                    for name in names:
                        info = tarfile.TarInfo(name)
                        info.size = 0
                        archive.addfile(info, io.BytesIO())
                with self.assertRaisesRegex(ValueError, 'ONLY'):
                    r.verify_tar(path)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'link.tar'
            with tarfile.open(path, 'w') as archive:
                info = tarfile.TarInfo('recovery.img')
                info.type, info.linkname = tarfile.SYMTYPE, 'boot.img'
                archive.addfile(info)
            with self.assertRaisesRegex(ValueError, 'ONLY'):
                r.verify_tar(path)

    def test_restore_exact_baseline(self):
        self.assertEqual(r.verify_tar(r.ROOT / 'build/OrangeFox-restore.tar', True), self.old.data)
        with self.assertRaisesRegex(ValueError, 'exact OrangeFox'):
            r.verify_image(self.built, True)

    def test_appended_archive_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'appended.tar'
            path.write_bytes(r.tar_bytes(self.built) + b'hidden trailing payload')
            with self.assertRaisesRegex(ValueError, 'canonical'):
                r.verify_tar(path)

    def test_dry_run_does_not_execute_odin(self):
        result = subprocess.run(['bash', str(r.ROOT / 'scripts/flash.sh')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PLAN ONLY', result.stdout)
        self.assertIn('RECOVERY only', result.stdout)

    def test_flash_requires_explicit_usb_path(self):
        result = subprocess.run(['bash', str(r.ROOT / 'scripts/flash.sh'), '--execute'],
                                input='', capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('explicit Odin USB path required', result.stderr)

    def test_flash_rejects_extra_odin_options(self):
        result = subprocess.run(['bash', str(r.ROOT / 'scripts/flash.sh'), '-e'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
