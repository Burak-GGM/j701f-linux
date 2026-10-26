/* Direct framebuffer proof of userspace life. No libc, disk I/O, or fixed geometry.
 * Linux framebuffer UAPI from linux/fb.h; AArch64 syscall ABI numbers below.
 */
#include <linux/fb.h>
/* AArch64 Linux asm-generic/unistd.h ABI. Do not use host asm/unistd.h. */
enum { A64_IOCTL=29, A64_OPENAT=56, A64_WRITE=64, A64_EXIT_GROUP=94,
       A64_NANOSLEEP=101, A64_MMAP=222 };

_Static_assert(sizeof(struct fb_var_screeninfo) == 160, "Unexpected framebuffer UAPI");
_Static_assert(sizeof(struct fb_fix_screeninfo) == 80, "Requires LP64 framebuffer UAPI");

typedef unsigned long usize;

static int samsung_xrgb_quirk(const struct fb_var_screeninfo *v, const struct fb_fix_screeninfo *f)
{
    /* Measured on this j701f: visual is left at zero while RGB bitfields are valid.
     * Accept only that exact XRGB8888 format. All geometry/bounds checks still run.
     */
    return f->visual == 0 && f->type == FB_TYPE_PACKED_PIXELS && v->bits_per_pixel == 32 &&
           v->red.offset == 16 && v->red.length == 8 && !v->red.msb_right &&
           v->green.offset == 8 && v->green.length == 8 && !v->green.msb_right &&
           v->blue.offset == 0 && v->blue.length == 8 && !v->blue.msb_right &&
           v->transp.length == 0;
}

static const char *layout_error(const struct fb_var_screeninfo *v, const struct fb_fix_screeninfo *f)
{
    if (!v->xres || !v->yres || v->xres > 8192 || v->yres > 8192)
        return "invalid visible resolution";
    if (v->bits_per_pixel != 16 && v->bits_per_pixel != 24 && v->bits_per_pixel != 32)
        return "unsupported bits_per_pixel (expected 16, 24 or 32)";
    if (f->type != FB_TYPE_PACKED_PIXELS) return "framebuffer type is not packed pixels";
    if (f->visual != FB_VISUAL_TRUECOLOR && !samsung_xrgb_quirk(v, f))
        return "framebuffer visual is not truecolor";
    if (!f->smem_len || f->smem_len > 128UL * 1024 * 1024)
        return "framebuffer allocation is zero or exceeds 128 MiB";
    const struct fb_bitfield *fields[] = { &v->red, &v->green, &v->blue, &v->transp };
    unsigned mask = 0;
    for (unsigned i = 0; i < 4; i++) {
        const struct fb_bitfield *b = fields[i];
        if (!b->length && i == 3) continue;
        if (!b->length || b->length > 8 || b->offset >= v->bits_per_pixel ||
            b->offset + b->length > v->bits_per_pixel || b->msb_right)
            return "invalid color bitfield (length, offset or msb_right)";
        unsigned m = ((1U << b->length) - 1) << b->offset;
        if (m & mask) return "overlapping color bitfields";
        mask |= m;
    }
    usize row_end = ((usize)v->xoffset + v->xres) * (v->bits_per_pixel / 8);
    usize end = ((usize)v->yoffset + v->yres - 1) * f->line_length + row_end;
    if (row_end > f->line_length) return "visible row exceeds line_length";
    if (end > f->smem_len) return "visible area exceeds framebuffer allocation";
    return 0;
}

static int valid_layout(const struct fb_var_screeninfo *v, const struct fb_fix_screeninfo *f)
{
    return layout_error(v, f) == 0;
}

static unsigned component(unsigned value, struct fb_bitfield field)
{
    return field.length ? ((value * ((1U << field.length) - 1) / 255) << field.offset) : 0;
}

static unsigned color(const struct fb_var_screeninfo *v, unsigned r, unsigned g, unsigned b)
{
    return component(r, v->red) | component(g, v->green) | component(b, v->blue) |
           component(255, v->transp); /* Opaque alpha matters for Samsung scanout. */
}

