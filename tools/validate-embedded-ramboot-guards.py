#!/usr/bin/env python3
"""Exercise real C handoff guards on the host; boot/environment APIs are mocks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/kernel/handoff-embedded'

HEADER = '''#ifndef RAMBOOT_HOST_H
#define RAMBOOT_HOST_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <limits.h>
#include <libfdt.h>
typedef unsigned long ulong;
typedef uint8_t u8;
struct cmd_tbl { int unused; };
struct test_bank { ulong start, size; };
struct test_bd { struct test_bank bi_dram[2]; };
struct test_gd { struct test_bd *bd; ulong relocaddr, mon_len; };
extern struct test_gd *gd;
#define DECLARE_GLOBAL_DATA_PTR
#define U_BOOT_CMD(...)
#define CMD_RET_FAILURE 1
#define SHA256_SUM_LEN 32
#define CHUNKSZ_SHA256 (64 * 1024)
const char *env_get(const char *key);
int env_set(const char *key, const char *value);
ulong get_prev_bl_fdt_addr(void);
int fit_check_format(const void *fit, ulong bytes);
void sha256_csum_wd(const unsigned char *input, unsigned len, unsigned char *output, unsigned chunk);
int run_commandf(const char *format, ...);
#endif
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(out=OUT, loader_dir=None):
    loader_dir = loader_dir or ROOT / 'build/kernel/uboot-j701f-embedded'
    source = ROOT / 'kernel/diagnostic/j701f-embedded-ramboot.c'
    loader = json.loads((loader_dir / 'report.json').read_text())
    if (loader['status'] != 'compiled' or
            sha(source) != loader['inputs'][str(source.relative_to(ROOT))] or
            sha(out / 'mainline.itb') != loader['paired_fit_sha256'] or
            sha(out / 'j701f-fit-payload.h') != loader['paired_fit_header_sha256']):
        raise ValueError('Compile the current handoff loader before testing its guards')
    with tempfile.TemporaryDirectory(prefix='j701f-ramboot-guards-') as temporary:
        work = Path(temporary)
        (work / 'ramboot-host.h').write_text(HEADER)
        for name in ['command.h', 'env.h', 'image.h', 'init.h', 'linux/libfdt.h',
                     'u-boot/sha256.h', 'asm/global_data.h']:
            target = work / name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('#include "ramboot-host.h"\n')
        command = ['clang', '-std=gnu11', '-Wall', '-Wextra', '-Wno-unused-parameter',
                   '-I' + str(work), '-I' + str(out),
                   str(ROOT / 'tests/embedded_ramboot_runtime_test.c'), '-lfdt', '-lcrypto',
                   '-fno-pie', '-no-pie', '-mcmodel=large',
                   '-Wl,--defsym,j701f_embedded_fit=0xbf100000',
                   '-Wl,--defsym,j701f_embedded_fit_end=' + hex(0xbf100000 + (out / 'mainline.itb').stat().st_size),
                   '-o', str(work / 'test')]
        subprocess.run(command, check=True)
        result = subprocess.run([str(work / 'test'), str(out / 'mainline.itb')],
                                check=True, capture_output=True, text=True)
    (out / 'guard-validation.txt').write_text(result.stdout)
    (out / 'guard-validation-report.json').write_text(json.dumps(dict(
        status='passed', phone_modified=False, hardware_boot_tested=False,
        source_sha256=sha(source), fit_sha256=sha(out / 'mainline.itb'),
        harness_sha256=sha(ROOT / 'tests/embedded_ramboot_runtime_test.c'),
        valid_handoffs=2, rejected_handoffs=15,
        scope='Actual C guards on x86_64 with real libfdt/SHA256 and mocked environment/boot APIs; no Linux execution.',
        limits=['Not a U-Boot emulator, Samsung handoff proof or real bootm test.']), indent=2)+'\n')
    print(result.stdout.splitlines()[-1])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fit-dir', type=Path, default=OUT)
    parser.add_argument('--loader-dir', type=Path)
    args = parser.parse_args()
    main(args.fit_dir, args.loader_dir)
