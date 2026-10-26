# Written by Claude 2026-10-10. recovery/scripts/settings.sh on a file standing
# in for the RECOVERY slot.
import os, pathlib, subprocess, tempfile, unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'recovery/scripts/settings.sh'
SLOT = 77824 * 512


class Settings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dev = pathlib.Path(self.tmp.name) / 'slot.img'
        self.image = os.urandom(16 * 1024 * 1024)          # an installed recovery image
        self.dev.write_bytes(self.image + bytes(SLOT - len(self.image)))

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *a):
        return subprocess.run(['sh', str(SCRIPT), *a], capture_output=True, text=True,
                              env={**os.environ, 'J701F_RECOVERY_SETTINGS_DEV': str(self.dev)})

    def test_unset_is_empty(self):
        r = self.run_script('get', 'lang')
        self.assertEqual((r.returncode, r.stdout), (0, ''))

    def test_set_get_and_replace(self):
        self.assertEqual(self.run_script('set', 'lang', 'tr').returncode, 0)
        self.assertEqual(self.run_script('set', 'other', 'x1').returncode, 0)
        self.assertEqual(self.run_script('set', 'lang', 'en').returncode, 0)
        self.assertEqual(self.run_script('get', 'lang').stdout, 'en\n')
        self.assertEqual(self.run_script('get', 'other').stdout, 'x1\n')

    def test_only_one_block_changes_and_the_image_is_untouched(self):
        before = self.dev.read_bytes()
        self.run_script('set', 'lang', 'tr')
        after = self.dev.read_bytes()
        self.assertEqual(len(after), SLOT)
        self.assertEqual(after[:len(self.image)], self.image)
        at = (77824 - 2048) * 512
        self.assertEqual(before[:at], after[:at])
        self.assertEqual(before[at + 512:], after[at + 512:])
        self.assertNotEqual(before[at:at + 512], after[at:at + 512])

    def test_bad_values_are_refused(self):
        for key, value in (('lang', 'tr; rm -rf /'), ('la ng', 'tr'), ('lang', '')):
            r = self.run_script('set', key, value)
            self.assertEqual(r.returncode, 1, (key, value))
        self.assertEqual(self.run_script('get', 'lang').stdout, '')

    def test_small_device_is_refused(self):
        self.dev.write_bytes(bytes(8 * 1024 * 1024))
        self.assertEqual(self.run_script('set', 'lang', 'tr').returncode, 1)


if __name__ == '__main__':
    unittest.main()
