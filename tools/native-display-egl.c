/* SPDX-License-Identifier: MIT
 * Query the actual GLES renderer on a native-display or Panfrost GBM device.
 * No frame is drawn, no buffer is displayed, and no acceleration is inferred
 * from allocation flags alone. Adapted from this project's render probe.
 */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <gbm.h>
#include <xf86drm.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    struct gbm_device *gbm = NULL;
    EGLDisplay display = EGL_NO_DISPLAY;
    EGLContext context = EGL_NO_CONTEXT;
    int fd = -1, result = 1;
    bool initialized = false;

    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc != 3 || (strcmp(argv[1], "render") && strcmp(argv[1], "display"))) {
        fprintf(stderr, "Usage: %s render|display DRM_NODE\n", argv[0]);
        return 1;
    }
    const char *expected = !strcmp(argv[1], "render") ? "panfrost" : "exynos";
    fd = open(argv[2], O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        perror("open DRM device");
        goto out;
    }
    drmVersionPtr version = drmGetVersion(fd);
    bool correct = version && version->name && !strcmp(version->name, expected);
    if (version)
        drmFreeVersion(version);
    if (!correct) {
        fprintf(stderr, "DRM driver does not match requested path\n");
        goto out;
    }
    printf("NATIVE_EGL_PATH=%s DRM_DRIVER=%s\n", argv[1], expected);
    gbm = gbm_create_device(fd);
    if (!gbm) {
        fprintf(stderr, "GBM device creation failed\n");
        goto out;
    }
    display = eglGetPlatformDisplay(EGL_PLATFORM_GBM_KHR, gbm, NULL);
    EGLint major, minor;
    if (display == EGL_NO_DISPLAY || !eglInitialize(display, &major, &minor)) {
        fprintf(stderr, "EGL initialization failed: %#x\n", eglGetError());
        goto out;
    }
    initialized = true;
    if (!eglBindAPI(EGL_OPENGL_ES_API))
        goto out;
    const EGLint attributes[] = {EGL_SURFACE_TYPE, 0, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                                EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8,
                                EGL_NONE};
    EGLConfig config;
    EGLint count = 0;
    if (!eglChooseConfig(display, attributes, &config, 1, &count) || count != 1) {
        fprintf(stderr, "GLES configuration unavailable\n");
        goto out;
    }
    const EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attributes);
    if (context == EGL_NO_CONTEXT ||
        !eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, context)) {
        fprintf(stderr, "Surfaceless GLES context failed: %#x\n", eglGetError());
        goto out;
    }
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    if (!renderer || glGetError() != GL_NO_ERROR)
        goto out;
    printf("NATIVE_EGL_RENDERER=%.200s\n", renderer);
    printf("NATIVE_EGL_PANFROST_T830=%d\n",
           !!(strcasestr(renderer, "panfrost") && strstr(renderer, "T830")));
    puts("NATIVE_EGL_CONTEXT_READY; no draw or scanout performed");
    result = 0;
out:
    if (initialized) {
        eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        if (context != EGL_NO_CONTEXT)
            eglDestroyContext(display, context);
        eglTerminate(display);
    }
    if (gbm)
        gbm_device_destroy(gbm);
    if (fd >= 0)
        close(fd);
    return result;
}
