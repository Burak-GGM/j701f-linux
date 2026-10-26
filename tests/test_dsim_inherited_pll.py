"""Exercise actual DSIM init ordering with inherited-PLL/no-new-event model.

The event model is a hypothesis from phone traces; tests do not prove hardware.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'build/kernel/ea8061s-prototype/reference/mainline/samsung-dsim.c'
MOCK = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define DSIM_STATE_INITIALIZED 1
#define DSIM_FUNCRST 2
#define RESET_TYPE 0
#define DSIM_PLLCTRL_REG 0
#define DSIM_PLL_EN (1U << 23)
#define BIT(x) (1U << (x))
#define msecs_to_jiffies(x) (x)
#define dev_err(...) ((void)0)
struct completion { int unused; };
struct samsung_dsim_driver_data { unsigned reg_values[1]; bool wait_for_reset; };
struct samsung_dsim {
    struct samsung_dsim_driver_data *driver_data;
    struct completion completed;
    unsigned state, lanes;
};
static int failure, irq_depth, reads;
static bool clock_on, trial;
static char trace[64];
static void event(char c) { size_t n = strlen(trace); assert(n+1 < sizeof(trace)); trace[n] = c; }
static bool samsung_dsim_j701f_trial(struct samsung_dsim *d) { (void)d; return trial; }
static unsigned samsung_dsim_read(struct samsung_dsim *d, unsigned reg)
{ (void)d; assert(reg == DSIM_PLLCTRL_REG); reads++; return clock_on ? DSIM_PLL_EN : 0; }
static unsigned long wait_for_completion_timeout(struct completion *c, unsigned long t)
{ (void)c; (void)t; event('W'); return failure == 2 ? 0 : 1; }
static void samsung_dsim_reset(struct samsung_dsim *d) { (void)d; event('R'); }
static void samsung_dsim_enable_irq(struct samsung_dsim *d)
{ (void)d; event('I'); assert(irq_depth == 0); irq_depth++; }
static void samsung_dsim_disable_irq(struct samsung_dsim *d)
{ (void)d; event('i'); assert(irq_depth == 1); irq_depth--; }
static void samsung_dsim_enable_lane(struct samsung_dsim *d, unsigned lanes)
{ (void)d; assert(lanes == 15); event('N'); }
static int samsung_dsim_enable_clock(struct samsung_dsim *d)
{
    (void)d; event('C');
    if (clock_on) return -EFAULT; /* already enabled: no fresh completion */
    clock_on = true;
    return failure == 1 ? -EIO : 0;
}
static void samsung_dsim_disable_clock(struct samsung_dsim *d)
{ (void)d; event('D'); assert(clock_on); clock_on = false; }
static void samsung_dsim_set_phy_ctrl(struct samsung_dsim *d) { (void)d; event('P'); }
static int samsung_dsim_init_link(struct samsung_dsim *d)
{ (void)d; event('L'); return failure == 3 ? -EFAULT : 0; }
'''
MAIN = r'''
int main(int argc, char **argv)
{
    assert(argc == 6);
    bool fixed = atoi(argv[1]); trial = atoi(argv[2]); clock_on = atoi(argv[3]);
    failure = atoi(argv[4]); bool retry = atoi(argv[5]);
    struct samsung_dsim_driver_data data = {{0}, true};
    struct samsung_dsim dsi = {.driver_data = &data, .lanes = 4};
    int first = fixed ? samsung_dsim_init(&dsi) : baseline_init(&dsi);
    int first_irq = irq_depth, first_clock = clock_on;
    unsigned first_state = dsi.state;
    char first_trace[64]; strcpy(first_trace, trace);
    int second = 0;
    if (retry) {
        failure = 0;
        second = fixed ? samsung_dsim_init(&dsi) : baseline_init(&dsi);
    }
    printf("%d %u %d %d %d %u %d %d %d %s %s\n", first, first_state, first_irq,
           first_clock, second, dsi.state, irq_depth, clock_on, reads, first_trace, trace);
}
'''


@unittest.skipUnless(SOURCE.is_file() and shutil.which('clang') and shutil.which('patch'),
                     'prepared DSIM source, clang and patch required')
class InheritedPllTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-pll-inherited-')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name)
        copy = path / 'drivers/gpu/drm/bridge/samsung-dsim.c'
        copy.parent.mkdir(parents=True)
        copy.write_text(SOURCE.read_text())
        def apply(name):
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                            str(ROOT / 'kernel/patches' / name)], cwd=path,
                           check=True, capture_output=True, text=True)
        apply('linux-dsim-init-errors.patch')
        source = copy.read_text()
        wait = source[source.index('static int samsung_dsim_wait_for_reset('):
                      source.index('static void samsung_dsim_reset(')]
        def init(text):
            return text[text.index('static int samsung_dsim_init('):
                        text.index('static void samsung_dsim_atomic_pre_enable(')]
        baseline = init(source).replace('samsung_dsim_init(', 'baseline_init(', 1)
        apply('linux-dsim-zz-j701f-inherited-pll.patch')
        harness = path / 'init.c'
        harness.write_text(MOCK + wait + baseline + init(copy.read_text()) + MAIN)
        cls.binary = path / 'init'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', str(harness), '-o', str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def run_case(self, fixed=1, trial=1, inherited=1, failure=0, retry=0):
        fields = subprocess.check_output(
            [str(self.binary), *(str(x) for x in (fixed, trial, inherited, failure, retry))],
            text=True, env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0')).split()
        return [int(x) for x in fields[:9]], fields[9:]

    def test_baseline_reproduces_failure_then_successful_retry(self):
        result, trace = self.run_case(fixed=0, retry=1)
        self.assertEqual(result, [-14, 0, 0, 0, 0, 1, 1, 1, 0])
        self.assertEqual(trace, ['RICiD', 'RICiDRICWPL'])

    def test_inherited_clock_stops_before_reset_and_first_init_succeeds(self):
        result, trace = self.run_case()
        self.assertEqual(result, [0, 1, 1, 1, 0, 1, 1, 1, 1])
        self.assertEqual(trace, ['DRICWPL', 'DRICWPL'])

    def test_profile_off_is_identical_to_baseline_without_extra_mmio(self):
        for inherited in (0, 1):
            with self.subTest(inherited=inherited):
                self.assertEqual(self.run_case(trial=0, inherited=inherited),
                                 self.run_case(fixed=0, trial=0, inherited=inherited))

    def test_already_off_clock_is_not_disabled_again_and_success_is_idempotent(self):
        result, trace = self.run_case(inherited=0, retry=1)
        self.assertEqual(result, [0, 1, 1, 1, 0, 1, 1, 1, 1])
        self.assertEqual(trace, ['RICWPL', 'RICWPL'])

    def test_each_failure_still_unwinds_and_retries(self):
        for failure, error in ((1, -5), (2, -110), (3, -14)):
            with self.subTest(failure=failure):
                result, trace = self.run_case(failure=failure, retry=1)
                self.assertEqual(result, [error, 0, 0, 0, 0, 1, 1, 1, 2])
                self.assertTrue(trace[0].startswith('DRIC'))
                self.assertTrue(trace[0].endswith('iD'))
                self.assertTrue(trace[1].endswith('RICWPL'))


if __name__ == '__main__':
    unittest.main()
