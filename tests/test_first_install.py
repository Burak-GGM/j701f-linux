"""Host-only unit and adversarial tests for tools/prepare-first-install.py."""
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import recovery  # noqa: E402


def load_tool(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


first_install = load_tool('prepare_first_install_test', 'prepare-first-install.py')
stub_tool = load_tool('prepare_sboot_stub_test', 'prepare-sboot-stub.py')


def _align4(n):
    return (n + 3) // 4 * 4


def build_minimal_fdt(prop_map, min_size=0):
    """Build a valid FDT v17 blob whose flat path->bytes properties match prop_map."""
    strings = bytearray()
    str_offsets = {}

    def name_off(name):
        if name not in str_offsets:
            str_offsets[name] = len(strings)
            strings.extend(name.encode('ascii') + b'\0')
        return str_offsets[name]

    tree = {'_props': {}, '_children': {}}
    for full_key, val in prop_map.items():
        parts = [p for p in full_key.split('/') if p]
        prop_name = parts[-1]
        node = tree
        for seg in parts[:-1]:
            node = node['_children'].setdefault(seg, {'_props': {}, '_children': {}})
        node['_props'][prop_name] = val

    struct_buf = bytearray()

    def emit_node(name, node):
        struct_buf.extend(struct.pack('>I', 1))
        raw_name = name.encode('ascii') + b'\0'
        struct_buf.extend(raw_name + bytes(_align4(len(raw_name)) - len(raw_name)))
        for k, v in node['_props'].items():
            struct_buf.extend(struct.pack('>3I', 3, len(v), name_off(k)))
            struct_buf.extend(v + bytes(_align4(len(v)) - len(v)))
        for child_name, child in node['_children'].items():
            emit_node(child_name, child)
        struct_buf.extend(struct.pack('>I', 2))

    emit_node('', tree)
    struct_buf.extend(struct.pack('>I', 9))

    header_len = 40
    rsvmap = bytes(16)
    off_rsvmap = header_len
    off_struct = off_rsvmap + len(rsvmap)
    if min_size > off_struct + len(struct_buf) + len(strings):
        nop_words = (min_size - (off_struct + len(struct_buf) + len(strings)) + 3) // 4
        struct_buf = struct.pack(f'>{nop_words}I', *([4] * nop_words)) + struct_buf
    off_strings = off_struct + len(struct_buf)
    total_size = off_strings + len(strings)
    header = struct.pack('>10I', 0xd00dfeed, total_size, off_struct, off_strings,
                         off_rsvmap, 17, 16, 0, len(strings), len(struct_buf))
    return bytes(header + rsvmap + struct_buf + strings)


def build_synthetic_a64_elf(static_exec=True, machine=183):
    """Build a minimal 64-bit little-endian ELF with one PT_LOAD program header."""
    e_type = 2 if static_exec else 3  # ET_EXEC vs ET_DYN (static-pie)
    ehdr = bytearray(64)
    ehdr[0:6] = b'\x7fELF\x02\x01'
    ehdr[6] = 1
    struct.pack_into('<HHIQQQIHHHHHH', ehdr, 16,
                     e_type, machine, 1, 0x400000, 64, 0, 0, 64, 56, 1, 0, 0, 0)
    phdr = struct.pack('<IIQQQQQQ', 1, 5, 0, 0x400000, 0x400000, 120, 120, 0x1000)
    return bytes(ehdr + phdr)


def build_synthetic_stub_dtbh():
    dtb = build_minimal_fdt({'/compatible': b'samsung,exynos7870\0'})
    return stub_tool.pack_table([dtb, dtb, dtb])


def build_synthetic_initramfs(is_recovery=False, busybox_elf=None, ui_elf=None):
    busybox_elf = busybox_elf or build_synthetic_a64_elf(static_exec=True)
    ui_elf = ui_elf or build_synthetic_a64_elf(static_exec=False)
    items = [
        ('bin', stat.S_IFDIR | 0o755, b''),
        ('init', stat.S_IFREG | 0o755, b'#!/bin/sh\n'),
        ('bin/busybox', stat.S_IFREG | 0o755, busybox_elf),
        ('bin/alpine-handoff', stat.S_IFREG | 0o755, b'#!/bin/sh\n'),
        ('bin/muic-usb-path', stat.S_IFREG | 0o755, b'#!/bin/sh\n'),
        ('bin/usb-configfs', stat.S_IFREG | 0o755, b'#!/bin/sh\n'),
    ]
    if is_recovery:
        items.extend([
            ('recovery', stat.S_IFDIR | 0o755, b''),
            ('recovery/scripts', stat.S_IFDIR | 0o755, b''),
            ('bin/recovery-ui', stat.S_IFREG | 0o755, ui_elf),
            ('bin/recovery-main', stat.S_IFREG | 0o755, b'#!/bin/sh\n'),
            ('recovery/scripts/flash-boot.sh', stat.S_IFREG | 0o755, b'#!/bin/sh\n'),
            ('recovery/scripts/storage.sh', stat.S_IFREG | 0o755, b'#!/bin/sh\n'),
        ])
    raw = b''.join(recovery.cpio_record(name, data, mode, idx + 1)
                   for idx, (name, mode, data) in enumerate(items))
    raw += recovery.cpio_record('TRAILER!!!', b'', 0, len(items) + 1)
    raw += bytes(recovery.align(len(raw), 512) - len(raw))
    return gzip.compress(raw, mtime=0)


def build_synthetic_arm64_image(payload=b''):
    hdr = bytearray(64)
    struct.pack_into('<3Q', hdr, 8, 0, 0x200000, 0x0a)
    hdr[56:60] = b'ARM\x64'
    return bytes(hdr) + payload


def build_synthetic_mainline_image(is_recovery=False, dtbh=None, cmdline=b'buildvariant=eng',
                                   bootcmd=b'bootcmd=j701f_ramboot\0',
                                   pin_fit_sha=True, non_empty_ramdisk=b'',
                                   corrupt_fit_kernel_hash=False,
                                   board_compatible=b'samsung,j7velte\0'):
    kernel_raw = build_synthetic_arm64_image(b'\x00' * 128)
    kernel_gz = gzip.compress(kernel_raw, mtime=0)
    fdt_blob = build_minimal_fdt({'/compatible': board_compatible})
    initrd_gz = build_synthetic_initramfs(is_recovery=is_recovery)

    k_hash = hashlib.sha256(kernel_gz).digest()
    if corrupt_fit_kernel_hash:
        k_hash = bytes([k_hash[0] ^ 0xff]) + k_hash[1:]

    fit_props = {
        '/configurations/default': b'conf-j701f-diagnostic\0',
        '/configurations/conf-j701f-diagnostic/compatible': board_compatible,
        '/images/kernel/data': kernel_gz,
        '/images/kernel/type': b'kernel\0',
        '/images/kernel/arch': b'arm64\0',
        '/images/kernel/os': b'linux\0',
        '/images/kernel/compression': b'gzip\0',
        '/images/kernel/hash-1/algo': b'sha256\0',
        '/images/kernel/hash-1/value': k_hash,
        '/images/fdt/data': fdt_blob,
        '/images/fdt/type': b'flat_dt\0',
        '/images/fdt/arch': b'arm64\0',
        '/images/fdt/os': b'linux\0',
        '/images/fdt/compression': b'none\0',
        '/images/fdt/hash-1/algo': b'sha256\0',
        '/images/fdt/hash-1/value': hashlib.sha256(fdt_blob).digest(),
        '/images/initramfs/data': initrd_gz,
        '/images/initramfs/type': b'ramdisk\0',
        '/images/initramfs/arch': b'arm64\0',
        '/images/initramfs/os': b'linux\0',
        '/images/initramfs/compression': b'none\0',
        '/images/initramfs/hash-1/algo': b'sha256\0',
        '/images/initramfs/value': b'',
        '/images/initramfs/hash-1/value': hashlib.sha256(initrd_gz).digest(),
    }
    fit_blob = build_minimal_fdt(fit_props, min_size=65536)
    fit_sha = hashlib.sha256(fit_blob).digest() if pin_fit_sha else b'\x00' * 32

    prefix = bytearray(build_synthetic_arm64_image(b'stdin=nulldev\0' + bootcmd + fit_sha))
    while len(prefix) % 8 != 0 or len(prefix) < 128:
        prefix.append(0)
    loader = bytes(prefix) + fit_blob

    dtbh = dtbh or build_synthetic_stub_dtbh()
    parts = {
        'kernel': loader,
        'ramdisk': non_empty_ramdisk,
        'second': b'',
        'dt': dtbh,
    }
    page = 2048
    header = bytearray(page)
    header[0:8] = b'ANDROID!'
    struct.pack_into('<10I', header, 8,
                     len(parts['kernel']), 0x10008000,
                     len(parts['ramdisk']), 0x11000000,
                     len(parts['second']), 0x10f00000,
                     0x10000100, page,
                     len(parts['dt']), 0x2004063c)
    header[64:64 + len(cmdline)] = cmdline
    header[576:596] = recovery.Image.digest(parts)

    out = bytes(header)
    for name in ('kernel', 'ramdisk', 'second', 'dt'):
        data = parts[name]
        out += data + bytes(recovery.align(len(data), page) - len(data))
    out += b'SEANDROIDENFORCE'
    return out


class SyntheticFirstInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.stub_dtbh = build_synthetic_stub_dtbh()
        self.stub_sha = hashlib.sha256(self.stub_dtbh).hexdigest()
        patch = mock.patch.object(first_install, 'STUB_DTBH_SHA256', self.stub_sha)
        patch.start()
        self.addCleanup(patch.stop)
        orig_patch = mock.patch.object(first_install, 'ROOT', self.work)
        orig_patch.start()
        self.addCleanup(orig_patch.stop)

    def test_prepare_and_verify_synthetic_bundle_shows_custom_override_hashes(self):
        boot_img = self.work / 'src-boot.img'
        rec_img = self.work / 'src-recovery.img'
        out_dir = self.work / 'out'
        boot_bytes = build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh)
        rec_bytes = build_synthetic_mainline_image(is_recovery=True, dtbh=self.stub_dtbh)
        boot_img.write_bytes(boot_bytes)
        rec_img.write_bytes(rec_bytes)

        manifest = first_install.prepare_bundle(boot_img, rec_img, out_dir)
        self.assertEqual(manifest['status'], 'host-prepared')
        self.assertFalse(manifest['phone_modified'])
        self.assertFalse(manifest['odin_executed'])
        self.assertFalse(manifest['pinned_defaults_used'])
        self.assertFalse(manifest['boot']['pinned_default'])
        self.assertEqual(manifest['boot']['custom_override_sha256'], hashlib.sha256(boot_bytes).hexdigest())
        self.assertIsNone(manifest['boot']['pinned_expected_sha256'])
        self.assertFalse(manifest['recovery']['pinned_default'])
        self.assertEqual(manifest['recovery']['custom_override_sha256'], hashlib.sha256(rec_bytes).hexdigest())

        boot_tar = out_dir / 'BOOT-j701f-mainline.tar'
        rec_tar = out_dir / 'RECOVERY-j701f-mainline.tar'
        self.assertTrue(boot_tar.is_file())
        self.assertTrue(rec_tar.is_file())

        boot_info = first_install.verify_tar(boot_tar, 'boot')
        rec_info = first_install.verify_tar(rec_tar, 'recovery')
        self.assertEqual(boot_info['member_name'], 'boot.img')
        self.assertEqual(rec_info['member_name'], 'recovery.img')

    def test_failed_rebuild_removes_stale_manifest_and_outputs(self):
        boot_img = self.work / 'src-boot.img'
        rec_img = self.work / 'src-recovery.img'
        out_dir = self.work / 'out'
        boot_img.write_bytes(build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh))
        rec_img.write_bytes(build_synthetic_mainline_image(is_recovery=True, dtbh=self.stub_dtbh))

        first_install.prepare_bundle(boot_img, rec_img, out_dir)
        self.assertTrue((out_dir / 'manifest.json').exists())
        self.assertTrue((out_dir / 'SHA256SUMS').exists())

        # Now corrupt the recovery image and rerun into the same output directory.
        bad_rec = self.work / 'bad-recovery.img'
        bad_rec.write_bytes(build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh))
        with self.assertRaisesRegex(ValueError, 'RECOVERY image is missing bin/recovery-ui'):
            first_install.prepare_bundle(boot_img, bad_rec, out_dir)

        for name in first_install.PUBLISHED_FILES:
            self.assertFalse((out_dir / name).exists(), f'Stale output {name} remained after failed run')
        self.assertEqual(list(out_dir.glob('.first-install-staging-*')), [])

    def test_directory_collision_never_leaves_a_ready_looking_manifest(self):
        # Codex's review case: a valid earlier bundle, then recovery.img replaced by a
        # directory. The run must refuse, and must not leave the old manifest behind.
        boot_img = self.work / 'src-boot.img'
        rec_img = self.work / 'src-recovery.img'
        out_dir = self.work / 'out'
        boot_img.write_bytes(build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh))
        rec_img.write_bytes(build_synthetic_mainline_image(is_recovery=True, dtbh=self.stub_dtbh))
        first_install.prepare_bundle(boot_img, rec_img, out_dir)
        (out_dir / 'recovery.img').unlink()
        (out_dir / 'recovery.img').mkdir()

        with self.assertRaisesRegex(ValueError, 'not a regular file or symlink'):
            first_install.prepare_bundle(boot_img, rec_img, out_dir)
        self.assertFalse((out_dir / 'manifest.json').exists(), 'stale manifest still marks the bundle ready')
        self.assertTrue((out_dir / 'recovery.img').is_dir())
        self.assertEqual(list(out_dir.glob('.first-install-staging-*')), [])

    def test_default_paths_enforce_pinned_cam5_and_rec8_hashes(self):
        default_boot = self.work / 'default-boot.img'
        default_rec = self.work / 'default-rec.img'
        out_dir = self.work / 'out'
        boot_bytes = build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh)
        rec_bytes = build_synthetic_mainline_image(is_recovery=True, dtbh=self.stub_dtbh)
        default_boot.write_bytes(boot_bytes)
        default_rec.write_bytes(rec_bytes)

        with mock.patch.object(first_install, 'DEFAULT_BOOT', default_boot), \
             mock.patch.object(first_install, 'DEFAULT_RECOVERY', default_rec):
            with self.assertRaisesRegex(ValueError, 'Default cam5 BOOT image SHA-256 mismatch'):
                first_install.prepare_bundle(None, None, out_dir)

            with mock.patch.object(first_install, 'PINNED_BOOT_SHA256', hashlib.sha256(boot_bytes).hexdigest()):
                with self.assertRaisesRegex(ValueError, 'Default rec8 RECOVERY image SHA-256 mismatch'):
                    first_install.prepare_bundle(None, None, out_dir)

    def test_swapped_boot_and_recovery_roles_rejected(self):
        boot_bytes = build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh)
        rec_bytes = build_synthetic_mainline_image(is_recovery=True, dtbh=self.stub_dtbh)
        with self.assertRaisesRegex(ValueError, 'RECOVERY image is missing bin/recovery-ui'):
            first_install.verify_mainline_image(boot_bytes, 'recovery')
        with self.assertRaisesRegex(ValueError, 'BOOT image must not contain recovery-ui'):
            first_install.verify_mainline_image(rec_bytes, 'boot')

    def test_missing_ramboot_marker_rejected(self):
        bad = build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh,
                                             bootcmd=b'bootcmd=run distro_bootcmd\0')
        with self.assertRaisesRegex(ValueError, 'bootcmd=j701f_ramboot'):
            first_install.verify_mainline_image(bad, 'boot')

    def test_unpinned_or_corrupt_fit_rejected(self):
        unpinned = build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh,
                                                  pin_fit_sha=False)
        with self.assertRaisesRegex(ValueError, 'not pinned in the loader'):
            first_install.verify_mainline_image(unpinned, 'boot')

        corrupt_hash = build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh,
                                                      corrupt_fit_kernel_hash=True)
        with self.assertRaisesRegex(ValueError, 'FIT kernel SHA-256 mismatch'):
            first_install.verify_mainline_image(corrupt_hash, 'boot')

    def test_wrong_board_compatible_rejected(self):
        wrong_board = build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh,
                                                     board_compatible=b'samsung,on7xelte\0')
        with self.assertRaisesRegex(ValueError, 'samsung,j7velte'):
            first_install.verify_mainline_image(wrong_board, 'boot')

    def test_nonempty_outer_ramdisk_rejected(self):
        bad = build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh,
                                             non_empty_ramdisk=b'not-empty')
        with self.assertRaisesRegex(ValueError, 'ramdisk_size'):
            first_install.verify_mainline_image(bad, 'boot')

    def test_tar_rejects_wrong_member_extra_files_symlinks_and_trailing_bytes(self):
        boot_bytes = build_synthetic_mainline_image(is_recovery=False, dtbh=self.stub_dtbh)
        good_tar = self.work / 'BOOT-j701f-mainline.tar'
        good_tar.write_bytes(first_install.ustar_bytes('boot.img', boot_bytes))

        with self.assertRaisesRegex(ValueError, 'ONLY a regular recovery.img'):
            first_install.verify_tar(good_tar, 'recovery')

        appended = self.work / 'appended.tar'
        appended.write_bytes(good_tar.read_bytes() + b'trailing-payload')
        with self.assertRaisesRegex(ValueError, 'canonical'):
            first_install.verify_tar(appended, 'boot')

        multi = self.work / 'multi.tar'
        with tarfile.open(multi, 'w', format=tarfile.USTAR_FORMAT) as archive:
            for name in ('boot.img', 'recovery.img'):
                info = tarfile.TarInfo(name)
                info.size = len(boot_bytes)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(boot_bytes))
        with self.assertRaisesRegex(ValueError, 'ONLY a regular boot.img'):
            first_install.verify_tar(multi, 'boot')

        symlink_tar = self.work / 'symlink.tar'
        with tarfile.open(symlink_tar, 'w', format=tarfile.USTAR_FORMAT) as archive:
            info = tarfile.TarInfo('boot.img')
            info.type = tarfile.SYMTYPE
            info.linkname = '/etc/passwd'
            archive.addfile(info)
        with self.assertRaisesRegex(ValueError, 'ONLY a regular boot.img'):
            first_install.verify_tar(symlink_tar, 'boot')

        nonroot_tar = self.work / 'nonroot.tar'
        with tarfile.open(nonroot_tar, 'w', format=tarfile.USTAR_FORMAT) as archive:
            info = tarfile.TarInfo('boot.img')
            info.size = len(boot_bytes)
            info.mode = 0o644
            info.uid = 1000
            info.gid = 1000
            archive.addfile(info, io.BytesIO(boot_bytes))
        with self.assertRaisesRegex(ValueError, 'metadata differs'):
            first_install.verify_tar(nonroot_tar, 'boot')


