"""scripts/install-release-on-recovery.sh against a simulated phone.

Written by Claude 2026-10-27 while finishing Codex's installer. The script runs
under qemu-aarch64 with the project's static BusyBox (the one in the recovery);
its absolute paths are prefixed with a temporary root (J701F_INSTALLER_TEST).
"""
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/install-release-on-recovery.sh'
BUSYBOX = ROOT / 'ramdisk/bin/busybox'
QEMU = shutil.which('qemu-aarch64') or shutil.which('qemu-aarch64-static')
UUID = '4ce26b55-8a59-4fb7-aad4-919a5c2cefeb'
SIZE = 4 << 20


@unittest.skipUnless(QEMU and BUSYBOX.is_file() and shutil.which('mke2fs'),
                     'qemu-aarch64, the static BusyBox (make busybox) and mke2fs are required')
class InstallReleaseOnRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-irr-')
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        cls.images = {}
        for uuid in (UUID, '11111111-2222-3333-4444-555555555555'):
            image = base / f'{uuid}.ext4'
            subprocess.run(['mke2fs', '-q', '-F', '-t', 'ext4', '-U', uuid, str(image), str(SIZE // 1024)],
                           check=True)
            cls.images[uuid] = image.read_bytes()
        cls.bb = base / 'bb'
        cls.bb.write_text(f'#!/bin/sh\nexec {QEMU} {BUSYBOX} "$@"\n')
        cls.bb.chmod(0o755)

    def phone(self, *, image_uuid=UUID, boot_mark=True, sd_type='SD', userdata_mounted=False,
              gz_hash=None, raw_hash=None, sectors=SIZE // 512):
        r = Path(tempfile.mkdtemp(dir=self.tmp.name))
        for d in ('dev', 'proc/self', 'proc/device-tree', 'sys/class/block/mmcblk0p24',
                  'sys/class/block/mmcblk0p10', 'sys/class/block/mmcblk2/device', 'mnt/sd/j701f-release'):
            (r / d).mkdir(parents=True)
        (r / 'dev/mmcblk0p24').write_bytes(b'\xa5' * SIZE)
        (r / 'dev/mmcblk0p10').write_bytes(b'\0' * 64 + (b'bootcmd=j701f_ramboot' if boot_mark else b'android') + b'\0')
        (r / 'sys/class/block/mmcblk0p24/uevent').write_text('MAJOR=179\nMINOR=24\nPARTNAME=USERDATA\n')
        (r / 'sys/class/block/mmcblk0p24/size').write_text(f'{sectors}\n')
        (r / 'sys/class/block/mmcblk0p24/dev').write_text('179:24\n')
        (r / 'sys/class/block/mmcblk0p10/uevent').write_text('MAJOR=179\nMINOR=10\nPARTNAME=BOOT\n')
        (r / 'sys/class/block/mmcblk2/device/type').write_text(sd_type + '\n')
        (r / 'proc/device-tree/compatible').write_bytes(b'samsung,j7velte\0samsung,exynos7870\0')
        (r / 'proc/mounts').write_text(f'/dev/mmcblk2p1 {r}/mnt/sd vfat rw 0 0\n')
        info = '25 1 179:33 / /mnt/sd rw - vfat /dev/mmcblk2p1 rw\n'
        if userdata_mounted:
            info += '26 1 179:24 / /mnt/root ro - ext4 /dev/mmcblk0p24 ro\n'
        (r / 'proc/self/mountinfo').write_text(info)
        raw = self.images[image_uuid]
        gz = gzip.compress(raw, mtime=0)
        rel = r / 'mnt/sd/j701f-release'
        (rel / 'userdata.ext4.gz').write_bytes(gz)
        (rel / 'userdata.ext4.gz.sha256').write_text((gz_hash or hashlib.sha256(gz).hexdigest()) + '  userdata.ext4.gz\n')
        (rel / 'userdata.ext4.sha256').write_text((raw_hash or hashlib.sha256(raw).hexdigest()) + '  userdata.ext4\n')
        return r

    def run_script(self, r, *args, source=None):
        env = dict(os.environ, J701F_INSTALLER_TEST='1', T_ROOT=str(r), T_BB=str(self.bb),
                   T_SECTORS=str(SIZE // 512), T_BYTES=str(SIZE), T_UUID=UUID)
        result = subprocess.run([str(self.bb), 'sh', str(SCRIPT), '--source',
                                 str(source or r / 'mnt/sd/j701f-release'), *args],
                                env=env, capture_output=True, text=True, timeout=300)
        return result.returncode, result.stdout + result.stderr

    def untouched(self, r):
        return (r / 'dev/mmcblk0p24').read_bytes() == b'\xa5' * SIZE

    def test_dry_run_checks_everything_and_writes_nothing(self):
        r = self.phone()
        code, out = self.run_script(r, '--erase-userdata')
        self.assertEqual(code, 0, out)
        self.assertIn('DRY RUN ONLY', out)
        self.assertTrue(self.untouched(r))

    def test_execute_writes_reads_back_and_checks_the_uuid(self):
        r = self.phone()
        code, out = self.run_script(r, '--erase-userdata', '--execute')
        self.assertEqual(code, 0, out)
        self.assertIn('WRITTEN AND VERIFIED', out)
        self.assertEqual((r / 'dev/mmcblk0p24').read_bytes(), self.images[UUID])
        self.assertEqual((r / 'mnt/sd/j701f-release/install.status').read_text().strip(), 'PASS')

    def test_wrong_uuid_after_writing_is_reported_as_failure(self):
        other = '11111111-2222-3333-4444-555555555555'
        r = self.phone(image_uuid=other)
        code, out = self.run_script(r, '--erase-userdata', '--execute')
        self.assertNotEqual(code, 0)
        self.assertIn('installed filesystem UUID mismatch: ' + other, out)
        self.assertEqual((r / 'mnt/sd/j701f-release/install.status').read_text().strip(), 'FAIL')

    def test_refusals_before_any_write(self):
        cases = [
            ({}, ('--execute',), 'explicit --erase-userdata is required'),
            ({'boot_mark': False}, ('--erase-userdata', '--execute'), 'BOOT does not contain'),
            ({'sd_type': 'MMC'}, ('--erase-userdata', '--execute'), 'not on external SD'),
            ({'userdata_mounted': True}, ('--erase-userdata', '--execute'), 'USERDATA is mounted'),
            ({'gz_hash': '0' * 64}, ('--erase-userdata', '--execute'), 'compressed payload checksum mismatch'),
            ({'raw_hash': '0' * 64}, ('--erase-userdata', '--execute'), 'decompressed image checksum mismatch'),
            ({'sectors': SIZE // 512 + 8}, ('--erase-userdata', '--execute'), 'unexpected USERDATA sectors'),
        ]
        for kwargs, args, message in cases:
            with self.subTest(message):
                r = self.phone(**kwargs)
                code, out = self.run_script(r, *args)
                self.assertNotEqual(code, 0, out)
                self.assertIn(message, out)
                self.assertTrue(self.untouched(r), message)

    def test_source_that_resolves_outside_the_sd_card_is_refused(self):
        r = self.phone()
        outside = Path(tempfile.mkdtemp(dir=self.tmp.name))
        shutil.move(str(r / 'mnt/sd/j701f-release'), str(outside / 'release'))
        (r / 'mnt/sd/j701f-release').symlink_to(outside / 'release')
        code, out = self.run_script(r, '--erase-userdata', '--execute')
        self.assertNotEqual(code, 0)
        self.assertIn('release must be staged on external SD', out)
        self.assertTrue(self.untouched(r))


if __name__ == '__main__':
    unittest.main()
