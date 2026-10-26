"""tools/build-kernel.py: local patches are applied once, and an edited patch replaces its older version."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('kernel_build_patches', ROOT / 'tools/build-kernel.py')
kernel_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kernel_build)


def new_file_patch(text):
    lines = text.splitlines()
    return ('--- /dev/null\n+++ b/driver.c\n@@ -0,0 +1,%d @@\n' % len(lines)
            + ''.join('+' + line + '\n' for line in lines))


class ApplyPatches(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.src = base / 'sources' / 'linux-9.9'
        self.src.mkdir(parents=True)
        (self.src / 'Makefile').write_text('obj-y += a.o\n')
        self.patch = base / 'linux-local-driver.patch'
        self.patch.write_text(new_file_patch('first version\n'))

    def markers(self):
        return sorted(p.name for p in self.src.parent.glob('*.applied'))

    def test_applied_once(self):
        kernel_build.apply_patches(self.src, [self.patch])
        self.assertEqual((self.src / 'driver.c').read_text(), 'first version\n')
        kernel_build.apply_patches(self.src, [self.patch])     # second run: nothing to do
        self.assertEqual(len(self.markers()), 1)

    def test_edited_patch_replaces_the_older_version(self):
        kernel_build.apply_patches(self.src, [self.patch])
        self.patch.write_text(new_file_patch('second version\nwith two lines\n'))
        kernel_build.apply_patches(self.src, [self.patch])
        self.assertEqual((self.src / 'driver.c').read_text(), 'second version\nwith two lines\n')
        self.assertEqual(len(self.markers()), 1)

    def test_tree_prepared_before_copies_were_kept_is_refused(self):
        kernel_build.apply_patches(self.src, [self.patch])
        for kept in self.src.parent.glob('*.patch'):
            kept.unlink()
        self.patch.write_text(new_file_patch('second version\n'))
        with self.assertRaises(ValueError):
            kernel_build.apply_patches(self.src, [self.patch])
        self.assertEqual((self.src / 'driver.c').read_text(), 'first version\n')

    def test_patch_with_a_longer_name_is_not_mistaken_for_an_older_version(self):
        other = self.patch.with_name('linux-local-driver.extra.patch')
        other.write_text('--- a/Makefile\n+++ b/Makefile\n@@ -1 +1,2 @@\n obj-y += a.o\n+obj-y += b.o\n')
        kernel_build.apply_patches(self.src, [other, self.patch])
        self.assertEqual(len(self.markers()), 2)
        self.assertIn('b.o', (self.src / 'Makefile').read_text())


if __name__ == '__main__':
    unittest.main()