static void swap_red_blue(struct fb_var_screeninfo *render_mode)
{
    /* Change only the renderer's interpretation, never the driver's mode. */
    struct fb_bitfield red = render_mode->red;
    render_mode->red = render_mode->blue;
    render_mode->blue = red;
}

static int j701f_scanout_swap(const struct fb_var_screeninfo *v, const struct fb_fix_screeninfo *f)
{
    /* Hardware confirmed: this activated Samsung ARGB declaration scans out
     * with red/blue exchanged. Scope correction to the measured format. */
    return f->type == FB_TYPE_PACKED_PIXELS && f->visual == FB_VISUAL_TRUECOLOR &&
           v->bits_per_pixel == 32 && v->red.offset == 16 && v->red.length == 8 &&
           !v->red.msb_right && v->green.offset == 8 && v->green.length == 8 &&
           !v->green.msb_right && v->blue.offset == 0 && v->blue.length == 8 &&
           !v->blue.msb_right && v->transp.offset == 24 && v->transp.length == 8 &&
           !v->transp.msb_right;
}

static void pixel(unsigned char *map, const struct fb_var_screeninfo *v,
                  const struct fb_fix_screeninfo *f, unsigned x, unsigned y, unsigned c)
{
    if (x >= v->xres || y >= v->yres) return;
#ifdef FB_PIXEL_TRACE
    FB_PIXEL_TRACE(x,y);
#endif
    usize index = ((usize)y + v->yoffset) * f->line_length +
                  ((usize)x + v->xoffset) * (v->bits_per_pixel / 8);
    for (unsigned byte = 0; byte < v->bits_per_pixel / 8; byte++)
        map[index + byte] = (unsigned char)(c >> (8 * byte));
}

/* Original 5x7 uppercase glyphs: each row's low five bits run left to right. */
static const unsigned char alphabet[26][7] = {
    {14,17,17,31,17,17,17}, {30,17,17,30,17,17,30}, {14,17,16,16,16,17,14},
    {30,17,17,17,17,17,30}, {31,16,16,30,16,16,31}, {31,16,16,30,16,16,16},
    {14,17,16,23,17,17,15}, {17,17,17,31,17,17,17}, {31,4,4,4,4,4,31},
    {7,2,2,2,18,18,12}, {17,18,20,24,20,18,17}, {16,16,16,16,16,16,31},
    {17,27,21,21,17,17,17}, {17,25,21,19,17,17,17}, {14,17,17,17,17,17,14},
    {30,17,17,30,16,16,16}, {14,17,17,17,21,18,13}, {30,17,17,30,20,18,17},
    {15,16,16,14,1,1,30}, {31,4,4,4,4,4,4}, {17,17,17,17,17,17,14},
    {17,17,17,17,17,10,4}, {17,17,17,21,21,21,10}, {17,17,10,4,10,17,17},
    {17,17,10,4,4,4,4}, {31,1,2,4,8,16,31}
};

static void text_line(unsigned char *map, const struct fb_var_screeninfo *v,
                      const struct fb_fix_screeninfo *f, const char *s, unsigned y, unsigned scale)
{
    unsigned len = 0;
    while (s[len]) len++;
    unsigned width = len * 6 * scale;
    unsigned x = v->xres > width ? (v->xres - width) / 2 : 0;
    unsigned white = color(v, 255, 255, 255);
    for (; *s; s++, x += 6 * scale) {
        if (*s < 'A' || *s > 'Z') continue;
        const unsigned char *rows = alphabet[*s - 'A'];
        for (unsigned r = 0; r < 7; r++)
            for (unsigned c = 0; c < 5; c++)
                if (rows[r] & (16 >> c))
                    for (unsigned sy = 0; sy < scale; sy++)
                        for (unsigned sx = 0; sx < scale; sx++)
                            pixel(map, v, f, x+c*scale+sx, y+r*scale+sy, white);
    }
}

