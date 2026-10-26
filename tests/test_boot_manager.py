import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BootManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.blocks = self.root / 'sys/class/block'
        self.blocks.mkdir(parents=True)
        self.hardware = self.root / 'hardware'
        self.hardware.mkdir()
        self.add_disk('mmcblk7', 'MMC')
        # Deliberately use different names, numbers and order than the phone.
        self.add_partition('mmcblk7p2', 'SYSTEM', 6291456, '259:42')
        self.add_partition('mmcblk7p9', 'RECOVERY', 77824, '259:49')
        self.add_partition('mmcblk7p3', 'BOOT', 65536, '259:43')
        self.add_partition('mmcblk7p8', 'USERDATA', 23314432, '259:48')
        self.calls = self.root / 'calls.jsonl'
        self.candidate = self.root / 'candidate'
        self.candidate.mkdir()
        (self.root / 'tmp').mkdir()
        (self.root / 'dev').mkdir()
        self.wrapper = self.root / 'busybox'
        self.wrapper.write_text('''#!/usr/bin/env python3
import json, os, pathlib, shutil, sys
args=sys.argv[1:]
with open(os.environ['LOADER_TEST_CALLS'],'a') as log:
    log.write(json.dumps(args)+'\\n')
if args[0]=='mknod':
    pathlib.Path(args[1]).touch()
elif args[0]=='mount':
    if os.environ.get('LOADER_TEST_MOUNT_FAIL'):
        sys.exit(1)
    shutil.copytree(os.environ['LOADER_TEST_CANDIDATE'],args[-1],dirs_exist_ok=True,symlinks=True)
elif args[0]=='umount':
    for item in pathlib.Path(args[1]).iterdir():
        if item.is_dir() and not item.is_symlink(): shutil.rmtree(item)
        else: item.unlink()
else:
    os.execvp(args[0],args)
''')
        self.wrapper.chmod(0o755)

    def add_disk(self, name, kind):
        disk = self.hardware / name
        (disk / 'device').mkdir(parents=True)
        (disk / 'device/type').write_text(kind + '\n')
        (disk / 'removable').write_text('0\n')
        (self.blocks / name).symlink_to(disk)

    def add_partition(self, name, label, sectors, numbers):
        disk_name = name.rsplit('p', 1)[0]
        part = self.hardware / disk_name / name
        part.mkdir()
        (part / 'partition').write_text(name.rsplit('p', 1)[1] + '\n')
        (part / 'size').write_text(str(sectors) + '\n')
        (part / 'dev').write_text(numbers + '\n')
        (part / 'uevent').write_text(f'DEVNAME={name}\nPARTNAME={label}\n')
        (self.blocks / name).symlink_to(part)

    def prepare_candidate(self):
        for name in ('etc', 'bin', 'sbin'):
            (self.candidate / name).mkdir()
        (self.candidate / 'etc/j701f-root').write_text('J701F_ALPINE_ROOT_V1\n')
        elf = bytearray(64)
        elf[:7] = b'\x7fELF\x02\x01\x01'
        struct.pack_into('<HH', elf, 16, 3, 183)
        (self.candidate / 'bin/busybox').write_bytes(elf)
        (self.candidate / 'bin/busybox').chmod(0o755)
        (self.candidate / 'sbin/init').symlink_to('/bin/busybox')

    def run_loader(self, action='inspect', mount_fail=False):
        script = (ROOT / 'ramdisk/bin/boot-manager').read_text()
        script = script.replace('bb=/bin/busybox', 'bb=' + shlex.quote(str(self.wrapper)))
        script = script.replace('blocks=/sys/class/block', 'blocks=' + shlex.quote(str(self.blocks)))
        script = script.replace('/tmp/j701f-', str(self.root / 'tmp/j701f-'))
        script = script.replace('/dev/j701f-', str(self.root / 'dev/j701f-'))
        env = dict(os.environ, LOADER_TEST_CALLS=str(self.calls),
                   LOADER_TEST_CANDIDATE=str(self.candidate))
        if mount_fail:
            env['LOADER_TEST_MOUNT_FAIL'] = 'yes'
        result = subprocess.run(['/bin/sh', '-c', script, 'boot-manager', action],
                                text=True, capture_output=True, env=env, timeout=10)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_discovers_by_identity_without_block_io(self):
        result, calls = self.run_loader()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SYSTEM: /dev/mmcblk7p2 (259:42)', result.stdout)
        self.assertIn('USERDATA: /dev/mmcblk7p8 (259:48)', result.stdout)
        self.assertFalse(any(c[0] in ('mount', 'mknod', 'dd', 'blkid') for c in calls))

    def test_sd_card_not_selected_even_if_removable_reports_zero(self):
        self.add_disk('mmcblk8', 'SD')
        self.add_partition('mmcblk8p1', 'USERDATA', 23314432, '179:33')
        result, calls = self.run_loader('check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not on internal MMC', result.stderr)
        self.assertFalse(any(c[0] == 'mount' for c in calls))

    def test_ambiguous_data_refused_before_mount(self):
        self.add_partition('mmcblk7p10', 'USERDATA', 23314432, '259:50')
        result, calls = self.run_loader('check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Ambiguous USERDATA', result.stderr)
        self.assertFalse(any(c[0] == 'mount' for c in calls))

    def test_wrong_capacity_and_missing_partition_refused(self):
        part = self.hardware / 'mmcblk7/mmcblk7p2'
        (part / 'size').write_text('6291455\n')
        result, _ = self.run_loader()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('capacity differs', result.stderr)
        (self.blocks / 'mmcblk7p2').unlink()
        result, _ = self.run_loader()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('partitions are missing', result.stderr)

    def test_check_uses_live_device_numbers_and_readonly_no_replay(self):
        self.prepare_candidate()
        result, calls = self.run_loader('check')
        self.assertEqual(result.returncode, 0, result.stderr)
        nodes = [c for c in calls if c[0] == 'mknod']
        self.assertEqual(nodes[0][-3:], ['b', '259', '48'])
        mount = next(c for c in calls if c[0] == 'mount')
        self.assertEqual(mount[1:5], ['-t', 'ext4', '-o', 'ro,noload,nosuid,nodev,noexec'])
        self.assertTrue(any(c[0] == 'umount' for c in calls))
        self.assertEqual(list((self.root / 'tmp').iterdir()), [])
        self.assertIn('does not execute this root', result.stdout)

    def test_android_root_rejected_and_unmounted(self):
        for name in ('etc', 'bin', 'sbin'):
            (self.candidate / name).mkdir()
        result, calls = self.run_loader('check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('marker missing', result.stderr)
        self.assertTrue(any(c[0] == 'umount' for c in calls))
        self.assertEqual(list((self.root / 'tmp').iterdir()), [])

    def test_mount_failure_cleans_ram_without_attempted_unmount(self):
        result, calls = self.run_loader('check', mount_fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0] == 'umount' for c in calls))
        self.assertEqual(list((self.root / 'tmp').iterdir()), [])

    def test_foreign_init_and_architecture_refused(self):
        self.prepare_candidate()
        init = self.candidate / 'sbin/init'
        init.unlink(); init.symlink_to('/init')
        result, _ = self.run_loader('check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unsupported init link', result.stderr)
        init.unlink(); init.symlink_to('/bin/busybox')
        binary = self.candidate / 'bin/busybox'
        elf = bytearray(binary.read_bytes()); struct.pack_into('<H', elf, 18, 62)
        binary.write_bytes(elf)
        result, _ = self.run_loader('check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not an AArch64 executable', result.stderr)

    def test_symlinked_root_directories_refused(self):
        self.prepare_candidate()
        shutil.rmtree(self.candidate / 'etc')
        (self.candidate / 'etc').symlink_to('/etc')
        result, calls = self.run_loader('check')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('invalid /etc', result.stderr)
        self.assertTrue(any(c[0] == 'umount' for c in calls))

    def test_boot_disabled_before_discovery(self):
        result, calls = self.run_loader('boot')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('handoff is not enabled', result.stderr)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
