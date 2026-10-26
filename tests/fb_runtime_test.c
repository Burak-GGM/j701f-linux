/* Simulated driver operations: never opens or changes any host display. */
#define FB_RUNTIME_TEST
#include "../tools/fb-heartbeat.c"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static struct fb_var_screeninfo current, original;
static struct fb_fix_screeninfo fixed;
static unsigned mode_sets, queries, maps, pans;
static int fail_blank, fail_put, shrink_after_put;
static unsigned char pixels[64*64*4];

static void reset_driver(void)
{
    memset(&current, 0, sizeof(current));
    memset(&fixed, 0, sizeof(fixed));
    current.xres = current.xres_virtual = 64;
    current.yres = current.yres_virtual = 64;
    current.bits_per_pixel = 32;
    current.red = (struct fb_bitfield){16,8,0};
    current.green = (struct fb_bitfield){8,8,0};
    current.blue = (struct fb_bitfield){0,8,0};
    current.pixclock = 15531;
    current.left_margin = 48; current.right_margin = 56;
    original = current;
    fixed.line_length = 64*4; fixed.smem_len = sizeof(pixels);
    mode_sets = queries = maps = pans = 0;
    fail_blank = fail_put = shrink_after_put = 0;
    memset(pixels, 0, sizeof(pixels));
}

static long call(long number, long a, long b, long c, long d, long e, long f)
{
    (void)d; (void)e; (void)f;
    if (number == A64_WRITE || number == A64_NANOSLEEP) return 0;
    if (number == A64_OPENAT) return 7;
    if (number == A64_MMAP) {
        assert(mode_sets == 1 && queries == 4);
        assert(b == sizeof(pixels));
        maps++;
        return (long)pixels;
    }
    assert(number == A64_IOCTL && a == 7);
    if (b == FBIOGET_VSCREENINFO) {
        *(struct fb_var_screeninfo *)c = current; queries++; return 0;
    }
    if (b == FBIOGET_FSCREENINFO) {
        *(struct fb_fix_screeninfo *)c = fixed; queries++; return 0;
    }
    if (b == FBIOBLANK) { assert(c == FB_BLANK_UNBLANK); return fail_blank ? -5 : 0; }
    if (b == FBIOPUT_VSCREENINFO) {
        struct fb_var_screeninfo requested = *(struct fb_var_screeninfo *)c;
        assert(requested.activate == (FB_ACTIVATE_NOW | FB_ACTIVATE_FORCE));
        requested.activate = original.activate;
        assert(memcmp(&requested, &original, sizeof(requested)) == 0);
        mode_sets++;
        if (fail_put) return -22;
        /* Observed phone transition after mode activation. */
        fixed.visual = FB_VISUAL_TRUECOLOR;
        current.transp = (struct fb_bitfield){24,8,0};
        if (shrink_after_put) fixed.smem_len = 4;
        return 0;
    }
    assert(b == FBIOPAN_DISPLAY && maps == 1);
    assert(((struct fb_var_screeninfo *)c)->transp.length == 8);
    assert(((struct fb_var_screeninfo *)c)->red.offset == 16);
    assert(((struct fb_var_screeninfo *)c)->blue.offset == 0);
    pans++; return 0;
}

int main(void)
{
    char *info[] = {"fb-heartbeat", "--info", "/dev/fb0"};
    char *test[] = {"fb-heartbeat", "--test", "/dev/fb0"};
    char *swapped[] = {"fb-heartbeat", "--test-swap-rb", "/dev/fb0"};
    reset_driver();
    assert(run(3, info) == 0 && mode_sets == 0 && maps == 0 && pans == 0);
    reset_driver();
    assert(run(3, test) == 0 && mode_sets == 1 && maps == 1 && pans == 6);
    for (unsigned i = 3; i < sizeof(pixels); i += 4) assert(pixels[i] == 255);
    assert(pixels[0] == 0 && pixels[1] == 220 && pixels[2] == 110);
    reset_driver();
    assert(run(3, swapped) == 0 && mode_sets == 1 && maps == 1 && pans == 6);
    assert(pixels[0] == 0 && pixels[1] == 220 && pixels[2] == 110 && pixels[3] == 255);
    reset_driver(); fail_blank = 1;
    assert(run(3, test) == 1 && mode_sets == 0 && maps == 0);
    reset_driver(); fail_put = 1;
    assert(run(3, test) == 1 && maps == 0);
    reset_driver(); shrink_after_put = 1;
    assert(run(3, test) == 1 && maps == 0 && pans == 0);
    printf("PASS: read-only probe, current-mode preservation, re-query bounds, opaque alpha and activation failures\n");
    return 0;
}
