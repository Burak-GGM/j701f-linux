# Written by Claude 2026-10-10. recovery/scripts/backup.sh on temporary
# directories only.
import glob, os, pathlib, subprocess, tempfile, unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / 'recovery/scripts/backup.sh'


class Backup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.tmp.name)
        self.root, self.dest, self.scratch = d / 'root', d / 'dest', d / 'scratch'
        (self.root / 'etc').mkdir(parents=True)
        (self.root / 'home/burak-alpine/.config/app').mkdir(parents=True)
        (self.root / 'etc/hostname').write_text('phone\n')
        (self.root / 'home/burak-alpine/.config/app/settings').write_bytes(os.urandom(5000))
        (self.root / 'secret').write_text('not selected\n')
        self.dest.mkdir()
        self.scratch.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *a):
        return subprocess.run(['sh', str(SCRIPT), *map(str, a)], capture_output=True, text=True)

    def archive(self):
        (a,) = glob.glob(str(self.dest / '*.tar.gz'))
        return a

    def test_create_verify_restore_round_trip(self):
        r = self.run_script('create', self.root, self.dest)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('skipping missing home/burak-alpine/.local/share', r.stdout)
        a = self.archive()
        self.assertEqual(self.run_script('verify', a).returncode, 0)
        self.assertEqual(self.run_script('restore', a, self.scratch).returncode, 0)
        self.assertEqual((self.scratch / 'etc/hostname').read_text(), 'phone\n')
        self.assertEqual((self.scratch / 'home/burak-alpine/.config/app/settings').read_bytes(),
                         (self.root / 'home/burak-alpine/.config/app/settings').read_bytes())
        self.assertFalse((self.scratch / 'secret').exists())
        self.assertFalse(glob.glob(str(self.dest / '*.part')))

    def test_restore_refuses_non_empty_target(self):
        self.run_script('create', self.root, self.dest)
        (self.scratch / 'existing').write_text('keep me\n')
        r = self.run_script('restore', self.archive(), self.scratch)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(sorted(os.listdir(self.scratch)), ['existing'])

    def test_damaged_archive_is_detected(self):
        self.run_script('create', self.root, self.dest)
        a = self.archive()
        with open(a, 'r+b') as f:
            f.seek(100)
            f.write(b'\x00\x00\x00\x00')
        self.assertEqual(self.run_script('verify', a).returncode, 1)
        self.assertEqual(self.run_script('restore', a, self.scratch).returncode, 1)
        self.assertEqual(os.listdir(self.scratch), [])

    def test_bad_paths_and_arguments_are_refused(self):
        for bad in ('/etc', '../outside', 'etc/../../x'):
            self.assertEqual(self.run_script('create', self.root, self.dest, bad).returncode, 1, bad)
        self.assertEqual(self.run_script('create', self.root, self.dest, 'nothing-here').returncode, 1)
        self.assertEqual(self.run_script('create', self.root / 'absent', self.dest).returncode, 1)
        self.assertEqual(self.run_script('wipe').returncode, 2)
        self.assertEqual(os.listdir(self.dest), [])

    # recovery/scripts/storage.sh with directories standing in for the mounts
    def storage(self, *a, **env):
        e = {**os.environ, 'J701F_RECOVERY_ROOT': str(self.root), 'J701F_RECOVERY_SD': str(self.dest), **env}
        return subprocess.run(['sh', str(SCRIPT.with_name('storage.sh')), *a], capture_output=True, text=True, env=e)

    def test_storage_backup_then_verify(self):
        r = self.storage('backup')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('CREATED', r.stdout)
        self.assertEqual(len(glob.glob(str(self.dest / 'j701f-backups/*.tar.gz'))), 1)
        r = self.storage('verify')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('VERIFIED', r.stdout)

    def test_storage_verify_without_backup_is_refused(self):
        r = self.storage('verify')
        self.assertEqual(r.returncode, 1)
        self.assertIn('no backup found', r.stdout)

    def test_storage_missing_sd_is_refused_and_root_untouched(self):
        before = sorted(str(p) for p in self.root.rglob('*'))
        r = self.storage('backup', J701F_RECOVERY_SD=str(self.dest / 'absent'))
        self.assertEqual(r.returncode, 1)
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob('*')))

    def test_storage_check_is_read_only(self):
        img = pathlib.Path(self.tmp.name) / 'fs.img'
        subprocess.run(['truncate', '-s', '8M', str(img)], check=True)
        subprocess.run(['mke2fs', '-q', '-t', 'ext4', str(img)], check=True)
        before = img.read_bytes()
        r = self.storage('check', J701F_RECOVERY_CHECK_DEV=str(img))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('CHECK finished', r.stdout)
        self.assertEqual(before, img.read_bytes())

    def test_storage_copy_never_overwrites(self):
        src = self.root / 'etc/hostname'
        r = self.storage('copy', str(src))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.dest / 'j701f-files/hostname').read_text(), 'phone\n')
        r = self.storage('copy', str(src))
        self.assertEqual(r.returncode, 1)
        self.assertIn('already there', r.stdout)


if __name__ == '__main__':
    unittest.main()
