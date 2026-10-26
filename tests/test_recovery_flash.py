# Written by Claude 2026-10-10. recovery/scripts/flash-boot.sh against image
# files only: the script is never pointed at a real device here.
import hashlib, os, pathlib, subprocess, tempfile, unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'recovery/scripts/flash-boot.sh'
SLOT = 1024 * 1024


def sha(b):
    return hashlib.sha256(b).hexdigest()


class FlashBoot(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.dir.name)
        self.slot = d / 'slot.img'
        self.old = os.urandom(SLOT)
        self.slot.write_bytes(self.old)
        self.state = d / 'state'
        self.good = d / 'good.img'
        self.good_bytes = b'ANDROID!' + os.urandom(300000)
        self.good.write_bytes(self.good_bytes)
        self.env = dict(os.environ, J701F_RECOVERY_TARGET=str(self.slot), J701F_RECOVERY_STATE=str(self.state))

    def tearDown(self):
        self.dir.cleanup()

    def run_script(self, *args):
        return subprocess.run(['sh', str(SCRIPT), *args], env=self.env, capture_output=True, text=True)

    def test_write_keeps_previous_and_verifies(self):
        r = self.run_script('write', str(self.good), sha(self.good_bytes))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('WRITTEN AND VERIFIED', r.stdout)
        now = self.slot.read_bytes()
        self.assertEqual(len(now), SLOT)
        self.assertEqual(now[:len(self.good_bytes)], self.good_bytes)
        self.assertEqual(now[len(self.good_bytes):], self.old[len(self.good_bytes):])
        self.assertEqual((self.state / 'boot-previous.img').read_bytes(), self.old)
        self.assertIn(sha(self.good_bytes), (self.state / 'boot-slot.txt').read_text())

    def test_rollback_restores_exact_contents(self):
        self.assertEqual(self.run_script('write', str(self.good)).returncode, 0)
        r = self.run_script('rollback')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.slot.read_bytes(), self.old)

    def test_rollback_without_previous_is_refused(self):
        r = self.run_script('rollback')
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.slot.read_bytes(), self.old)

    def refused(self, path, *extra):
        r = self.run_script('write', str(path), *extra)
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('REFUSED', r.stdout)
        self.assertEqual(self.slot.read_bytes(), self.old)
        self.assertFalse((self.state / 'boot-previous.img').exists())

    def test_wrong_header_is_refused(self):
        bad = pathlib.Path(self.dir.name) / 'bad.img'
        bad.write_bytes(b'NOTABOOT' + os.urandom(10000))
        self.refused(bad)

    def test_too_large_is_refused(self):
        big = pathlib.Path(self.dir.name) / 'big.img'
        big.write_bytes(b'ANDROID!' + os.urandom(SLOT))
        self.refused(big)

    def test_too_small_and_missing_are_refused(self):
        tiny = pathlib.Path(self.dir.name) / 'tiny.img'
        tiny.write_bytes(b'ANDROID!')
        self.refused(tiny)
        self.refused(pathlib.Path(self.dir.name) / 'absent.img')

    def test_wrong_hash_is_refused(self):
        self.refused(self.good, '0' * 64)

    def test_info_and_usage(self):
        r = self.run_script('info')
        self.assertEqual(r.returncode, 0)
        self.assertIn(sha(self.old), r.stdout)
        self.assertEqual(self.run_script('format').returncode, 2)
        self.assertEqual(self.slot.read_bytes(), self.old)


if __name__ == '__main__':
    unittest.main()
