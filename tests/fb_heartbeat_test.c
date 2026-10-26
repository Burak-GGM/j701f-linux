#define FB_HEARTBEAT_TEST
#include "../tools/fb-heartbeat.c"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    /* Actual phone probe: visual=0 with complete XRGB8888 bitfields. */
    struct fb_var_screeninfo phone = {0};
    struct fb_fix_screeninfo phone_fix = {0};
    phone.xres = phone.xres_virtual = 720;
    phone.yres = phone.yres_virtual = 1280;
    phone.bits_per_pixel = 32;
    phone.red = (struct fb_bitfield){16,8,0};
    phone.green = (struct fb_bitfield){8,8,0};
    phone.blue = (struct fb_bitfield){0,8,0};
    phone_fix.line_length = 2880;
    phone_fix.smem_len = 7372800;
    assert(samsung_xrgb_quirk(&phone,&phone_fix));
    assert(valid_layout(&phone,&phone_fix));
    phone_fix.smem_len = 1024;
    assert(!valid_layout(&phone,&phone_fix)); /* Compatibility must retain bounds. */
    phone_fix.smem_len = 7372800;
    phone.red.offset = 0;
    assert(!valid_layout(&phone,&phone_fix)); /* Never accept arbitrary visual=0. */
    phone.red.offset = 16;
    phone.transp = (struct fb_bitfield){24,8,0};
    assert(!valid_layout(&phone,&phone_fix));
    phone_fix.visual = FB_VISUAL_TRUECOLOR;
    assert(j701f_scanout_swap(&phone, &phone_fix));
    phone.bits_per_pixel = 24;
    assert(!j701f_scanout_swap(&phone, &phone_fix));
    phone.bits_per_pixel = 32;
    phone.transp.length = 0;
    assert(!j701f_scanout_swap(&phone, &phone_fix));

    struct fb_var_screeninfo v = {0};
    struct fb_fix_screeninfo f = {0};
    v.xres = 540; v.yres = 960; v.xres_virtual = 544; v.yres_virtual = 970;
    v.xoffset = 2; v.yoffset = 3; v.bits_per_pixel = 32;
    v.red = (struct fb_bitfield){16,8,0}; v.green = (struct fb_bitfield){8,8,0};
    v.blue = (struct fb_bitfield){0,8,0}; v.transp = (struct fb_bitfield){24,8,0};
    f.type = FB_TYPE_PACKED_PIXELS; f.visual = FB_VISUAL_TRUECOLOR;
    f.line_length = 544 * 4; f.smem_len = f.line_length * 970;
    assert(valid_layout(&v, &f));
    assert(color(&v,255,0,0) == 0xffff0000U);
    swap_red_blue(&v);
    assert(color(&v,255,0,0) == 0xff0000ffU);
    assert(color(&v,0,255,0) == 0xff00ff00U);
    assert(color(&v,255,255,255) == 0xffffffffU);
    swap_red_blue(&v); /* Packing changes only in the renderer's copied mode. */
    unsigned char *map = malloc(f.smem_len + 64);
    assert(map);
    memset(map, 0xa5, f.smem_len + 64);
    draw(map, &v, &f, 0);
    /* Row padding, off-screen offsets, and guard bytes must remain untouched. */
    for (unsigned y = 0; y < 970; y++) {
        for (unsigned x = 0; x < f.line_length; x++) {
            if (y < v.yoffset || y >= v.yoffset+v.yres || x < v.xoffset*4 || x >= (v.xoffset+v.xres)*4)
                assert(map[y*f.line_length+x] == 0xa5);
        }
    }
    for (unsigned i = 0; i < 64; i++) assert(map[f.smem_len+i] == 0xa5);
    usize first = v.yoffset*f.line_length+v.xoffset*4;
    unsigned char blue = map[first];
    draw(map, &v, &f, 1);
    assert(map[first] != blue); /* Heartbeat actually changes each frame. */
    if (argc == 2) {
        FILE *out = fopen(argv[1], "wb"); assert(out);
        fprintf(out, "P6\n%u %u\n255\n", v.xres, v.yres);
        for (unsigned y = 0; y < v.yres; y++) for (unsigned x = 0; x < v.xres; x++) {
            unsigned char *p = map+(y+v.yoffset)*f.line_length+(x+v.xoffset)*4;
            unsigned char rgb[3] = {p[2],p[1],p[0]};
            assert(fwrite(rgb,1,3,out)==3);
        }
        fclose(out);
    }
    unsigned size = f.smem_len;
    f.smem_len = 4; assert(!valid_layout(&v,&f));
    assert(strcmp(layout_error(&v,&f), "visible area exceeds framebuffer allocation") == 0);
    f.smem_len = size;
    f.visual = FB_VISUAL_DIRECTCOLOR;
    assert(strcmp(layout_error(&v,&f), "framebuffer visual is not truecolor") == 0);
    f.visual = FB_VISUAL_TRUECOLOR;
    v.bits_per_pixel = 15; assert(!valid_layout(&v,&f)); v.bits_per_pixel = 32;
    v.red.length = 10; assert(!valid_layout(&v,&f)); v.red.length = 8;
    v.green.offset = 16; assert(!valid_layout(&v,&f)); v.green.offset = 8;
    v.yoffset = 1000; assert(!valid_layout(&v,&f)); v.yoffset = 3;
    /* RGB565 and RGB24 layouts also pack according to the reported bitfields. */
    v.bits_per_pixel=16; v.red=(struct fb_bitfield){11,5,0};
    v.green=(struct fb_bitfield){5,6,0}; v.blue=(struct fb_bitfield){0,5,0};
    v.transp=(struct fb_bitfield){0,0,0};
    assert(valid_layout(&v,&f)); assert(color(&v,255,255,255)==0xffff);
    draw(map,&v,&f,0);
    v.bits_per_pixel=24; v.red=(struct fb_bitfield){0,8,0};
    v.green=(struct fb_bitfield){8,8,0}; v.blue=(struct fb_bitfield){16,8,0};
    assert(valid_layout(&v,&f)); assert(color(&v,255,0,0)==0xff);
    draw(map,&v,&f,0);
    free(map);
    puts("PASS: framebuffer layout validation, alpha, stride/offset bounds, RGB565/24/32 and changing heartbeat");
    return 0;
}
