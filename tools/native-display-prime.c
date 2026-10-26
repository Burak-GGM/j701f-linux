/* SPDX-License-Identifier: MIT
 * Compare linear GBM allocation on Panfrost and the Exynos display device.
 * Creates an FB object but never changes the mode, planes or visible pixels.
 */
#include <errno.h>
#include <fcntl.h>
#include <gbm.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>

static int check_driver(int fd, const char *expected)
{
    drmVersionPtr version = drmGetVersion(fd);
    int ok = version && version->name && !strcmp(version->name, expected);

    if (!ok)
        fprintf(stderr, "Expected DRM driver %s, got %s\n", expected,
                version && version->name ? version->name : "unknown");
    drmFreeVersion(version);
    return ok;
}

int main(int argc, char **argv)
{
    struct gbm_device *gbm = NULL;
    struct gbm_bo *bo = NULL;
    int gpu = -1, display = -1, allocation = -1, dma = -1, result = 1;
    bool display_allocator;
    uint32_t handles[4] = {0}, strides[4] = {0}, offsets[4] = {0};
    uint32_t fb = 0;

    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc != 4 || (strcmp(argv[3], "render") && strcmp(argv[3], "display"))) {
        fprintf(stderr, "Usage: %s PANFROST_RENDER_NODE EXYNOS_CARD render|display\n", argv[0]);
        return 1;
    }
    display_allocator = !strcmp(argv[3], "display");
    gpu = open(argv[1], O_RDWR | O_CLOEXEC);
    display = open(argv[2], O_RDWR | O_CLOEXEC);
    if (gpu < 0 || display < 0) {
        perror("open DRM device");
        goto out;
    }
    if (!check_driver(gpu, "panfrost") || !check_driver(display, "exynos"))
        goto out;
    /* A separate file description keeps PRIME's imported handle distinct from
     * any handle owned by the display-backed GBM device (kmsro allocation).
     */
    if (display_allocator) {
        allocation = open(argv[2], O_RDWR | O_CLOEXEC);
        if (allocation < 0) {
            perror("open display GBM allocator");
            goto out;
        }
    }
    printf("NATIVE_PRIME_ALLOCATOR %s\n", display_allocator ? "display" : "render");
    gbm = gbm_create_device(display_allocator ? allocation : gpu);
    if (!gbm) {
        perror("gbm_create_device");
        goto out;
    }
    bo = gbm_bo_create(gbm, 720, 1280, GBM_FORMAT_XRGB8888,
                       GBM_BO_USE_RENDERING | GBM_BO_USE_LINEAR |
                       (display_allocator ? GBM_BO_USE_SCANOUT : 0));
    if (!bo) {
        perror("gbm_bo_create linear XRGB8888");
        goto out;
    }
    strides[0] = gbm_bo_get_stride(bo);
    printf("NATIVE_PRIME_BUFFER width=720 height=1280 format=XRGB8888 stride=%" PRIu32
           " modifier=%" PRIu64 "\n", strides[0], gbm_bo_get_modifier(bo));
    /* A modifier other than LINEAR cannot be consumed by this DECON plane. */
    if (gbm_bo_get_modifier(bo) != DRM_FORMAT_MOD_LINEAR) {
        fprintf(stderr, "GBM did not provide a verified linear modifier\n");
        goto out;
    }
    dma = gbm_bo_get_fd(bo);
    if (dma < 0) {
        perror("gbm_bo_get_fd");
        goto out;
    }
    if (drmPrimeFDToHandle(display, dma, &handles[0])) {
        printf("NATIVE_PRIME_IMPORT_REJECTED errno=%d\n", errno);
        result = 2;
        goto out;
    }
    puts("NATIVE_PRIME_IMPORT_OK");
    if (drmModeAddFB2(display, 720, 1280, DRM_FORMAT_XRGB8888,
                      handles, strides, offsets, &fb, 0)) {
        printf("NATIVE_PRIME_FB_REJECTED errno=%d\n", errno);
        result = 2;
        goto out;
    }
    puts("NATIVE_PRIME_SCANOUT_OBJECT_OK");
    result = 0;
out:
    if (fb)
        drmModeRmFB(display, fb);
    if (handles[0]) {
        struct drm_gem_close close_handle = {.handle = handles[0]};
        drmIoctl(display, DRM_IOCTL_GEM_CLOSE, &close_handle);
    }
    if (dma >= 0)
        close(dma);
    if (bo)
        gbm_bo_destroy(bo);
    if (gbm)
        gbm_device_destroy(gbm);
    if (allocation >= 0)
        close(allocation);
    if (display >= 0)
        close(display);
    if (gpu >= 0)
        close(gpu);
    return result;
}
