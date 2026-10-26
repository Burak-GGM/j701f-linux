"""Execute the actual patched DSIM wait branch and IRQ handler on the host."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'build/kernel/ea8061s-prototype/reference/mainline/samsung-dsim.c'
STAGED = ROOT / 'kernel/patches/staged/linux-dsim-pll-wait-fix.patch'
ACTIVE = ROOT / 'kernel/patches/linux-dsim-pll-wait-fix.patch'

MOCK = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint32_t u32;
typedef int irqreturn_t;
#define IRQ_HANDLED 1
#define BIT(x) (1U << (x))
#define DSIM_INT_PLL_STABLE BIT(31)
#define DSIM_INT_SW_RST_RELEASE BIT(30)
#define DSIM_INT_SFR_FIFO_EMPTY BIT(29)
#define DSIM_INT_SFR_HDR_FIFO_EMPTY BIT(28)
#define DSIM_INT_RX_DONE BIT(18)
#define DSIM_INT_RX_ECC_ERR BIT(15)
enum {DSIM_INTSRC_REG, DSIM_INTMSK_REG};
struct completion { unsigned calls; };
struct samsung_dsim {
    struct completion completed, pll_stabilized;
    unsigned long hs_clock;
};
static unsigned long completion_result;
static u32 status, ack, interrupt_mask = ~0U;
static unsigned finished, started;
static void complete(struct completion *c) { c->calls++; }
static unsigned long wait_for_completion_timeout(struct completion *c, unsigned long t)
{
    (void)c; (void)t;
    return completion_result;
}
#define usecs_to_jiffies(x) (x)
#define dev_err(...) ((void)0)
#define dev_warn(...) ((void)0)
static int printk_timed_ratelimit(unsigned long *j, unsigned ms)
{
    (void)j; (void)ms;
    return 0;
}
static u32 samsung_dsim_read(struct samsung_dsim *dsi, unsigned reg)
{
    (void)dsi; assert(reg == DSIM_INTSRC_REG); return status;
}
static void samsung_dsim_write(struct samsung_dsim *dsi, unsigned reg, u32 value)
{
    (void)dsi;
    if (reg == DSIM_INTSRC_REG) { ack = value; status &= ~value; }
    else { assert(reg == DSIM_INTMSK_REG); interrupt_mask = value; }
}
static int samsung_dsim_transfer_finish(struct samsung_dsim *dsi)
{
    (void)dsi; finished++; return 1;
}
static void samsung_dsim_transfer_start(struct samsung_dsim *dsi)
{
    (void)dsi; started++;
}
'''

MAIN = r'''
int main(int argc, char **argv)
{
    assert(argc == 3);
    struct samsung_dsim dsi = {0};
    completion_result = strtoul(argv[1], NULL, 0);
    status = strtoul(argv[2], NULL, 0);
    unsigned long result = exercise_wait(&dsi, 476666666, 100);
    assert(samsung_dsim_irq(0, &dsi) == IRQ_HANDLED);
    printf("%lu %lu %u %u %u %u %u %u\n", result, dsi.hs_clock,
           dsi.completed.calls, dsi.pll_stabilized.calls,
           finished, started, ack, interrupt_mask);
}
'''


@unittest.skipUnless(SOURCE.is_file() and shutil.which('clang') and shutil.which('patch'),
                     'prepared DSIM source snapshot, clang and patch are required')
class DsimCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-dsim-completion-')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name)
        copy = path / 'drivers/gpu/drm/bridge/samsung-dsim.c'
        copy.parent.mkdir(parents=True)
        copy.write_text(SOURCE.read_text())
        patch = STAGED if STAGED.is_file() else ACTIVE
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)],
                       cwd=path, check=True, capture_output=True, text=True)
        source = copy.read_text()
        start = source.index('\tif (!wait_for_completion_timeout(&dsi->pll_stabilized,')
        end = source.index('\nstatic int samsung_dsim_enable_clock(', start)
        wait = ('static unsigned long exercise_wait(struct samsung_dsim *dsi, '
                'unsigned long fout, unsigned int timeout)\n{\n' + source[start:end])
        start = source.index('static irqreturn_t samsung_dsim_irq(')
        end = source.index('static void samsung_dsim_enable_irq(', start)
        irq = source[start:end]
        harness = path / 'completion.c'
        harness.write_text(MOCK + wait + irq + MAIN)
        cls.binary = path / 'completion'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-parameter', '-fsanitize=address,undefined',
                        str(harness), '-o', str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def run_case(self, completion=1, irq=0):
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
        result = subprocess.check_output([str(self.binary), str(completion), str(irq)],
                                         text=True, env=env)
        return [int(word) for word in result.split()]

    def test_successful_completion_sets_clock(self):
        for remaining in (1, 8, 100):
            with self.subTest(remaining=remaining):
                self.assertEqual(self.run_case(completion=remaining)[:2],
                                 [476666666, 476666666])

    def test_timeout_rejects_clock(self):
        self.assertEqual(self.run_case(completion=0)[:2], [0, 0])

    def test_reset_unmasks_pll_interrupt(self):
        result = self.run_case(irq=1 << 30)
        self.assertEqual(result[2:4], [1, 0])
        self.assertEqual(result[7] & (1 << 31), 0)

    def test_pll_completion_preserves_simultaneous_receive(self):
        for transfer in (1 << 18, 1 << 29):
            with self.subTest(transfer=transfer):
                status = (1 << 31) | transfer
                result = self.run_case(irq=status)
                self.assertEqual(result[2:7], [0, 1, 1, 1, status])

    def test_all_coalesced_events_are_serviced(self):
        status = (1 << 30) | (1 << 31) | (1 << 18)
        self.assertEqual(self.run_case(irq=status)[2:7], [1, 1, 1, 1, status])

    def test_spurious_irq_does_not_complete_or_advance_transfer(self):
        self.assertEqual(self.run_case(irq=0)[2:7], [0, 0, 0, 0, 0])


if __name__ == '__main__':
    unittest.main()
