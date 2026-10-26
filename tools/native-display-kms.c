/* SPDX-License-Identifier: GPL-2.0-only
 * Explicit native Exynos KMS colour/page-flip experiment, no sound.
 * Run only under display-trial-supervisor.py, with SDDM stopped and unchanged
 * BOOT. The watchdog reboot is teardown even if an ioctl blocks indefinitely.
 */
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_mode.h>

static unsigned events;
static double first_event, last_event;

static void flip(int fd, unsigned frame, unsigned sec, unsigned usec, void *data)
{
    (void)fd; (void)data;
    double at = sec + usec / 1e6;
    if (!events) first_event = at;
    last_event = at;
    ++events;
    printf("NATIVE_FLIP event=%u sequence=%u at=%.6f\n", events, frame, at);
    fflush(stdout);
}

static void fail(const char *operation)
{
    fprintf(stderr, "NATIVE_KMS_FAIL %s: %s\n", operation, strerror(errno));
    exit(1);
}

int main(int argc, char **argv)
{
    if (argc != 2 || strncmp(argv[1], "/dev/dri/card", 13)) return 2;
    setvbuf(stdout, NULL, _IOLBF, 0);
    int fd = open(argv[1], O_RDWR | O_CLOEXEC);
    if (fd < 0) fail("open");
    drmVersionPtr v = drmGetVersion(fd);
    if (!v || strcmp(v->name, "exynos")) {
        fprintf(stderr, "Refusing non-native/non-Exynos DRM device\n");
        return 2;
    }
    drmFreeVersion(v);
    if (drmSetMaster(fd)) fail("master");
    drmModeRes *r = drmModeGetResources(fd);
    if (!r) fail("resources");
    drmModeConnector *c = NULL;
    drmModeModeInfo mode = {0};
    for (int n = 0; n < r->count_connectors && !c; ++n) {
        drmModeConnector *candidate = drmModeGetConnector(fd, r->connectors[n]);
        if (!candidate) continue;
        for (int m = 0; m < candidate->count_modes; ++m) {
            if (candidate->connection == DRM_MODE_CONNECTED &&
                candidate->connector_type == DRM_MODE_CONNECTOR_DSI &&
                candidate->modes[m].hdisplay == 720 && candidate->modes[m].vdisplay == 1280) {
                c = candidate;
                mode = candidate->modes[m];
                break;
            }
        }
        if (!c) drmModeFreeConnector(candidate);
    }
    if (!c) { fprintf(stderr, "No connected 720x1280 DSI connector\n"); return 3; }
    uint32_t crtc = 0;
    for (int n = 0; n < c->count_encoders && !crtc; ++n) {
        drmModeEncoder *e = drmModeGetEncoder(fd, c->encoders[n]);
        if (!e) continue;
        for (int k = 0; k < r->count_crtcs && k < 32; ++k)
            if (e->possible_crtcs & (1u << k)) { crtc = r->crtcs[k]; break; }
        drmModeFreeEncoder(e);
    }
    if (!crtc) { fprintf(stderr, "No compatible CRTC\n"); return 3; }
    printf("NATIVE_MODE connector=%u crtc=%u %ux%u clock=%u htotal=%u vtotal=%u\n",
           c->connector_id, crtc, mode.hdisplay, mode.vdisplay, mode.clock, mode.htotal, mode.vtotal);
    uint32_t fb[2];
    for (unsigned n = 0; n < 2; ++n) {
        struct drm_mode_create_dumb b = {.width=720, .height=1280, .bpp=32};
        if (ioctl(fd, DRM_IOCTL_MODE_CREATE_DUMB, &b)) fail("create dumb");
        if (drmModeAddFB(fd, 720, 1280, 24, 32, b.pitch, b.handle, &fb[n])) fail("add fb");
        struct drm_mode_map_dumb map = {.handle=b.handle};
        if (ioctl(fd, DRM_IOCTL_MODE_MAP_DUMB, &map)) fail("map dumb");
        uint8_t *pixels = mmap(NULL, b.size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, map.offset);
        if (pixels == MAP_FAILED) fail("mmap");
        for (unsigned y = 0; y < 1280; ++y) {
            uint32_t *row = (uint32_t *)(pixels + y * b.pitch);
            for (unsigned x = 0; x < 720; ++x) {
                static const uint32_t colours[] = {0xffff0000, 0xff00ff00, 0xff0000ff};
                row[x] = colours[(x / 240 + n) % 3];
            }
        }
        munmap(pixels, b.size);
    }
    if (drmModeSetCrtc(fd, crtc, fb[0], 0, 0, &c->connector_id, 1, &mode)) fail("set CRTC");
    puts("NATIVE_MODESET_OK");
    drmEventContext ctx = {.version=DRM_EVENT_CONTEXT_VERSION, .page_flip_handler=flip};
    for (unsigned n = 0; n < 120; ++n) {
        if (drmModePageFlip(fd, crtc, fb[(n + 1) % 2], DRM_MODE_PAGE_FLIP_EVENT, NULL)) fail("page flip");
        struct pollfd p = {.fd=fd, .events=POLLIN};
        if (poll(&p, 1, 1500) <= 0 || !(p.revents & POLLIN)) {
            fprintf(stderr, "NATIVE_FLIP_TIMEOUT\n"); return 4;
        }
        if (drmHandleEvent(fd, &ctx)) fail("handle event");
    }
    printf("NATIVE_FLIPS_OK count=%u elapsed=%.6f event_rate=%.3f\n",
           events, last_event-first_event, (events-1)/(last_event-first_event));
    puts("NATIVE_PANEL_HOLD_FOR_DCS_READ 8s");
    sleep(8);
    /* Process exit is not experiment teardown. The supervisor always resets
     * the phone, discarding the overlay and booting the original simpledrm.
     */
    return 0;
}
