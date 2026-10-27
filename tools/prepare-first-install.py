#!/usr/bin/env python3
"""Prepare and verify host-only single-member USTAR Odin archives for BOOT and RECOVERY.

Never invokes Odin, never accesses USB, and never writes to a phone.
"""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import sys
import tarfile
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import recovery  # noqa: E402


def _load_tool(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fit_tool = _load_tool('build_mainline_fit', 'build-mainline-fit.py')
stub_tool = _load_tool('prepare_sboot_stub', 'prepare-sboot-stub.py')

DEFAULT_OUT = ROOT / 'build/first-install'
DEFAULT_BOOT = ROOT / 'build/kernel/boot-update-cam5/boot-mainline.img'
DEFAULT_RECOVERY = ROOT / 'build/kernel/boot-update-rec8/boot-mainline.img'

PINNED_BOOT_SHA256 = 'f2e232a89294ffe5a106d75499b5d37596aaf7b401ce7ef1740cface5ad5877f'
PINNED_RECOVERY_SHA256 = 'd439dfaec0c1da2ec25311941721f0baf4910bbeeeb139284bacf1309db1b124'

BOOT_CAPACITY = 65536 * 512      # 33,554,432 bytes (32 MiB, mmcblk0p10)
RECOVERY_CAPACITY = 77824 * 512  # 39,845,888 bytes (38 MiB, mmcblk0p11)

STUB_DTBH_SHA256 = '4a58e660fec63dfce5abca17dffe3166b6ca63ccf6b6eb69849d7969c870bd41'
EXPECTED_FIELDS = {
    'kernel_addr': 0x10008000,
    'ramdisk_size': 0,
    'ramdisk_addr': 0x11000000,
    'second_size': 0,
    'second_addr': 0x10f00000,
    'tags_addr': 0x10000100,
    'page_size': 2048,
    'os_version_raw': 0x2004063c,
}
ROLE_SPEC = {
    'boot': {
        'member': 'boot.img',
        'archive': 'BOOT-j701f-mainline.tar',
        'capacity': BOOT_CAPACITY,
        'partition': 'BOOT',
        'device': '/dev/mmcblk0p10',
        'sectors': 65536,
        'pinned_sha256': PINNED_BOOT_SHA256,
    },
    'recovery': {
        'member': 'recovery.img',
        'archive': 'RECOVERY-j701f-mainline.tar',
        'capacity': RECOVERY_CAPACITY,
        'partition': 'RECOVERY',
        'device': '/dev/mmcblk0p11',
        'sectors': 77824,
        'pinned_sha256': PINNED_RECOVERY_SHA256,
    },
}
PUBLISHED_FILES = (
    'boot.img',
    'BOOT-j701f-mainline.tar',
    'recovery.img',
    'RECOVERY-j701f-mainline.tar',
    'SHA256SUMS',
    'manifest.json',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def extract_embedded_fit(loader):
    """Find and return the unique embedded FIT inside the U-Boot loader binary."""
    require(len(loader) >= 64 and loader[56:60] == b'ARM\x64',
            'Loader is not an ARM64 Image')
    text_offset, memory_size, flags = struct.unpack_from('<3Q', loader, 8)
    require(text_offset == 0 and not (flags & 1) and 0 < memory_size < 0x04000000,
            'Unsupported U-Boot ARM64 header parameters')
    require(b'bootcmd=j701f_ramboot\0' in loader,
            'U-Boot loader is missing locked bootcmd=j701f_ramboot environment')

    candidates = []
    pos = 64
    while True:
        idx = loader.find(b'\xd0\x0d\xfe\xed', pos)
        if idx < 0 or idx + 40 > len(loader):
            break
        if idx % 8 == 0:
            total = struct.unpack_from('>I', loader, idx + 4)[0]
            if 65536 <= total <= len(loader) - idx:
                blob = loader[idx:idx + total]
                try:
                    props = fit_tool.fit_properties(blob)
                except ValueError:
                    props = None
                if props and '/configurations/conf-j701f-diagnostic/compatible' in props:
                    candidates.append((idx, blob, props))
        pos = idx + 4

    require(len(candidates) == 1,
            f'Expected exactly one embedded J701F FIT in loader, found {len(candidates)}')
    offset, fit_blob, props = candidates[0]
    fit_digest = hashlib.sha256(fit_blob).digest()
    require(fit_digest in loader[:offset] or fit_digest in loader[offset + len(fit_blob):],
            'Embedded FIT SHA-256 digest is not pinned in the loader binary')
    return offset, fit_blob, props


def verify_mainline_image(data, role):
    """Verify an embedded-FIT mainline Android container for role ('boot' or 'recovery')."""
    require(role in ROLE_SPEC, f'Unsupported role: {role!r}')
    spec = ROLE_SPEC[role]
    require(len(data) <= spec['capacity'],
            f'{role} image ({len(data)} bytes) exceeds {spec["partition"]} capacity ({spec["capacity"]} bytes)')

    image = recovery.Image(data)
    for field, expected in EXPECTED_FIELDS.items():
        require(image.fields[field] == expected,
                f'Unexpected {field} in {role} header: {image.fields[field]:#x} != {expected:#x}')
    require(image.parts['ramdisk'] == b'' and image.parts['second'] == b'',
            'Mainline container must have empty outer Android ramdisk and second slots')

    cmdline = image.header[64:576].split(b'\0', 1)[0]
    extra_cmdline = image.header[608:1632].split(b'\0', 1)[0]
    name_field = image.header[48:64].split(b'\0', 1)[0]
    require(cmdline == b'buildvariant=eng' and extra_cmdline == b'' and name_field == b'',
            'Unexpected outer Android header name or command line')

    if (ROOT / 'original/OrangeFox-recovery.img').is_file():
        old = recovery.baseline()
        allowed = set(range(8, 12)) | set(range(16, 20)) | set(range(40, 44)) | set(range(576, 596))
        require(all(a == b or i in allowed for i, (a, b) in enumerate(zip(old.header, image.header))),
                'Header bytes differ from baseline outside kernel/ramdisk/dt sizes and SHA-1')

    stub_tool.parse_table(image.parts['dt'])
    require(sha256_bytes(image.parts['dt']) == STUB_DTBH_SHA256,
            'Outer DTBH table does not match the pinned J701F S-BOOT stub')

    fit_offset, fit_blob, props = extract_embedded_fit(image.parts['kernel'])
    require(props.get('/configurations/default') == b'conf-j701f-diagnostic\0',
            'Unexpected FIT default configuration')
    require(props.get('/configurations/conf-j701f-diagnostic/compatible') == b'samsung,j7velte\0',
            'FIT configuration is not for samsung,j7velte')

    for node, kind in (('kernel', 'kernel'), ('fdt', 'flat_dt'), ('initramfs', 'ramdisk')):
        prefix = f'/images/{node}'
        blob = props.get(f'{prefix}/data')
        require(blob is not None and len(blob) > 0, f'Missing FIT {node} data')
        require(props.get(f'{prefix}/hash-1/algo') == b'sha256\0', f'FIT {node} must use sha256')
        require(props.get(f'{prefix}/hash-1/value') == hashlib.sha256(blob).digest(),
                f'FIT {node} SHA-256 mismatch')
        require(props.get(f'{prefix}/type') == kind.encode() + b'\0', f'Wrong FIT {node} type')
        require(props.get(f'{prefix}/arch') == b'arm64\0' and props.get(f'{prefix}/os') == b'linux\0',
                f'Wrong FIT {node} arch/os')

    kernel_comp = props.get('/images/kernel/compression')
    kernel_data = props['/images/kernel/data']
    if kernel_comp == b'gzip\0':
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        kernel_raw = decoder.decompress(kernel_data)
        require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                'Corrupt gzip kernel payload in FIT')
    elif kernel_comp == b'none\0':
        kernel_raw = kernel_data
    else:
        raise ValueError(f'Unsupported FIT kernel compression: {kernel_comp!r}')
    require(len(kernel_raw) >= 64 and kernel_raw[56:60] == b'ARM\x64',
            'Decompressed FIT kernel is not an ARM64 Image')

    fdt_data = props['/images/fdt/data']
    require(len(fdt_data) >= 40 and struct.unpack_from('>I', fdt_data, 0)[0] == 0xd00dfeed,
            'FIT FDT is not a valid flattened device tree')
    require(b'samsung,j7velte\0' in fdt_data, 'FIT FDT does not identify samsung,j7velte')

    initrd_gz = props['/images/initramfs/data']
    try:
        initrd_cpio = gzip.decompress(initrd_gz)
    except OSError as exc:
        raise ValueError('FIT initramfs is not valid gzip data') from exc
    entries = {name: (vals, payload) for name, vals, payload in recovery.cpio_entries(initrd_cpio)}
    for required_entry in ('init', 'bin/busybox', 'bin/alpine-handoff', 'bin/muic-usb-path', 'bin/usb-configfs'):
        require(required_entry in entries, f'FIT initramfs is missing {required_entry}')
    recovery.elf_static(entries['bin/busybox'][1])

    has_recovery_ui = 'bin/recovery-ui' in entries or 'bin/recovery-main' in entries
    if role == 'boot':
        require(not has_recovery_ui,
                'BOOT image must not contain recovery-ui/recovery-main (would enter recovery instead of system)')
    else:
        for req in ('bin/recovery-ui', 'bin/recovery-main', 'recovery/scripts/flash-boot.sh',
                    'recovery/scripts/storage.sh'):
            require(req in entries, f'RECOVERY image is missing {req}')
        ui_bin = entries['bin/recovery-ui'][1]
        require(len(ui_bin) >= 64 and ui_bin[:6] == b'\x7fELF\x02\x01'
                and struct.unpack_from('<H', ui_bin, 18)[0] == 183,
                'recovery-ui is not a 64-bit AArch64 ELF binary')

    return {
        'role': role,
        'partition': spec['partition'],
        'device': spec['device'],
        'capacity_bytes': spec['capacity'],
        'image_bytes': len(data),
        'image_sha256': sha256_bytes(data),
        'loader_bytes': len(image.parts['kernel']),
        'loader_sha256': sha256_bytes(image.parts['kernel']),
        'fit_offset': fit_offset,
        'fit_bytes': len(fit_blob),
        'fit_sha256': sha256_bytes(fit_blob),
        'kernel_uncompressed_bytes': len(kernel_raw),
        'kernel_uncompressed_sha256': sha256_bytes(kernel_raw),
        'fdt_bytes': len(fdt_data),
        'fdt_sha256': sha256_bytes(fdt_data),
        'initramfs_bytes': len(initrd_gz),
        'initramfs_sha256': sha256_bytes(initrd_gz),
        'initramfs_entries': len(entries),
        'stub_dtbh_sha256': sha256_bytes(image.parts['dt']),
    }


def ustar_bytes(member_name, data):
    """Build canonical single-member uncompressed USTAR archive bytes."""
    require(member_name in ('boot.img', 'recovery.img'), f'Disallowed tar member name: {member_name!r}')
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        info = tarfile.TarInfo(member_name)
        info.size = len(data)
        info.mode = 0o644
        info.mtime = 0
        info.uid = 0
        info.gid = 0
        info.uname = ''
        info.gname = ''
        info.type = tarfile.REGTYPE
        archive.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def verify_tar(path, role):
    """Verify that path is a canonical single-member USTAR archive for role ('boot' or 'recovery')."""
    require(role in ROLE_SPEC, f'Unsupported role: {role!r}')
    expected_member = ROLE_SPEC[role]['member']
    path = Path(path)
    raw_tar = path.read_bytes()
    with tarfile.open(fileobj=io.BytesIO(raw_tar), mode='r:') as archive:
        members = archive.getmembers()
        require(len(members) == 1 and members[0].name == expected_member and members[0].isfile(),
                f'Archive must contain ONLY a regular {expected_member} member')
        member = members[0]
        require(member.uid == 0 and member.gid == 0 and member.mode == 0o644 and member.mtime == 0
                and member.uname == '' and member.gname == '',
                'Archive member metadata differs from canonical root USTAR attributes')
        payload = archive.extractfile(member).read()
    require(raw_tar == ustar_bytes(expected_member, payload),
            f'Archive is not canonical {expected_member}-only USTAR (extra headers or trailing data)')
    info = verify_mainline_image(payload, role)
    info['archive_name'] = path.name
    info['archive_bytes'] = len(raw_tar)
    info['archive_sha256'] = sha256_bytes(raw_tar)
    info['member_name'] = expected_member
    return info


def clear_published_outputs(out_dir):
    """Remove any previous ready markers and artifacts; refuse non-file/directory collisions.

    The manifest goes first, before anything can fail, so that a refused or
    half-cleaned output directory never still looks prepared. Then every other
    target is checked before any of them is removed.
    """
    manifest = out_dir / 'manifest.json'
    if manifest.is_symlink() or manifest.is_file():
        manifest.unlink()
    targets = [out_dir / name for name in PUBLISHED_FILES]
    for target in targets:
        if (target.exists() or target.is_symlink()) and not (target.is_symlink() or target.is_file()):
            raise ValueError(f'Output target {target} exists and is not a regular file or symlink (e.g. directory)')
    for target in targets:
        if target.is_symlink() or target.is_file():
            target.unlink()


def prepare_bundle(boot_path=None, recovery_path=None, out_dir=DEFAULT_OUT):
    raw_out = Path(out_dir)
    require(not raw_out.is_symlink(), f'Output directory must not be a symlink: {raw_out}')
    out_dir = raw_out.resolve()
    if out_dir.exists():
        require(out_dir.is_dir(), f'Output path is not a directory: {out_dir}')
    else:
        out_dir.mkdir(parents=True, exist_ok=True)

    raw_boot = Path(boot_path) if boot_path is not None else DEFAULT_BOOT
    raw_rec = Path(recovery_path) if recovery_path is not None else DEFAULT_RECOVERY

    published_targets = set()
    for name in PUBLISHED_FILES:
        target = out_dir / name
        published_targets.add(target)
        if target.exists() or target.is_symlink():
            try:
                published_targets.add(target.resolve())
            except OSError:
                pass

    # Check both unresolved and resolved input paths against published output paths BEFORE any cleanup.
    for label, candidate in (('BOOT', raw_boot), ('RECOVERY', raw_rec)):
        resolved_candidate = candidate.resolve()
        require(candidate.absolute() not in published_targets and resolved_candidate not in published_targets,
                f'{label} source image {candidate} collides with a published output path in {out_dir}')

    # Now invalidate any prior published manifest/archives so a failed run never leaves stale ready state.
    clear_published_outputs(out_dir)

    require(not raw_boot.is_symlink() and raw_boot.is_file(), f'Missing regular BOOT image: {raw_boot}')
    require(not raw_rec.is_symlink() and raw_rec.is_file(), f'Missing regular RECOVERY image: {raw_rec}')

    boot_resolved = raw_boot.resolve()
    rec_resolved = raw_rec.resolve()
    require(boot_resolved != rec_resolved, 'BOOT and RECOVERY source paths must be distinct')

    boot_custom = boot_path is not None and boot_resolved != DEFAULT_BOOT.resolve()
    rec_custom = recovery_path is not None and rec_resolved != DEFAULT_RECOVERY.resolve()

    boot_data = boot_resolved.read_bytes()
    rec_data = rec_resolved.read_bytes()
    boot_sha = sha256_bytes(boot_data)
    rec_sha = sha256_bytes(rec_data)

    if not boot_custom:
        require(boot_sha == PINNED_BOOT_SHA256,
                f'Default cam5 BOOT image SHA-256 mismatch: {boot_sha} != {PINNED_BOOT_SHA256}')
    if not rec_custom:
        require(rec_sha == PINNED_RECOVERY_SHA256,
                f'Default rec8 RECOVERY image SHA-256 mismatch: {rec_sha} != {PINNED_RECOVERY_SHA256}')

    verify_mainline_image(boot_data, 'boot')
    verify_mainline_image(rec_data, 'recovery')

    staging = Path(tempfile.mkdtemp(prefix='.first-install-staging-', dir=out_dir))
    try:
        outputs = {}
        for role, src_path, data, is_custom in (
            ('boot', boot_resolved, boot_data, boot_custom),
            ('recovery', rec_resolved, rec_data, rec_custom),
        ):
            spec = ROLE_SPEC[role]
            img_stage = staging / spec['member']
            tar_stage = staging / spec['archive']
            recovery.write(img_stage, data)
            recovery.write(tar_stage, ustar_bytes(spec['member'], data))
            verified = verify_tar(tar_stage, role)
            verified['source_image'] = (str(src_path.relative_to(ROOT))
                                        if src_path.is_relative_to(ROOT) else str(src_path))
            verified['pinned_default'] = not is_custom
            verified['pinned_expected_sha256'] = None if is_custom else spec['pinned_sha256']
            verified['custom_override_sha256'] = verified['image_sha256'] if is_custom else None
            outputs[role] = verified

        sha_lines = [
            f"{outputs['boot']['image_sha256']}  boot.img\n",
            f"{outputs['boot']['archive_sha256']}  {ROLE_SPEC['boot']['archive']}\n",
            f"{outputs['recovery']['image_sha256']}  recovery.img\n",
            f"{outputs['recovery']['archive_sha256']}  {ROLE_SPEC['recovery']['archive']}\n",
        ]
        recovery.write(staging / 'SHA256SUMS', ''.join(sha_lines).encode())

        manifest = {
            'status': 'host-prepared',
            'device': 'SM-J701F / samsung,j7velte',
            'phone_modified': False,
            'odin_executed': False,
            'pinned_defaults_used': not (boot_custom or rec_custom),
            'boot': outputs['boot'],
            'recovery': outputs['recovery'],
        }
        recovery.json_write(staging / 'manifest.json', manifest)

        # Verify no colliding directory or symlink appeared in out_dir before publishing,
        # and publish manifest.json last so 'host-prepared' is atomic.
        try:
            clear_published_outputs(out_dir)
            for name in PUBLISHED_FILES:
                (staging / name).replace(out_dir / name)
        except Exception:
            for name in PUBLISHED_FILES:
                target = out_dir / name
                if target.is_file() or target.is_symlink():
                    target.unlink()
            raise
        return manifest
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--boot-image', type=Path, default=None,
                        help='Verified mainline BOOT image (default: pinned boot-update-cam5/boot-mainline.img)')
    parser.add_argument('--recovery-image', type=Path, default=None,
                        help='Verified mainline graphical RECOVERY image (default: pinned boot-update-rec8/boot-mainline.img)')
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUT,
                        help='Output directory for single-member Odin USTAR archives (default: build/first-install)')
    parser.add_argument('--verify-tar', type=Path, metavar='ARCHIVE',
                        help='Verify an existing single-member Odin USTAR archive instead of building')
    parser.add_argument('--role', choices=('boot', 'recovery'),
                        help='Expected role when using --verify-tar')
    args = parser.parse_args()

    if args.verify_tar is not None:
        if not args.role:
            parser.error('--verify-tar requires --role {boot,recovery}')
        info = verify_tar(args.verify_tar, args.role)
        print(f"PASS: verified {args.role} USTAR archive {args.verify_tar} ({info['archive_bytes']} bytes, sha256 {info['archive_sha256']})")
        return

    manifest = prepare_bundle(args.boot_image, args.recovery_image, args.output_dir)
    print(f"PASS: prepared host-only first-install archives in {args.output_dir}")
    print(f"  BOOT:     {manifest['boot']['archive_name']} ({manifest['boot']['archive_bytes']} bytes, sha256 {manifest['boot']['archive_sha256']})")
    print(f"  RECOVERY: {manifest['recovery']['archive_name']} ({manifest['recovery']['archive_bytes']} bytes, sha256 {manifest['recovery']['archive_sha256']})")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, tarfile.TarError, zlib.error) as exc:
        raise SystemExit(f'ERROR: {exc}')
