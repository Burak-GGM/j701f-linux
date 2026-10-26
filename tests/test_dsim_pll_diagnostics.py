"""Execute the trial-only PLL diagnostic and actual wait tail with mocked MMIO."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'build/kernel/ea8061s-prototype/reference/mainline/samsung-dsim.c'
PATCHES = ('linux-dsim-pll-wait-fix.patch',
           'linux-dsim-j701f-timing-trial.patch',
           'linux-dsim-z-j701f-pll-diagnostics.patch')

MOCK = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint32_t u32;
enum { DSIM_INTMSK_REG, DSIM_LINK_STATUS_REG, DSIM_PLLCTRL_REG };
struct completion { bool done; };
struct samsung_dsim {
    void *dev;
    struct completion completed, pll_stabilized;
    unsigned long hs_clock;
};
static bool trial, ready;
static u32 mask_before, mask_now, link;
static unsigned reads, writes, messages;
static bool samsung_dsim_j701f_trial(struct samsung_dsim *dsi)
{ (void)dsi; return trial; }
static void reinit_completion(struct completion *c) { c->done = false; }
static bool completion_done(struct completion *c) { return c->done; }
static u32 samsung_dsim_read(struct samsung_dsim *dsi, unsigned reg)
{
    (void)dsi; reads++;
    if (reg == DSIM_INTMSK_REG) return writes ? mask_now : mask_before;
    if (reg == DSIM_PLLCTRL_REG) return 0x806ae2;
    assert(reg == DSIM_LINK_STATUS_REG);
    return writes ? link : 0x01138002;
}
static void samsung_dsim_write(struct samsung_dsim *dsi, unsigned reg, u32 value)
{
    (void)dsi; assert(reg == DSIM_PLLCTRL_REG); assert(value == 0x806371);
    writes++;
}
static unsigned long wait_for_completion_timeout(struct completion *c, unsigned long t)
{ (void)c; (void)t; return ready ? 17 : 0; }
#define usecs_to_jiffies(x) (x)
#define dev_err(...) ((void)0)
#define dev_info(dev, fmt, ...) do { (void)(dev); messages++; printf(fmt, __VA_ARGS__); } while (0)
'''

MAIN = r'''
int main(int argc, char **argv)
{
    assert(argc == 7);
    trial = atoi(argv[1]); ready = atoi(argv[2]);
    mask_before = strtoul(argv[3], NULL, 0);
    mask_now = strtoul(argv[4], NULL, 0);
    link = strtoul(argv[5], NULL, 0);
    struct samsung_dsim dsi = {.completed = {.done = atoi(argv[6])}};
    unsigned long result = exercise_wait(&dsi, 476666666, 100);
    printf("RESULT %lu %lu %u %u %u\n", result, dsi.hs_clock, reads, writes, messages);
}
'''


@unittest.skipUnless(SOURCE.is_file() and shutil.which('clang') and shutil.which('patch'),
                     'prepared DSIM snapshot, clang and patch required')
class PllDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-pll-observe-')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name)
        copy = path / 'drivers/gpu/drm/bridge/samsung-dsim.c'
        copy.parent.mkdir(parents=True)
        copy.write_text(SOURCE.read_text())
        for patch in PATCHES:
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                            str(ROOT / 'kernel/patches' / patch)], cwd=path,
                           check=True, capture_output=True, text=True)
        source = copy.read_text()
        start = source.index('static void samsung_dsim_j701f_pll_diagnostic(')
        end = source.index('static unsigned long samsung_dsim_set_pll(', start)
        helper = source[start:end]
        start = source.index('\treinit_completion(&dsi->pll_stabilized);', end)
        end = source.index('static int samsung_dsim_enable_clock(', start)
        wait = ('static unsigned long exercise_wait(struct samsung_dsim *dsi, '
                'unsigned long fout, unsigned int timeout)\n{\n'
                '\tu32 mask_before = 0, link_before = 0, pll_before = 0, reg = 0x806371;\n\tbool ready;\n'
                + source[start:end])
        harness = path / 'observe.c'
        harness.write_text(MOCK + helper + wait + MAIN)
        cls.binary = path / 'observe'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', str(harness), '-o', str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def run_case(self, trial=1, ready=0, before=0xffffffff, now=0xffffffff,
                 link=0x1000000, reset=0):
        output = subprocess.check_output(
            [str(self.binary), *(str(x) for x in (trial, ready, before, now, link, reset))],
            text=True, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'))
        lines = output.splitlines()
        return lines[:-1], [int(x) for x in lines[-1].split()[1:]]

    def test_default_path_performs_no_diagnostic_reads_or_logging(self):
        for ready in (0, 1):
            with self.subTest(ready=ready):
                messages, result = self.run_case(trial=0, ready=ready)
                self.assertEqual(messages, [])
                self.assertEqual(result, [476666666 * ready] * 2 + [0, 1, 0])

    def test_stable_hardware_without_irq_is_observed_but_still_rejected(self):
        messages, result = self.run_case()
        self.assertEqual(result, [0, 0, 5, 1, 1])
        self.assertEqual(messages, ['J701F PLL completion=0 mask_before=0xffffffff '
                                    'mask_now=0xffffffff link_before=0x01138002 link_now=0x01000000 '
                                    'pll_before=0x00806ae2 reset_done=0'])

    def test_unlocked_hardware_timeout_is_distinguishable(self):
        messages, result = self.run_case(link=0)
        self.assertEqual(result[:2], [0, 0])
        self.assertIn('link_now=0000000000', messages[0])

    def test_mask_change_and_reset_completion_are_retained(self):
        messages, result = self.run_case(ready=1, now=0x3ffb7fff, reset=1)
        self.assertEqual(result, [476666666, 476666666, 5, 1, 1])
        self.assertIn('mask_before=0xffffffff mask_now=0x3ffb7fff', messages[0])
        self.assertIn('reset_done=1', messages[0])

    def test_instrumentation_never_changes_programming_or_failure_result(self):
        for ready in (0, 1):
            with self.subTest(ready=ready):
                observed = self.run_case(trial=1, ready=ready)[1]
                baseline = self.run_case(trial=0, ready=ready)[1]
                self.assertEqual(observed[:2], baseline[:2])
                self.assertEqual(observed[3], baseline[3])


if __name__ == '__main__':
    unittest.main()
