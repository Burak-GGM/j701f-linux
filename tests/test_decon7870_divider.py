"""Execute the actual DECON commit routine against mock MMIO, no phone access.

Needs the prepared mainline source/header snapshots in the display reference
directory. The staged patch is deliberately not part of automatic kernel builds.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'build/kernel/ea8061s-prototype/reference/mainline'
PATCH = ROOT / 'kernel/patches/staged/linux-decon7870-vclkdiv.patch'

MOCK = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include "regs-decon7.h"
typedef uint32_t u32;
#define DIV_ROUND_UP(a,b) (((a)+(b)-1)/(b))
struct clk { unsigned long rate; };
static unsigned long clk_get_rate(struct clk *c) { return c->rate; }
static u32 readl(const void *p) { return *(const u32 *)p; }
static void writel(u32 v, void *p) { *(u32 *)p=v; }
struct drm_display_mode {
    int clock, hdisplay, vdisplay, htotal, vtotal;
    int crtc_vsync_end, crtc_vsync_start, crtc_vtotal, crtc_vdisplay;
    int crtc_hsync_end, crtc_hsync_start, crtc_htotal, crtc_hdisplay;
};
struct crtc_state { struct drm_display_mode adjusted_mode; };
struct exynos_drm_crtc { void *ctx; struct { struct crtc_state *state; } base; };
struct decon_context {
    void *regs; struct clk *vclk; bool i80_if; struct exynos_drm_crtc *crtc;
    const struct decon_data *data;
};
'''

MAIN = r'''
int main(int argc, char **argv) {
    assert(argc==4);
    _Alignas(4) unsigned char mmio[0x800]={0};
    struct clk clk={strtoul(argv[2],NULL,10)};
    struct crtc_state state={.adjusted_mode={
        .clock=64385, .hdisplay=720, .vdisplay=1280, .htotal=828, .vtotal=1296,
        .crtc_vsync_start=1289, .crtc_vsync_end=1291, .crtc_vtotal=1296, .crtc_vdisplay=1280,
        .crtc_hsync_start=776, .crtc_hsync_end=780, .crtc_htotal=828, .crtc_hdisplay=720,
    }};
    if (atoi(argv[3])) state.adjusted_mode.htotal=0;
    struct exynos_drm_crtc crtc={.base={.state=&state}};
    struct decon_context ctx={.regs=mmio,.vclk=&clk,.crtc=&crtc,
        .data=atoi(argv[1]) ? &exynos7870_decon_data : &exynos7_decon_data};
    crtc.ctx=&ctx;
    decon_commit(&crtc);
    unsigned offsets[]={VCLKCON1,VCLKCON2,VIDTCON0,VIDTCON1,VIDTCON2,VIDTCON3,VIDTCON4,
                        LINECNT_OP_THRESHOLD,VIDCON0,DECON_UPDATE};
    for(unsigned i=0;i<sizeof(offsets)/sizeof(offsets[0]);i++)
        printf("%08x ",readl(mmio+offsets[i]));
    puts("");
}
'''


@unittest.skipUnless((REFERENCE / 'exynos7_drm_decon.c').is_file()
                     and (REFERENCE / 'regs-decon7.h').is_file()
                     and shutil.which('clang') and shutil.which('patch'),
                     'prepared DECON source/header, clang and patch required')
class DeconDividerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-decon-div-')
        cls.addClassCleanup(cls.tmp.cleanup)
        work = Path(cls.tmp.name)
        source = work / 'drivers/gpu/drm/exynos/exynos7_drm_decon.c'
        source.parent.mkdir(parents=True)
        original = (REFERENCE / source.name).read_text()
        source.write_text(original)
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(PATCH)],
                       cwd=work, check=True, capture_output=True, text=True)
        shutil.copy2(REFERENCE / 'regs-decon7.h', work)
        cls.binaries = []
        for name, text in [('original', original), ('candidate', source.read_text())]:
            data = text[text.index('struct decon_data {'):text.index('struct decon_context {')]
            routines = text[text.index('static u32 decon_calc_clkdiv('):
                            text.index('static int decon_enable_vblank(')]
            cfile, binary = work / (name + '.c'), work / name
            cfile.write_text(MOCK + data + routines + MAIN)
            subprocess.run(['clang', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            '-fsanitize=address,undefined', str(cfile), '-o', str(binary)],
                           check=True, capture_output=True, text=True)
            cls.binaries.append(binary)

    def registers(self, patched, soc=1, rate=64000000, unset=0):
        output = subprocess.check_output([str(self.binaries[patched]), str(soc), str(rate), str(unset)],
                                         env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0'), text=True)
        return [int(word, 16) for word in output.split()]

    def test_measured_clock_divide_one_is_unchanged(self):
        self.assertEqual(self.registers(0), self.registers(1))
        self.assertEqual(self.registers(1)[:2], [0, 0])

    def test_7870_divider_field_matches_vendor_definition(self):
        self.assertEqual(self.registers(0, rate=128770000)[:2], [1, 1])
        self.assertEqual(self.registers(1, rate=128770000)[:2], [0x10000, 0x10000])

    def test_other_soc_keeps_low_field(self):
        for rate in (64000000, 128770000, 2000000000000):
            with self.subTest(rate=rate):
                self.assertEqual(self.registers(0, soc=0, rate=rate),
                                 self.registers(1, soc=0, rate=rate))

    def test_clamp_stays_inside_eight_bit_field(self):
        self.assertEqual(self.registers(1, rate=2000000000000)[:2], [0xfe0000, 0xfe0000])

    def test_timings_match_readonly_firmware_snapshot(self):
        self.assertEqual(self.registers(1)[2:],
                         [0x40008, 0x10000, 0x2f0037, 0x30000, 0x4ff02cf, 1279, 3, 1])

    def test_unset_mode_does_not_write_mmio(self):
        self.assertEqual(self.registers(1, unset=1), [0] * 10)


if __name__ == '__main__':
    unittest.main()