@unittest.skipUnless(first_install.DEFAULT_BOOT.is_file() and first_install.DEFAULT_RECOVERY.is_file(),
                     'built cam5 BOOT and rec8 RECOVERY images are required')
class BuiltFirstInstallArtifactsTests(unittest.TestCase):
    def test_real_cam5_and_rec8_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / 'first-install'
            manifest = first_install.prepare_bundle(None, None, out_dir)
            self.assertTrue(manifest['pinned_defaults_used'])
            self.assertTrue(manifest['boot']['pinned_default'])
            self.assertEqual(manifest['boot']['pinned_expected_sha256'],
                             first_install.PINNED_BOOT_SHA256)
            self.assertIsNone(manifest['boot']['custom_override_sha256'])
            self.assertTrue(manifest['recovery']['pinned_default'])
            self.assertEqual(manifest['recovery']['pinned_expected_sha256'],
                             first_install.PINNED_RECOVERY_SHA256)
            self.assertIsNone(manifest['recovery']['custom_override_sha256'])
            res = subprocess.run(
                [sys.executable, str(ROOT / 'tools/prepare-first-install.py'),
                 '--verify-tar', str(out_dir / 'BOOT-j701f-mainline.tar'), '--role', 'boot'],
                capture_output=True, text=True, check=True,
            )
            self.assertIn('PASS: verified boot USTAR archive', res.stdout)


