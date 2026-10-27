"""The TWRP/OrangeFox release ZIP, run against a fake phone on the host.

Written by Claude 2026-10-27. installer.sh runs under qemu-aarch64 with the very
BusyBox the ZIP ships; partitions, /proc, /sys and the volume keys are files.
"""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUSYBOX = ROOT / 'ramdisk/bin/busybox'
QEMU = shutil.which('qemu-aarch64') or shutil.which('qemu-aarch64-static')
UUID = '4ce26b55-8a59-4fb7-aad4-919a5c2cefeb'
SIZE = 4 << 20
KEY_UP, KEY_DOWN = 115, 114
SHM = Path('/dev/shm')


def key_event(code):
    return struct.pack('<qqHHi', 0, 0, 1, code, 1)  # 64-bit struct input_event, EV_KEY press


@unittest.skipUnless(QEMU and BUSYBOX.is_file() and shutil.which('mke2fs'),
                     'qemu-aarch64, the static BusyBox (make busybox) and mke2fs are required')
class RecoveryZipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-zip-')
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name)
        image = base / 'userdata.ext4'
        subprocess.run(['mke2fs', '-q', '-F', '-t', 'ext4', '-U', UUID, '-E', 'root_owner=0:0',
                        str(image), str(SIZE // 1024)], check=True)
        cls.raw = image.read_bytes()
        cls.gz = gzip.compress(cls.raw, mtime=0)
        cls.bb = base / 'bb'
        cls.bb.write_text(f'#!/bin/sh\nexec {QEMU} {BUSYBOX} "$@"\n')
        cls.bb.chmod(0o755)

    def phone(self, *, bootloader='J701FXXU7CUH1', boot_mark=True, sectors=SIZE // 512,
              key=KEY_UP, gz_hash=None, raw_hash=None, embed=False, zip_on_userdata=False,
              json_uuid=UUID, sd_type='SD', zip_link_to_internal=False, userdata_mounted=False):
        d = Path(tempfile.mkdtemp(dir=self.tmp.name))
        (d / 'dev').mkdir(); (d / 'byname').mkdir(); (d / 'sys/mmcblk0p24').mkdir(parents=True)
        (d / 'proc/self').mkdir(parents=True); (d / 'input').mkdir(); (d / 'sd').mkdir()
        userdata = d / 'dev/mmcblk0p24'
        userdata.write_bytes(b'\xa5' * SIZE)
        (d / 'byname/USERDATA').symlink_to(userdata)
        (d / 'dev/boot').write_bytes(b'\0' * 4096 + (b'bootcmd=j701f_ramboot\0' if boot_mark else b'android\0'))
        (d / 'byname/BOOT').symlink_to(d / 'dev/boot')
        (d / 'sys/mmcblk0p24/uevent').write_text('MAJOR=179\nMINOR=24\nPARTN=24\nPARTNAME=USERDATA\n')
        (d / 'sys/mmcblk0p24/size').write_text(f'{sectors}\n')
        (d / 'sys/mmcblk0p24/dev').write_text('179:24\n')
        # /sys/dev/block: the SD card's filesystem is the temporary directory's;
        # "internal storage" (/dev/shm, another filesystem) is the eMMC.
        sysdev = d / 'sysdev'; sysdev.mkdir()
        for path, kind, disk in ((d / 'sd', sd_type, 'mmcblk1'), (SHM, 'MMC', 'mmcblk0')):
            st = os.stat(path)
            part = d / 'devices' / disk / (disk + 'p1')
            part.mkdir(parents=True, exist_ok=True)
            (part / 'partition').write_text('1\n')
            (d / 'devices' / disk / 'device').mkdir(exist_ok=True)
            (d / 'devices' / disk / 'device/type').write_text(kind + '\n')
            (sysdev / f'{os.major(st.st_dev)}:{os.minor(st.st_dev)}').symlink_to(part)
        (d / 'proc/cmdline').write_text(f'console=ram androidboot.bootloader={bootloader} androidboot.mode=recovery\n')
        info = '22 1 0:20 / /tmp rw - tmpfs tmpfs rw\n'
        if userdata_mounted:
            info += f'30 1 179:24 / {d / "not-a-mount"} rw - ext4 /dev/block/mmcblk0p24 rw\n'
        (d / 'proc/self/mountinfo').write_text(info)
        if key is not None:
            (d / 'input/event0').write_bytes(key_event(key))
        else:
            (d / 'input/event0').write_bytes(b'')
        release = {
            'userdata.ext4.gz': self.gz,
            'userdata.ext4.gz.sha256': (gz_hash or hashlib.sha256(self.gz).hexdigest()) + '  userdata.ext4.gz\n',
            'userdata.ext4.sha256': (raw_hash or hashlib.sha256(self.raw).hexdigest()) + '  userdata.ext4\n',
            'release.json': json.dumps({
                'device': 'SM-J701F / samsung,j7velte', 'partition': 'USERDATA',
                'sectors': SIZE // 512, 'bytes': SIZE, 'filesystem_uuid': json_uuid,
                'root_version': 'TEST_0_1'}, indent=2) + '\n',
        }
        zpath = d / 'sd/j701f-install.zip'
        internal = None
        if zip_on_userdata or zip_link_to_internal:
            internal = Path(tempfile.mkdtemp(dir=SHM, prefix='j701f-internal-'))
            self.addCleanup(shutil.rmtree, internal)
        cmd = ['python3', str(ROOT / 'tools/build-recovery-zip.py'), str(zpath)]
        if embed:
            rel = d / 'staging'
            rel.mkdir()
            for name, data in release.items():
                (rel / name).write_bytes(data if isinstance(data, bytes) else data.encode())
            cmd += ['--embed', str(rel)]
        else:
            rel = d / 'sd/j701f-release'
            rel.mkdir()
            for name, data in release.items():
                (rel / name).write_bytes(data if isinstance(data, bytes) else data.encode())
        if internal:
            cmd[2] = str(internal / 'j701f-install.zip')
        subprocess.run(cmd, check=True, capture_output=True)
        if zip_link_to_internal:
            zpath.symlink_to(internal / 'j701f-install.zip')
        elif zip_on_userdata:
            zpath = internal / 'j701f-install.zip'
            if not embed:
                shutil.move(str(d / 'sd/j701f-release'), str(internal / 'j701f-release'))
        self.last_env = None
        work = d / 'work'
        with zipfile.ZipFile(zpath) as z:
            z.extractall(work, [n for n in z.namelist() if n.startswith('j701f/')])
        env = dict(os.environ, BB=str(self.bb), J701F_INSTALLER_TEST='1',
                   T_UUID=UUID, T_SECTORS=str(SIZE // 512), T_BYTES=str(SIZE),
                   T_BYNAME=str(d / 'byname'), T_SYS=str(d / 'sys'), T_PROC=str(d / 'proc'),
                   T_INPUT=str(d / 'input'), T_KEY_TIMEOUT='3', T_SYSDEV=str(sysdev))
        self.runs = getattr(self, 'runs', {})
        self.runs[d] = (env, work, zpath)
        result = subprocess.run([str(self.bb), 'sh', str(work / 'j701f/installer.sh'), '1', str(zpath)],
                                env=env, capture_output=True, text=True, timeout=300)
        ui = '\n'.join(l[9:] for l in result.stdout.splitlines() if l.startswith('ui_print '))
        return result.returncode, ui, userdata.read_bytes(), d

    def rerun(self, d):
        env, work, zpath = self.runs[d]
        env = dict(env, T_KEY_TIMEOUT='3')
        (d / 'input/event0').write_bytes(key_event(KEY_UP))
        result = subprocess.run([str(self.bb), 'sh', str(work / 'j701f/installer.sh'), '1', str(zpath)],
                                env=env, capture_output=True, text=True, timeout=300)
        return result.returncode, '\n'.join(l[9:] for l in result.stdout.splitlines() if l.startswith('ui_print '))

    def assert_untouched(self, data):
        self.assertEqual(data, b'\xa5' * SIZE)

    def test_installs_release_next_to_zip_and_verifies(self):
        code, ui, data, d = self.phone()
        self.assertEqual(code, 0, ui)
        self.assertEqual(data, self.raw)
        self.assertIn('DONE: USERDATA written and verified', ui)
        self.assertIn('Version: TEST_0_1', ui)
        self.assertTrue((d / 'sd/j701f-release/install.status').read_text().startswith('PASS'))

    def test_installs_release_embedded_in_zip(self):
        code, ui, data, d = self.phone(embed=True)
        self.assertEqual(code, 0, ui)
        self.assertEqual(data, self.raw)
        self.assertIn('Release: inside the ZIP', ui)
        self.assertTrue((d / 'sd/j701f-install.status').read_text().startswith('PASS'))

    def test_volume_down_cancels(self):
        code, ui, data, _ = self.phone(key=KEY_DOWN)
        self.assertNotEqual(code, 0)
        self.assertIn('cancelled', ui)
        self.assert_untouched(data)

    def test_no_key_times_out_and_cancels(self):
        code, ui, data, _ = self.phone(key=None)
        self.assertNotEqual(code, 0)
        self.assertIn('cancelled', ui)
        self.assert_untouched(data)

    def test_other_phone_refused(self):
        code, ui, data, _ = self.phone(bootloader='J710FXXU1')
        self.assertNotEqual(code, 0)
        self.assertIn('not an SM-J701F', ui)
        self.assert_untouched(data)

    def test_boot_without_linux_loader_refused(self):
        code, ui, data, _ = self.phone(boot_mark=False)
        self.assertNotEqual(code, 0)
        self.assertIn('BOOT does not hold the J701F Linux loader', ui)
        self.assert_untouched(data)

    def test_wrong_partition_size_refused(self):
        code, ui, data, _ = self.phone(sectors=SIZE // 512 + 8)
        self.assertNotEqual(code, 0)
        self.assertIn('sectors', ui)
        self.assert_untouched(data)

    def test_damaged_payload_refused_before_writing(self):
        code, ui, data, _ = self.phone(gz_hash='0' * 64)
        self.assertNotEqual(code, 0)
        self.assertIn('checksum mismatch', ui)
        self.assert_untouched(data)

    def test_zip_on_internal_storage_refused(self):
        code, ui, data, _ = self.phone(zip_on_userdata=True)
        self.assertNotEqual(code, 0)
        self.assertIn('the ZIP is not on the SD card', ui)
        self.assert_untouched(data)

    def test_zip_symlinked_from_sd_to_internal_storage_refused(self):
        code, ui, data, _ = self.phone(zip_link_to_internal=True, embed=True)
        self.assertNotEqual(code, 0)
        self.assertIn('the ZIP is not on the SD card', ui)
        self.assert_untouched(data)

    def test_release_file_linked_to_internal_storage_refused(self):
        code, ui, data, d = self.phone(key=None, sd_type='SD')
        # Rebuild the case: the payload in j701f-release/ is a link into internal storage.
        internal = Path(tempfile.mkdtemp(dir=SHM, prefix='j701f-internal-'))
        self.addCleanup(shutil.rmtree, internal)
        rel = d / 'sd/j701f-release'
        shutil.move(str(rel / 'userdata.ext4.gz'), str(internal / 'userdata.ext4.gz'))
        (rel / 'userdata.ext4.gz').symlink_to(internal / 'userdata.ext4.gz')
        code, ui = self.rerun(d)
        self.assertNotEqual(code, 0)
        self.assertIn('userdata.ext4.gz is not on the SD card', ui)
        self.assert_untouched((d / 'dev/mmcblk0p24').read_bytes())

    def test_storage_that_is_not_an_sd_card_refused(self):
        code, ui, data, _ = self.phone(sd_type='MMC')
        self.assertNotEqual(code, 0)
        self.assertIn('not on the SD card', ui)
        self.assert_untouched(data)

    def test_userdata_mount_found_by_major_minor_must_be_unmounted(self):
        code, ui, data, _ = self.phone(userdata_mounted=True)
        self.assertNotEqual(code, 0)
        self.assertIn('cannot unmount', ui)
        self.assert_untouched(data)

    def test_read_back_mismatch_reported_as_failure(self):
        code, ui, data, d = self.phone(raw_hash='1' * 64)
        self.assertNotEqual(code, 0)
        self.assertIn('read-back SHA-256 does not match', ui)
        self.assertTrue((d / 'sd/j701f-release/install.status').read_text().startswith('FAIL'))

    def test_release_for_another_filesystem_refused(self):
        code, ui, data, _ = self.phone(json_uuid='00000000-0000-0000-0000-000000000000')
        self.assertNotEqual(code, 0)
        self.assertIn('another filesystem UUID', ui)
        self.assert_untouched(data)

    def test_update_binary_and_installer_parse(self):
        for script in ('update-binary', 'installer.sh'):
            subprocess.run([str(self.bb), 'sh', '-n', str(ROOT / 'recovery/installer' / script)], check=True)


if __name__ == '__main__':
    unittest.main()