static void draw(unsigned char *map, const struct fb_var_screeninfo *v,
                 const struct fb_fix_screeninfo *f, unsigned tick)
{
    unsigned background = color(v, 4, 18, 28);
    unsigned pulse = (tick & 1) ? color(v, 0, 220, 110) : color(v, 0, 120, 230);
    unsigned bar = v->yres / 8;
    for (unsigned y = 0; y < v->yres; y++)
        for (unsigned x = 0; x < v->xres; x++)
            pixel(map, v, f, x, y, y < bar ? pulse : background);
    unsigned scale = v->xres / 108;
    if (scale > v->yres / 70) scale = v->yres / 70;
    if (!scale) scale = 1;
    text_line(map, v, f, "BURAK LINUX", v->yres/3, scale);
    text_line(map, v, f, "INIT IS RUNNING", v->yres/3 + 10*scale, scale);
    text_line(map, v, f, "CONNECT USB", v->yres/3 + 24*scale, scale);
    text_line(map, v, f, "SERIAL CONSOLE", v->yres/3 + 34*scale, scale);
}

#ifndef FB_HEARTBEAT_TEST
#ifdef FB_RUNTIME_TEST
static long call(long number, long a, long b, long c, long d, long e, long f);
#else
static long call(long number, long a, long b, long c, long d, long e, long f)
{
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    register long x4 __asm__("x4") = e;
    register long x5 __asm__("x5") = f;
    register long x8 __asm__("x8") = number;
    __asm__ volatile ("svc 0" : "+r"(x0) : "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5), "r"(x8) : "memory", "cc");
    return x0;
}
#endif

static void log_message(const char *message)
{
    usize n = 0;
    while (message[n]) n++;
    call(A64_WRITE, 2, (long)message, n, 0, 0, 0);
}

static void number(long value)
{
    char buffer[24];
    unsigned i = sizeof(buffer);
    unsigned long v = value < 0 ? (unsigned long)-value : (unsigned long)value;
    do { buffer[--i] = '0' + v % 10; v /= 10; } while (v);
    if (value < 0) buffer[--i] = '-';
    call(A64_WRITE, 2, (long)(buffer+i), sizeof(buffer)-i, 0, 0, 0);
}

static long fb_ioctl(long fd, long command, void *arg)
{
    return call(A64_IOCTL, fd, command, (long)arg, 0, 0, 0);
}

static void property(const char *name, unsigned long value)
{
    log_message(name); log_message("="); number(value); log_message("\n");
}

static void describe(const struct fb_var_screeninfo *v, const struct fb_fix_screeninfo *f)
{
    property("xres", v->xres); property("yres", v->yres);
    property("xres_virtual", v->xres_virtual); property("yres_virtual", v->yres_virtual);
    property("xoffset", v->xoffset); property("yoffset", v->yoffset);
    property("bits_per_pixel", v->bits_per_pixel); property("type", f->type);
    property("visual", f->visual); property("line_length", f->line_length);
    property("smem_len", f->smem_len);
    const struct fb_bitfield *fields[] = { &v->red, &v->green, &v->blue, &v->transp };
    const char *names[] = { "red", "green", "blue", "alpha" };
    for (unsigned i=0; i<4; i++) {
        log_message(names[i]); log_message(": offset="); number(fields[i]->offset);
        log_message(" length="); number(fields[i]->length);
        log_message(" msb_right="); number(fields[i]->msb_right); log_message("\n");
    }
    const char *reason = layout_error(v,f);
    log_message("Layout validation: "); log_message(reason ? reason : "supported"); log_message("\n");
    if (!reason && samsung_xrgb_quirk(v,f))
        log_message("Using measured Samsung XRGB8888 compatibility for visual=0\n");
}

static int equal(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}

static int run(int argc, char **argv)
{
    int info_only = argc == 3 && equal(argv[1], "--info");
    int test_only = argc == 3 && equal(argv[1], "--test");
    int activate_test = argc == 3 && equal(argv[1], "--test-activate");
    int swap_test = argc == 3 && equal(argv[1], "--test-swap-rb");
    if (activate_test || swap_test) test_only = 1;
    if (argc != 2 && !info_only && !test_only) {
        log_message("Usage: fb-heartbeat [--info|--test|--test-activate|--test-swap-rb] /dev/fbN\n"); return 2;
    }
    long fd = call(A64_OPENAT, -100, (long)argv[(info_only || test_only) ? 2 : 1], info_only ? 0 : 2, 0, 0, 0);
    if (fd < 0) { log_message("Framebuffer open failed: "); number(fd); log_message("\n"); return 1; }
    struct fb_var_screeninfo v;
    struct fb_fix_screeninfo f;
    if (fb_ioctl(fd, FBIOGET_VSCREENINFO, &v) < 0 || fb_ioctl(fd, FBIOGET_FSCREENINFO, &f) < 0) {
        log_message("Framebuffer query failed\n"); return 1;
    }
    describe(&v, &f);
    if (info_only) return 0; /* Read-only queries; no mmap, unblank, pan or writes. */
    if (!valid_layout(&v, &f)) { log_message("Unsupported framebuffer layout; refusing to draw\n"); return 1; }
    long result = fb_ioctl(fd, FBIOBLANK, (void *)FB_BLANK_UNBLANK);
    log_message("Framebuffer unblank result: "); number(result); log_message("\n");
    if (result < 0) return 1;
    /* Hardware confirmed: force the queried current mode through set_par to
     * prepare the Samsung display window. Preserve geometry and timings, then
     * query and validate again: the driver normalizes visual and alpha fields.
     * Never reuse the old allocation/stride blindly.
     */
    v.activate = FB_ACTIVATE_NOW | FB_ACTIVATE_FORCE;
    result = fb_ioctl(fd, FBIOPUT_VSCREENINFO, &v);
    log_message("Framebuffer current-mode activation result: "); number(result); log_message("\n");
    if (result < 0) return 1;
    if (fb_ioctl(fd, FBIOGET_VSCREENINFO, &v) < 0 || fb_ioctl(fd, FBIOGET_FSCREENINFO, &f) < 0) {
        log_message("Framebuffer query after activation failed\n"); return 1;
    }
    log_message("Framebuffer after current-mode activation:\n");
    describe(&v, &f);
    if (!valid_layout(&v, &f)) {
        log_message("Unsupported activated framebuffer layout; refusing to draw\n"); return 1;
    }
    long addr = call(A64_MMAP, 0, f.smem_len, 3, 1, fd, 0);
    if ((unsigned long)addr >= (unsigned long)-4095) {
        log_message("Framebuffer mmap failed: "); number(addr); log_message("\n"); return 1;
    }
    int failures = 0;
    struct fb_var_screeninfo render_mode;
    /* Freestanding build has no libc memcpy. Volatile prevents replacement of
     * this small copy with an unavailable library call. */
    for (usize i = 0; i < sizeof(v); i++)
        ((volatile unsigned char *)&render_mode)[i] = ((const unsigned char *)&v)[i];
    if (swap_test || j701f_scanout_swap(&v, &f)) {
        swap_red_blue(&render_mode);
        log_message("Renderer red/blue channels swapped; driver mode unchanged\n");
    }
    v.activate = FB_ACTIVATE_NOW;
    unsigned count = 0;
    while (1) {
        draw((unsigned char *)addr, &render_mode, &f, count);
        result = fb_ioctl(fd, FBIOPAN_DISPLAY, &v);
        if (result < 0) failures = 1;
        if (test_only || !count || (count % 60 == 0)) {
            log_message("Framebuffer heartbeat: "); number(count);
            log_message(" pan result: "); number(result); log_message("\n");
        }
        count++;
        const long delay[2] = {1, 0};
        call(A64_NANOSLEEP, (long)delay, 0, 0, 0, 0, 0);
        if (test_only && count == 6) {
            log_message("Display test completed after six frames\n");
            return failures ? 1 : 0;
        }
    }
}

#ifndef FB_RUNTIME_TEST
__attribute__((used, noreturn)) static void entry(long *stack)
{
    int status = run((int)stack[0], (char **)(stack+1));
    call(A64_EXIT_GROUP, status, 0, 0, 0, 0, 0);
    for (;;) {}
}

__asm__(".global _start\n_start:\nmov x0, sp\nbl entry\n");
#endif
#endif
