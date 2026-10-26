"""Run the existing DSIM PLL search, retaining its actual 7870 limits."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'build/kernel/ea8061s-prototype/reference/mainline/samsung-dsim.c'

MOCK = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define HZ_PER_MHZ 1000000UL
#define DIV_ROUND_UP(a, b) (((a) + (b) - 1) / (b))
#define do_div(a, b) ((a) /= (b))
#define abs(x) labs((long)(x))
struct samsung_dsim_driver_data {
    unsigned pll_fin_min, pll_fin_max, m_min, m_max, min_freq, max_freq;
};
struct samsung_dsim { struct samsung_dsim_driver_data *driver_data; };
'''

MAIN = r'''
int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    struct samsung_dsim_driver_data data = LIMITS;
    struct samsung_dsim dsi = {.driver_data = &data};
    u8 p = 0, s = 0; u16 m = 0;
    unsigned long rate = samsung_dsim_pll_find_pms(&dsi, strtoul(argv[1], NULL, 0),
                                                 strtoul(argv[2], NULL, 0), &p, &m, &s);
    printf("%lu %u %u %u\n", rate, p, m, s);
}
'''


@unittest.skipUnless(SOURCE.is_file() and shutil.which('clang'),
                     'prepared DSIM source snapshot and clang are required')
class DsimPllSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-dsim-pll-search-')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name)
        source = SOURCE.read_text()
        function = source[source.index('static unsigned long samsung_dsim_pll_find_pms('):
                          source.index('static unsigned long samsung_dsim_set_pll(')]
        data = source[source.index('static const struct samsung_dsim_driver_data '
                                   'exynos7870_dsi_driver_data = {'):]
        data = data[:data.index('};')]
        keys = ('pll_fin_min', 'pll_fin_max', 'm_min', 'm_max', 'min_freq', 'max_freq')
        cls.limits = {key: int(re.search(r'\.' + key + r'\s*=\s*(\d+)', data)[1])
                      for key in keys}
        values = '{' + ','.join(str(cls.limits[key]) for key in keys) + '}'
        harness = path / 'pll.c'
        harness.write_text(MOCK + function + MAIN.replace('LIMITS', values))
        cls.binary = path / 'pll'
        subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', str(harness), '-o', str(cls.binary)],
                       check=True, capture_output=True, text=True)

    def search(self, fin, target):
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
        return [int(word) for word in subprocess.check_output(
            [str(self.binary), str(fin), str(target)], text=True, env=env).split()]

    def test_j701f_rate_with_existing_limits(self):
        self.assertEqual(self.search(26000000, 477000000), [476666666, 3, 110, 1])
        # Firmware's 220/2 and selected 110/1 have the same ratio. This proves
        # frequency arithmetic only, not equal analogue jitter or link stability.
        self.assertEqual(220 / (1 << 2), 110 / (1 << 1))

    def test_selected_dividers_respect_unchanged_limits(self):
        for target in (343000000, 477000000, 1001000000):
            with self.subTest(target=target):
                rate, p, m, s = self.search(26000000, target)
                self.assertGreaterEqual(m, self.limits['m_min'])
                self.assertLessEqual(m, self.limits['m_max'])
                self.assertGreaterEqual(26000000 / p, self.limits['pll_fin_min'] * 1000000)
                self.assertLessEqual(26000000 / p, self.limits['pll_fin_max'] * 1000000)
                vco = 26000000 * m / p
                self.assertGreaterEqual(vco, self.limits['min_freq'] * 1000000)
                self.assertLessEqual(vco, self.limits['max_freq'] * 1000000)
                self.assertEqual(rate, 26000000 * m // (p << s))
                self.assertLess(abs(rate - target), target // 100)

    def test_no_solution_leaves_output_dividers_untouched(self):
        for fin, target in ((5000000, 477000000), (26000000, 0)):
            with self.subTest(fin=fin, target=target):
                self.assertEqual(self.search(fin, target), [0, 0, 0, 0])


if __name__ == '__main__':
    unittest.main()