if __name__ == '__main__':
    unittest.main()


first_install_script = (lambda spec: (spec.loader.exec_module(m := importlib.util.module_from_spec(spec)), m)[1])(
    importlib.util.spec_from_file_location('first_install_script', ROOT / 'scripts/first-install.py'))


class FirstInstallScriptTests(unittest.TestCase):
    """scripts/first-install.py (added by Claude 2026-10-27, finishing Argon's draft)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def release(self, uuid=first_install_script.UUID, gz=b'payload', gz_hash=None):
        rel = self.work / 'release'
        rel.mkdir(exist_ok=True)
        (rel / 'userdata.ext4.gz').write_bytes(gz)
        (rel / 'userdata.ext4.gz.sha256').write_text((gz_hash or hashlib.sha256(gz).hexdigest()) + '  userdata.ext4.gz\n')
        (rel / 'userdata.ext4.sha256').write_text('a' * 64 + '  userdata.ext4\n')
        (rel / 'release.json').write_text(json.dumps({
            'device': 'SM-J701F / samsung,j7velte', 'sectors': first_install_script.SECTORS,
            'bytes': first_install_script.BYTES, 'filesystem_uuid': uuid,
            'raw_image': {'sha256': 'a' * 64}, 'root_version': 'TEST'}))
        return rel

    def fake_card(self, fstype='vfat', removable='1', mounted=True):
        card = self.work / 'card'
        card.mkdir(exist_ok=True)
        # Like sysfs: class/block/sdz1 -> devices/.../sdz/sdz1, "removable" on the disk.
        sys_block = self.work / 'sys/class/block'
        disk = self.work / 'sys/devices/usb/sdz'
        (disk / 'sdz1').mkdir(parents=True, exist_ok=True)
        (disk / 'sdz1/partition').write_text('1\n')
        (disk / 'removable').write_text(removable + '\n')
        sys_block.mkdir(parents=True, exist_ok=True)
        if not (sys_block / 'sdz1').is_symlink():
            (sys_block / 'sdz1').symlink_to(disk / 'sdz1')
        mounts = self.work / 'mounts'
        mounts.write_text(f'/dev/sdz1 {os.path.realpath(card)} {fstype} rw 0 0\n' if mounted else '')
        return card, mounts, sys_block

    def test_release_checks(self):
        info = first_install_script.check_release(self.release())
        self.assertEqual(info['root_version'], 'TEST')
        with self.assertRaisesRegex(ValueError, 'another filesystem UUID'):
            first_install_script.check_release(self.release(uuid='0' * 8 + '-0000-0000-0000-' + '0' * 12))
        with self.assertRaisesRegex(ValueError, 'does not match'):
            first_install_script.check_release(self.release(gz_hash='b' * 64))

    def test_sd_card_must_be_a_removable_vfat_mount(self):
        card, mounts, sys_block = self.fake_card()
        self.assertEqual(first_install_script.check_sd(card, mounts, sys_block)['disk'], 'sdz')
        card, mounts, sys_block = self.fake_card(removable='0')
        with self.assertRaisesRegex(ValueError, 'not on a removable disk'):
            first_install_script.check_sd(card, mounts, sys_block)
        card, mounts, sys_block = self.fake_card(fstype='ext4')
        with self.assertRaisesRegex(ValueError, 'expects FAT32'):
            first_install_script.check_sd(card, mounts, sys_block)
        card, mounts, sys_block = self.fake_card(mounted=False)
        with self.assertRaisesRegex(ValueError, 'not a mount point'):
            first_install_script.check_sd(card, mounts, sys_block)
        card, mounts, sys_block = self.fake_card()
        with self.assertRaisesRegex(ValueError, 'needed'):
            first_install_script.check_sd(card, mounts, sys_block, need=1 << 62)

    def test_stage_copies_and_reads_back_everything(self):
        rel = self.release()
        bundle = self.work / 'bundle'
        bundle.mkdir()
        (bundle / 'boot.img').write_bytes(b'boot')
        card = self.work / 'card'
        card.mkdir()
        dest = first_install_script.stage(card, rel, bundle)
        for name in first_install_script.RELEASE_FILES:
            self.assertEqual((dest / name).read_bytes(), (rel / name).read_bytes())
        for name in first_install_script.RECOVERY_SCRIPTS:
            self.assertTrue((dest / name).is_file(), name)
        self.assertEqual((dest / 'boot-mainline.img').read_bytes(), b'boot')
        self.assertEqual(list(dest.glob('*.part')), [])

    def test_never_runs_odin_or_touches_usb(self):
        source = (ROOT / 'scripts/first-install.py').read_text()
        for forbidden in ('subprocess', 'os.system', 'os.popen', 'Popen', '/dev/bus/usb/0', 'pyusb'):
            self.assertNotIn(forbidden, source)
