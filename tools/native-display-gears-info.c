/* SPDX-License-Identifier: MIT
 * Observe the benchmark's actual EGL size/renderer during warmup only.
 * Does not change rendering, swap interval, geometry or driver selection.
 */
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>

EGLBoolean eglSwapBuffers(EGLDisplay display, EGLSurface surface)
{
    static EGLBoolean (*next_swap)(EGLDisplay, EGLSurface);
    static unsigned frames;
    static EGLint previous_width, previous_height;
    if (!next_swap) {
        *(void **)(&next_swap) = dlsym(RTLD_NEXT, "eglSwapBuffers");
        if (!next_swap)
            abort();
    }
    if (frames++ < 300) {
        EGLint width = 0, height = 0;
        if (eglQuerySurface(display, surface, EGL_WIDTH, &width) &&
            eglQuerySurface(display, surface, EGL_HEIGHT, &height) &&
            (width != previous_width || height != previous_height)) {
            fprintf(stderr, "GEARS_EGL_SIZE width=%d height=%d\n", width, height);
            previous_width = width;
            previous_height = height;
        }
        if (frames == 1) {
            const char *renderer = (const char *)glGetString(GL_RENDERER);
            fprintf(stderr, "GEARS_GL_RENDERER=%s\n", renderer ? renderer : "unknown");
        }
    }
    return next_swap(display, surface);
}
