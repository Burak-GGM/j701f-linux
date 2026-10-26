"""Inject host-init failures into the actual DSIM callback and retry it."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'build/kernel/ea8061s-prototype/reference/mainline/samsung-dsim.c'
STAGED = ROOT / 'kernel/patches/staged/linux-dsim-init-errors.patch'
ACTIVE = ROOT / 'kernel/patches/linux-dsim-init-errors.patch'

MOCK = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#define DSIM_STATE_INITIALIZED 1
#define DSIM_FUNCRST 2
#define RESET_TYPE 0
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
static int failure, irq_depth, calls;
static bool clock_on;
static unsigned long wait_for_completion_timeout(struct completion *c, unsigned long t)
{
    (void)c; (void)t; calls++;
    return failure == 2 ? 0 : 1;
}
static void samsung_dsim_reset(struct samsung_dsim *dsi) { (void)dsi; calls++; }
static void samsung_dsim_enable_irq(struct samsung_dsim *dsi)
{
    (void)dsi; calls++; assert(irq_depth == 0); irq_depth++;
}
static void samsung_dsim_disable_irq(struct samsung_dsim *dsi)
{
    (void)dsi; calls++; assert(irq_depth == 1); irq_depth--;
}
static void samsung_dsim_enable_lane(struct samsung_dsim *dsi, unsigned lanes)
{
    (void)dsi; assert(lanes == 15); calls++;
}
static int samsung_dsim_enable_clock(struct samsung_dsim *dsi)
{
    (void)dsi; calls++; clock_on = true; /* model partial setup on failure */
    return failure == 1 ? -EIO : 0;
}
static void samsung_dsim_disable_clock(struct samsung_dsim *dsi)
{
    (void)dsi; calls++; assert(clock_on); clock_on = false;
}
static void samsung_dsim_set_phy_ctrl(struct samsung_dsim *dsi) { (void)dsi; calls++; }
static int samsung_dsim_init_link(struct samsung_dsim *dsi)
{
    (void)dsi; calls++;
    return failure == 3 ? -EFAULT : 0;
}
'''

MAIN = r'''
int main(int argc, char **argv)
{
    assert(argc == 4);
    failure = atoi(argv[1]);
    bool retry = atoi(argv[2]);
    struct samsung_dsim_driver_data data = {{atoi(argv[3])}, true};
    struct samsung_dsim dsi = {.driver_data = &data, .lanes = 4};
    int first = samsung_dsim_init(&dsi);
    unsigned first_state = dsi.state;
    int first_irq = irq_depth;
    bool first_clock = clock_on;
    int second = 0;
    if (retry) {
        int before = calls;
        failure = 0;
        second = samsung_dsim_init(&dsi);
        if (first == 0) assert(calls == before); /* idempotent */
    }
    printf("%d %u %d %d %d %u %d %d\n", first, first_state, first_irq,
           first_clock, second, dsi.state, irq_depth, clock_on);
}
'''


@unittest.skipUnless(SOURCE.is_file() and shutil.which('clang') and shutil.which('patch'),
                     'prepared DSIM source snapshot, clang and patch are required')
class DsimInitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-dsim-init-')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name)
        copy = path / 'drivers/gpu/drm/bridge/samsung-dsim.c'
        copy.parent.mkdir(parents=True)
        copy.write_text(SOURCE.read_text())
        patch = STAGED if STAGED.is_file() else ACTIVE
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)],
                       cwd=path, check=True, capture_output=True, text=True)
        source = copy.read_text()
        wait = source[source.index('static int samsung_dsim_wait_for_reset('):
                      source.index('static void samsung_dsim_reset(')]
        init = source[source.index('static int samsung_dsim_init('):
                      source.index('static void samsung_dsim_atomic_pre_enable(')]
        harness = path / 'init.c'
        harness.write_text(MOCK + wait + init + MAIN)
        cls.binary = path / 'init'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', str(harness), '-o', str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def run_case(self, failure=0, retry=0, reset_type=0):
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
        return [int(word) for word in subprocess.check_output(
            [str(self.binary), str(failure), str(retry), str(reset_type)],
            text=True, env=env).split()]

    def test_success_and_idempotent_second_init(self):
        self.assertEqual(self.run_case(retry=1), [0, 1, 1, 1, 0, 1, 1, 1])

    def test_original_errors_propagate_and_resources_unwind(self):
        for failure, error in ((1, -5), (2, -110), (3, -14)):
            with self.subTest(failure=failure):
                self.assertEqual(self.run_case(failure), [error, 0, 0, 0, 0, 0, 0, 0])

    def test_retry_after_each_failure_balances_irq_and_clocks(self):
        for failure, error in ((1, -5), (2, -110), (3, -14)):
            with self.subTest(failure=failure):
                self.assertEqual(self.run_case(failure, retry=1),
                                 [error, 0, 0, 0, 0, 1, 1, 1])

    def test_functional_reset_path_also_unwinds_and_retries(self):
        self.assertEqual(self.run_case(1, retry=1, reset_type=2),
                         [-5, 0, 0, 0, 0, 1, 1, 1])


if __name__ == '__main__':
    unittest.main()
