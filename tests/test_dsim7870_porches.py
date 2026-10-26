"""Compare the actual common DSIM routine with the unapplied porch candidate.

Requires the prepared source snapshot documented in docs/j701f-display.md.
Checks register programming on the host; does not validate link timing.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'build/kernel/ea8061s-prototype/reference/mainline/samsung-dsim.c'
PATCH = ROOT / 'kernel/patches/linux-dsim-j701f-timing-trial.patch'

MOCK = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <errno.h>
typedef uint64_t u64;
typedef uint32_t u32;
struct drm_display_mode {
    int clock, hdisplay, hsync_start, hsync_end, htotal;
    int vdisplay, vsync_start, vsync_end, vtotal, flags;
};
struct driver_data { unsigned num_bits_resol, main_vsa_offset; };
struct plat_data { int hw_type; };
struct samsung_dsim {
    struct drm_display_mode mode;
    struct driver_data *driver_data;
    struct plat_data *plat_data;
    uint64_t hs_clock;
};
#define DSIM_TYPE_EXYNOS7870 7870
#define DSIM_TYPE_IMX8MM 8000
#define DSIM_TYPE_IMX8MP 8001
#define DRM_MODE_FLAG_NHSYNC 1
#define DRM_MODE_FLAG_NVSYNC 2
#define DRM_MODE_FLAG_PHSYNC 4
#define DRM_MODE_FLAG_PVSYNC 8
struct drm_bridge { struct samsung_dsim *dsi; };
struct drm_bridge_state { int unused; };
struct drm_connector_state { int unused; };
struct drm_crtc_state { struct drm_display_mode adjusted_mode; };
#define bridge_to_dsi(b) ((b)->dsi)
static bool j701f_vendor_timing, mock_board;
#define of_machine_is_compatible(x) (mock_board)
#define MIPI_DSI_MODE_VIDEO 1
#define DIV64_U64_ROUND_UP(a, b) (((a) + (b) - 1) / (b))
#define max(a, b) ((a) > (b) ? (a) : (b))
#define dev_dbg(...) ((void)0)
#define DSIM_CMD_ALLOW(x) ((u32)(x) << 28)
#define DSIM_STABLE_VFP(x) ((u32)(x) << 16)
#define DSIM_MAIN_VBP(x) ((u32)(x))
#define DSIM_MAIN_HFP(x) ((u32)(x) << 16)
#define DSIM_MAIN_HBP(x) ((u32)(x))
#define DSIM_MAIN_VSA(x, shift) ((u32)(x) << (shift))
#define DSIM_MAIN_HSA(x) ((u32)(x))
#define DSIM_MAIN_HRESOL(x, bits) ((u32)(x) & ((1U << (bits)) - 1))
#define DSIM_MAIN_VRESOL(x, bits) (DSIM_MAIN_HRESOL(x, bits) << 16)
enum {DSIM_MVPORCH_REG, DSIM_MHPORCH_REG, DSIM_MSYNC_REG, DSIM_MDRESOL_REG};
static u32 regs[4];
static void samsung_dsim_write(struct samsung_dsim *dsi, unsigned index, u32 val)
{
    (void)dsi;
    assert(index < 4);
    regs[index] = val;
}
'''

MAIN = r'''
int main(int argc, char **argv)
{
    assert(argc == 5);
    struct driver_data driver = {12, 16};
    struct plat_data plat = {atoi(argv[1])};
    struct samsung_dsim dsi = {
        .mode = {64385, 720, 776, 780, 828, 1280, 1289, 1291, 1296, 0},
        .driver_data = &driver, .plat_data = &plat, .hs_clock = 476666666,
        .mode_flags = MIPI_DSI_MODE_VIDEO,
        .lanes = 4,
    };
    j701f_vendor_timing = atoi(argv[2]); mock_board = atoi(argv[3]);
    int vfp = atoi(argv[4]);
    dsi.mode.vsync_start = 1280 + vfp;
    dsi.mode.vsync_end = dsi.mode.vsync_start + 2;
    dsi.mode.vtotal = dsi.mode.vsync_end + 5;
    struct drm_crtc_state crtc = {.adjusted_mode = dsi.mode};
    struct drm_bridge bridge = {.dsi = &dsi};
    int ret = samsung_dsim_atomic_check(&bridge, NULL, &crtc, NULL);
    if (!ret) {
        dsi.mode = crtc.adjusted_mode;
        samsung_dsim_set_display_mode(&dsi);
    }
    printf("%08x %08x %08x %08x %d\n", regs[0], regs[1], regs[2], regs[3], ret);
}
'''


@unittest.skipUnless(SOURCE.is_file() and shutil.which('clang') and shutil.which('patch'),
                     'prepared DSIM source snapshot, clang and patch are required')
class DsimPorchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='j701f-dsim-porches-')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name)
        copy = path / 'drivers/gpu/drm/bridge/samsung-dsim.c'
        copy.parent.mkdir(parents=True)
        copy.write_text(SOURCE.read_text())
        original = copy.read_text()
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(PATCH)],
                       cwd=path, check=True, capture_output=True, text=True)
        cls.binaries = []
        for name, source in [('current', original), ('candidate', copy.read_text())]:
            function = source[source.index('static void samsung_dsim_set_display_mode('):
                              source.index('static void samsung_dsim_set_display_enable(')]
            atomic = source[source.index('static int samsung_dsim_atomic_check('):
                            source.index('static void samsung_dsim_mode_set(')]
            helper = ''
            if name == 'candidate':
                helper = source[source.index('static bool samsung_dsim_j701f_trial('):
                                source.index('/* returns true iff')]
            cfile = path / (name + '.c')
            # The actual routine also needs the mode flag member.
            mock = MOCK.replace('uint64_t hs_clock;',
                                'uint64_t hs_clock; unsigned mode_flags, lanes;')
            cfile.write_text(mock + helper + function + atomic + MAIN)
            binary = path / name
            subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-parameter',
                            # The unpatched routine leaves the mock's board globals
                            # unread; clang 23 reports that as an error under -Werror.
                            '-Wno-unknown-warning-option', '-Wno-unused-but-set-global',
                            '-fsanitize=address,undefined', str(cfile), '-o', str(binary)],
                           check=True, capture_output=True, text=True)
            cls.binaries.append(binary)

    def registers(self, candidate, hw_type=7870, enabled=1, board=1, vfp=9):
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
        output = subprocess.check_output([str(self.binaries[candidate]), str(hw_type),
                                          str(enabled), str(board), str(vfp)],
                                         text=True, env=env)
        words = output.split()
        return [int(word, 16) for word in words[:4]] + [int(words[4])]

    def test_candidate_matches_captured_horizontal_counts(self):
        current = self.registers(0, 7870)
        candidate = self.registers(1, 7870)
        self.assertEqual(current[1:3], [0x002e0027, 0x00020000])
        self.assertEqual(candidate[1:3], [0x00380030, 0x00020004])
        self.assertEqual(candidate[3], 0x050002d0)
        self.assertEqual(candidate[4], 0)

    def test_other_hardware_keeps_common_conversion(self):
        self.assertEqual(self.registers(0, 5433), self.registers(1, 5433))

    def test_candidate_matches_captured_vertical_programming(self):
        self.assertEqual(self.registers(0)[0], 0xf0090005)
        self.assertEqual(self.registers(1)[0], 0x60010005)

    def test_profile_off_by_default_and_restricted_to_board(self):
        for enabled, board in ((0, 1), (1, 0), (0, 0)):
            with self.subTest(enabled=enabled, board=board):
                self.assertEqual(self.registers(1, enabled=enabled, board=board),
                                 self.registers(0))

    def test_invalid_command_budgets_rejected_before_programming(self):
        for vfp in (0, 1, 2, 19, 21):
            with self.subTest(vfp=vfp):
                self.assertEqual(self.registers(1, vfp=vfp), [0, 0, 0, 0, -22])

    def test_valid_command_budget_boundaries(self):
        for vfp, command in ((3, 0), (9, 6), (18, 15)):
            with self.subTest(vfp=vfp):
                values = self.registers(1, vfp=vfp)
                self.assertEqual(values[4], 0)
                self.assertEqual(values[0], (command << 28) | (1 << 16) | 5)


if __name__ == '__main__':
    unittest.main()
