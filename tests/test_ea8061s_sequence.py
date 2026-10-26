"""Execute the panel's actual init routine with a mock DSI transport on the host.

The fixture is independently extracted from the pinned Samsung GPLv2 sources.
This tests byte ordering, waits, and transfer failures, not the physical panel.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/kmod/ea8061s/panel-j701f-ea8061s.c'
FIXTURE = ROOT / 'tests/fixtures/ea8061s-j7ve-init.json'

MOCK = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint8_t u8;
struct mipi_dsi_device { int unused; };
struct mipi_dsi_multi_context { struct mipi_dsi_device *dsi; int accum_err; };
static unsigned char commands[64][64];
static size_t lengths[64];
static int calls, fail_at, waits;
static unsigned delays[32][2];
static long mipi_dsi_dcs_write_buffer(struct mipi_dsi_device *dsi,
                                    const void *buf, size_t len)
{
    (void)dsi;
    assert(calls < 64 && len <= 64);
    const unsigned char *bytes = buf;
    for (size_t i = 0; i < len; i++) commands[calls][i] = bytes[i];
    lengths[calls++] = len;
    return calls == fail_at ? -EIO : (long)len;
}
static void write_multi(struct mipi_dsi_multi_context *ctx,
                        const void *buf, size_t len)
{
    if (ctx->accum_err) return;
    long ret = mipi_dsi_dcs_write_buffer(ctx->dsi, buf, len);
    if (ret < 0) ctx->accum_err = (int)ret;
}
#define mipi_dsi_dcs_write_seq_multi(ctx, ...) do { \
    static const u8 data[] = { __VA_ARGS__ }; \
    write_multi(ctx, data, sizeof(data)); \
} while (0)
static void mipi_dsi_dcs_exit_sleep_mode_multi(struct mipi_dsi_multi_context *ctx)
{
    mipi_dsi_dcs_write_seq_multi(ctx, 0x11);
}
static void record_wait(struct mipi_dsi_multi_context *ctx, unsigned a, unsigned b)
{
    if (ctx->accum_err) return;
    assert(waits < 32);
    delays[waits][0] = a; delays[waits++][1] = b;
}
#define mipi_dsi_usleep_range(ctx, a, b) record_wait(ctx, a, b)
#define mipi_dsi_msleep(ctx, a) record_wait(ctx, (a)*1000, (a)*1000)
'''

MAIN = r'''
int main(int argc, char **argv)
{
    struct mipi_dsi_device dsi = {0};
    fail_at = argc == 2 ? atoi(argv[1]) : 0;
    int ret = ea8061s_init_sequence(&dsi);
    printf("{\"result\":%d,\"commands\":[", ret);
    for (int i = 0; i < calls; i++) {
        printf("%s\"", i ? "," : "");
        for (size_t j = 0; j < lengths[i]; j++) printf("%02x", commands[i][j]);
        printf("\"");
    }
    printf("],\"waits\":[");
    for (int i = 0; i < waits; i++)
        printf("%s[%u,%u]", i ? "," : "", delays[i][0], delays[i][1]);
    printf("]}\n");
    return 0;
}
'''


@unittest.skipUnless(shutil.which('clang'), 'host clang is required')
class PanelSequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-panel-sequence-')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name)
        source = SOURCE.read_text()
        # Compile the driver functions themselves, without kernel-only lifecycle code.
        functions = source[source.index('static void ea8061s_lock_keys('):
                           source.index('static void ea8061s_power_off(')]
        harness = path / 'sequence.c'
        harness.write_text(MOCK + functions + MAIN)
        cls.binary = path / 'sequence'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', str(harness), '-o', str(cls.binary)],
                       check=True, capture_output=True, text=True)
        cls.expected = [c['hex'] for c in json.loads(FIXTURE.read_text())['commands']]

    def run_sequence(self, fail_at=0):
        # No heap allocation in the routine/harness; LeakSanitizer cannot run
        # inside a ptrace-based sandbox. Keep address/UB checks enabled.
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
        return json.loads(subprocess.check_output([str(self.binary), str(fail_at)],
                                                 text=True, env=env))

    def test_vendor_command_bytes_and_order(self):
        result = self.run_sequence()
        self.assertEqual(result['result'], 0)
        self.assertEqual(result['commands'], self.expected)

    def test_vendor_waits(self):
        self.assertEqual(self.run_sequence()['waits'],
                         [[5000, 6000], [10000, 11000], [10000, 11000], [150000, 150000]])

    def test_each_failed_transfer_stops_sequence_and_relocks_both_keys(self):
        for fail_at in range(1, len(self.expected) + 1):
            with self.subTest(fail_at=fail_at):
                result = self.run_sequence(fail_at)
                self.assertEqual(result['result'], -5)
                self.assertEqual(result['commands'],
                                 self.expected[:fail_at] + ['f0a5a5', 'fca5a5'])


if __name__ == '__main__':
    unittest.main()
