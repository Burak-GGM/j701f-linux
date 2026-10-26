"""Exercise the actual panel power callbacks with failing host resources.

This verifies software ordering and rail accounting, not electrical behaviour.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_ea8061s_sequence import MOCK, SOURCE

RESOURCES = r'''
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
struct drm_panel { int unused; };
/* Claude 2026-10-10: stand-ins for the brightness code added to the driver. */
typedef uint16_t u16;
/* the backlight operations table is only referenced from probe, which is not compiled here */
#pragma clang diagnostic ignored "-Wunused-const-variable"
#define mipi_dsi_dcs_write_buffer_multi(ctx, buf, len) write_multi(ctx, buf, len)
struct mutex { int held; };
static void mutex_lock(struct mutex *m) { m->held++; }
static void mutex_unlock(struct mutex *m) { m->held--; }
struct backlight_device { struct { int brightness; } props; void *data; };
struct backlight_ops { int (*update_status)(struct backlight_device *); };
static void *bl_get_data(struct backlight_device *bl) { return bl->data; }
struct regulator { int id, count; };
struct gpio_desc { bool output; };
#define container_of(ptr, type, member) \
    ((type *)((char *)(ptr) - offsetof(type, member)))
static int resource_fail;
static char events[4096];
static size_t used;
static void event(const char *name, unsigned a, unsigned b)
{
    int n = snprintf(events + used, sizeof(events) - used, "%s:%u:%u,", name, a, b);
    assert(n > 0 && (size_t)n < sizeof(events) - used);
    used += (size_t)n;
}
static int regulator_enable(struct regulator *r)
{
    event("enable", r->id, 0);
    if (resource_fail == r->id) return -EIO;
    r->count++;
    return 0;
}
static int regulator_disable(struct regulator *r)
{
    event("disable", r->id, 0);
    assert(r->count == 1);
    r->count--;
    return 0;
}
static int gpiod_direction_output(struct gpio_desc *g, int value)
{
    event("direction", value, 0);
    if (resource_fail == 3) return -EIO;
    g->output = true;
    return 0;
}
static void gpiod_set_value_cansleep(struct gpio_desc *g, int value)
{
    assert(g->output);
    event("reset", value, 0);
}
static void usleep_range(unsigned a, unsigned b) { event("wait", a, b); }
static void msleep(unsigned a) { event("wait", a * 1000, a * 1000); }
#define dev_warn(...) ((void)0)
static void mipi_dsi_dcs_set_display_on_multi(struct mipi_dsi_multi_context *ctx)
{
    mipi_dsi_dcs_write_seq_multi(ctx, 0x29);
}
static int mipi_dsi_dcs_set_display_off(struct mipi_dsi_device *dsi)
{
    const u8 data[] = {0x28};
    return mipi_dsi_dcs_write_buffer(dsi, data, sizeof(data)) < 0 ? -EIO : 0;
}
static int mipi_dsi_dcs_enter_sleep_mode(struct mipi_dsi_device *dsi)
{
    const u8 data[] = {0x10};
    return mipi_dsi_dcs_write_buffer(dsi, data, sizeof(data)) < 0 ? -EIO : 0;
}
'''

LIFECYCLE_MAIN = r'''
int main(int argc, char **argv)
{
    assert(argc == 4);
    struct mipi_dsi_device dsi = {0};
    struct regulator io = {.id = 1}, ci = {.id = 2};
    struct gpio_desc reset = {0};
    struct j701f_ea8061s ctx = {.dsi = &dsi, .vddio = &io, .vci = &ci,
                               .reset = &reset};
    resource_fail = atoi(argv[1]);
    fail_at = atoi(argv[2]);
    int cycles = atoi(argv[3]);
    int prepare = 0, enable = 0, disable = 0, unprepare = 0;
    for (int i = 0; i < cycles; i++) {
        prepare = ea8061s_prepare(&ctx.panel);
        if (prepare) break;
        enable = ea8061s_enable(&ctx.panel);
        if (!enable) disable = ea8061s_disable(&ctx.panel);
        unprepare = ea8061s_unprepare(&ctx.panel);
    }
    printf("{\"prepare\":%d,\"enable\":%d,\"disable\":%d,\"unprepare\":%d,"
           "\"rails\":[%d,%d],\"calls\":%d,\"events\":\"%s\"}\n",
           prepare, enable, disable, unprepare, io.count, ci.count, calls, events);
    return 0;
}
'''


@unittest.skipUnless(shutil.which('clang'), 'host clang is required')
class PanelLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-panel-lifecycle-')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name)
        source = SOURCE.read_text()
        callbacks = source[source.index('struct j701f_ea8061s {'):
                           source.index('static const struct drm_display_mode')]
        harness = path / 'lifecycle.c'
        harness.write_text(MOCK + RESOURCES + callbacks + LIFECYCLE_MAIN)
        cls.binary = path / 'lifecycle'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', str(harness), '-o', str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def run_lifecycle(self, resource_fail=0, transfer_fail=0, cycles=1):
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
        return json.loads(subprocess.check_output(
            [str(self.binary), str(resource_fail), str(transfer_fail), str(cycles)],
            text=True, env=env))

    def test_ordered_power_reset_and_teardown(self):
        result = self.run_lifecycle()
        self.assertEqual([result[k] for k in ('prepare', 'enable', 'disable', 'unprepare')],
                         [0, 0, 0, 0])
        self.assertEqual(result['rails'], [0, 0])
        self.assertTrue(result['events'].startswith(
            'enable:1:0,enable:2:0,wait:25000:25000,direction:0:0,'
            'wait:5000:6000,reset:1:0,wait:5000:6000,reset:0:0,wait:10000:11000,'))
        self.assertTrue(result['events'].endswith(
            'wait:20000:21000,wait:100000:100000,wait:5000:6000,'
            'reset:1:0,wait:10000:11000,disable:2:0,disable:1:0,'))
        self.assertEqual(result['calls'], 25)

    def test_resource_failures_leave_no_rail_reference(self):
        for failure in (1, 2, 3):
            with self.subTest(resource=failure):
                result = self.run_lifecycle(resource_fail=failure)
                self.assertEqual(result['prepare'], -5)
                self.assertEqual(result['rails'], [0, 0])
                self.assertEqual(result['calls'], 0)

    def test_every_init_transfer_failure_powers_down(self):
        for failure in range(1, 20):
            with self.subTest(transfer=failure):
                result = self.run_lifecycle(transfer_fail=failure)
                self.assertEqual(result['prepare'], -5)
                self.assertEqual(result['rails'], [0, 0])
                self.assertTrue(result['events'].endswith('disable:2:0,disable:1:0,'))

    def test_enable_transfer_failures_can_unprepare(self):
        for failure in range(20, 24):
            with self.subTest(transfer=failure):
                result = self.run_lifecycle(transfer_fail=failure)
                self.assertEqual(result['prepare'], 0)
                self.assertEqual(result['enable'], -5)
                self.assertEqual(result['unprepare'], 0)
                self.assertEqual(result['rails'], [0, 0])

    def test_sleep_error_still_completes_power_off(self):
        result = self.run_lifecycle(transfer_fail=25)
        self.assertEqual(result['unprepare'], 0)
        self.assertEqual(result['rails'], [0, 0])

    def test_repeated_cycles_balance_rails(self):
        result = self.run_lifecycle(cycles=2)
        self.assertEqual(result['calls'], 50)
        self.assertEqual(result['rails'], [0, 0])


if __name__ == '__main__':
    unittest.main()
