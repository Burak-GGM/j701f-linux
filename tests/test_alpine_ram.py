import importlib.util
import io
from pathlib import Path
import struct
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('alpine_ram', ROOT / 'tools/alpine-ram-test.py')
alpine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alpine)


class AlpineArchiveTests(unittest.TestCase):
    def archive(self, extra=(), machine=183):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'root.tar.gz'
        elf = bytearray(64)
        elf[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<H', elf, 18, machine)
        with tarfile.open(path, 'w:gz') as archive:
            for name in ('bin', 'lib', 'sbin', 'etc'):
                entry = tarfile.TarInfo(name)
                entry.type = tarfile.DIRTYPE
                archive.addfile(entry)
            for name, content in [('bin/busybox', elf), ('lib/ld-musl-aarch64.so.1', elf),
                                  ('sbin/apk', elf), ('etc/alpine-release', b'3.24.0\n')]:
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                archive.addfile(entry, io.BytesIO(content))
            for entry, content in extra:
                archive.addfile(entry, io.BytesIO(content) if content else None)
        return path

    def test_valid_arm64_root_and_absolute_init_link(self):
        init = tarfile.TarInfo('sbin/init')
        init.type = tarfile.SYMTYPE; init.linkname = '/bin/busybox'
        info = alpine.inspect_archive(self.archive([(init, None)]))
        self.assertEqual(info['release'], '3.24.0')
        self.assertFalse(info['openrc_present'])

    def test_parent_traversal_and_absolute_member_paths_rejected(self):
        for name in ('../outside', '/outside', 'etc/../../outside'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    alpine.inspect_archive(self.archive([(tarfile.TarInfo(name), None)]))

    def test_symlink_escape_rejected(self):
        entry = tarfile.TarInfo('etc/escape')
        entry.type = tarfile.SYMTYPE; entry.linkname = '../../outside'
        with self.assertRaisesRegex(ValueError, 'escapes'):
            alpine.inspect_archive(self.archive([(entry, None)]))

    def test_extraction_through_absolute_symlink_rejected(self):
        link = tarfile.TarInfo('escape')
        link.type = tarfile.SYMTYPE; link.linkname = '/tmp'
        entry = tarfile.TarInfo('escape/file')
        with self.assertRaisesRegex(ValueError, 'ancestor'):
            alpine.inspect_archive(self.archive([(link, None), (entry, None)]))

    def test_device_nodes_and_setuid_rejected(self):
        node = tarfile.TarInfo('dev/storage')
        node.type = tarfile.BLKTYPE; node.devmajor = 179; node.devminor = 0
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            alpine.inspect_archive(self.archive([(node, None)]))
        executable = tarfile.TarInfo('suid')
        executable.mode = 0o4755
        with self.assertRaisesRegex(ValueError, 'Setuid'):
            alpine.inspect_archive(self.archive([(executable, None)]))

    def test_duplicate_and_unsafe_hardlink_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            alpine.inspect_archive(self.archive([(tarfile.TarInfo('etc/alpine-release'), None)]))
        link = tarfile.TarInfo('hardlink')
        link.type = tarfile.LNKTYPE; link.linkname = '../outside'
        with self.assertRaisesRegex(ValueError, 'traverses'):
            alpine.inspect_archive(self.archive([(link, None)]))

    def test_wrong_architecture_rejected(self):
        with self.assertRaisesRegex(ValueError, 'AArch64'):
            alpine.inspect_archive(self.archive(machine=62))


if __name__ == '__main__':
    unittest.main()
