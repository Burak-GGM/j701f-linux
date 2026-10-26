/* SPDX-License-Identifier: MIT
 * Render with Panfrost into a display-backed linear DMA-BUF, verify both GLES
 * readback and bytes mapped through the exporting buffer, then create an Exynos
 * FB object. Never attaches it to a plane or changes visible pixels.
 * Shader/readback method derives from panfrost-render-probe.c in this project.
 */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <gbm.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>
#include <linux/dma-buf.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

enum { EDGE = 64 };

static bool validate_exported_bytes(const unsigned char *map, size_t length, size_t stride)
{
    if (!map || stride < EDGE * 4 || stride > (SIZE_MAX - EDGE * 4) / (EDGE - 1) ||
        length < (EDGE - 1) * stride + EDGE * 4)
        return false;
    for (unsigned y = 0; y < EDGE; y++)
        for (unsigned x = 0; x < EDGE; x++) {
            const unsigned char *p = map + y * stride + x * 4;
            bool odd = (x + y) & 1;
            /* DRM XRGB8888 is B,G,R,X in little-endian memory. */
            if (p[0] || p[1] != (odd ? 255 : 0) || p[2] != (odd ? 0 : 255))
                return false;
        }
    return true;
}

static bool driver_is(int fd, const char *expected)
{
    drmVersionPtr v = drmGetVersion(fd);
    bool match = v && v->name && !strcmp(v->name, expected);
    if (v)
        drmFreeVersion(v);
    return match;
}

static GLuint compile_shader(GLenum type, const char *text)
{
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &text, NULL);
    glCompileShader(s);
    GLint ok = GL_FALSE;
    glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[1024] = {0};
        glGetShaderInfoLog(s, sizeof(log), NULL, log);
        fprintf(stderr, "Shader error: %.1000s\n", log);
        glDeleteShader(s);
        return 0;
    }
    return s;
}

static bool draw_imported_texture(GLuint texture)
{
    const char *vs_text = "attribute vec2 position; void main(){gl_Position=vec4(position,0.0,1.0);}";
    const char *fs_text = "precision mediump float; void main(){"
        "float odd=mod(floor(gl_FragCoord.x)+floor(gl_FragCoord.y),2.0);"
        "gl_FragColor=vec4(1.0-odd,odd,0.0,1.0);}";
    GLuint vs = compile_shader(GL_VERTEX_SHADER, vs_text);
    GLuint fs = compile_shader(GL_FRAGMENT_SHADER, fs_text);
    GLuint program = 0, fbo = 0, vbo = 0;
    bool result = false;
    if (!vs || !fs)
        goto out;
    program = glCreateProgram();
    glAttachShader(program, vs);
    glAttachShader(program, fs);
    glBindAttribLocation(program, 0, "position");
    glLinkProgram(program);
    GLint linked = GL_FALSE;
    glGetProgramiv(program, GL_LINK_STATUS, &linked);
    if (!linked)
        goto out;
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        fprintf(stderr, "Imported texture cannot be a GLES render target\n");
        goto out;
    }
    const GLfloat points[] = {-1,-1, 1,-1, -1,1, 1,1};
    glGenBuffers(1, &vbo);
    glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(points), points, GL_STATIC_DRAW);
    glViewport(0, 0, EDGE, EDGE);
    glDisable(GL_DITHER);
    glDisable(GL_BLEND);
    glUseProgram(program);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, NULL);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    glFinish();
    unsigned char pixels[EDGE * EDGE * 4];
    glReadPixels(0, 0, EDGE, EDGE, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    if (glGetError() != GL_NO_ERROR)
        goto out;
    for (unsigned y = 0; y < EDGE; y++)
        for (unsigned x = 0; x < EDGE; x++) {
            const unsigned char *p = pixels + (y * EDGE + x) * 4;
            bool odd = (x + y) & 1;
            if (p[0] != (odd ? 0 : 255) || p[1] != (odd ? 255 : 0) || p[2] || p[3] != 255)
                goto out;
        }
    result = true;
out:
    glDeleteBuffers(1, &vbo);
    glDeleteFramebuffers(1, &fbo);
    if (program)
        glDeleteProgram(program);
    glDeleteShader(vs);
    glDeleteShader(fs);
    return result;
}

int main(int argc, char **argv)
{
    int gpu = -1, native = -1, allocation = -1, dma = -1, result = 1;
    struct gbm_device *display_gbm = NULL, *gpu_gbm = NULL;
    struct gbm_bo *bo = NULL;
    EGLDisplay display = EGL_NO_DISPLAY;
    EGLContext context = EGL_NO_CONTEXT;
    EGLImageKHR image = EGL_NO_IMAGE_KHR;
    bool initialized = false;
    GLuint texture = 0;
    uint32_t handle = 0, fb = 0;
    PFNEGLDESTROYIMAGEKHRPROC destroy_image = NULL;
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc != 3) {
        fprintf(stderr, "Usage: %s PANFROST_RENDER_NODE EXYNOS_CARD\n", argv[0]);
        return 1;
    }
    gpu = open(argv[1], O_RDWR | O_CLOEXEC);
    native = open(argv[2], O_RDWR | O_CLOEXEC);
    allocation = open(argv[2], O_RDWR | O_CLOEXEC);
    if (gpu < 0 || native < 0 || allocation < 0 ||
        drmGetNodeTypeFromFd(gpu) != DRM_NODE_RENDER ||
        !driver_is(gpu, "panfrost") || !driver_is(native, "exynos") || !driver_is(allocation, "exynos")) {
        fprintf(stderr, "Required Panfrost/Exynos devices unavailable\n");
        goto out;
    }
    display_gbm = gbm_create_device(allocation);
    if (!display_gbm)
        goto out;
    bo = gbm_bo_create(display_gbm, 720, 1280, GBM_FORMAT_XRGB8888,
                       GBM_BO_USE_LINEAR | GBM_BO_USE_SCANOUT | GBM_BO_USE_RENDERING);
    if (!bo || gbm_bo_get_modifier(bo) != DRM_FORMAT_MOD_LINEAR)
        goto out;
    uint32_t stride = gbm_bo_get_stride(bo);
    if (stride < 720 * 4 || stride > 16384)
        goto out;
    printf("NATIVE_SHARED_BUFFER width=720 height=1280 format=XRGB8888 stride=%u modifier=0\n", stride);
    dma = gbm_bo_get_fd(bo);
    if (dma < 0)
        goto out;
    gpu_gbm = gbm_create_device(gpu);
    if (!gpu_gbm)
        goto out;
    display = eglGetPlatformDisplay(EGL_PLATFORM_GBM_KHR, gpu_gbm, NULL);
    if (display == EGL_NO_DISPLAY || !eglInitialize(display, NULL, NULL))
        goto out;
    initialized = true;
    if (!eglBindAPI(EGL_OPENGL_ES_API))
        goto out;
    const EGLint attributes[] = {EGL_SURFACE_TYPE, 0, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                                EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE};
    EGLConfig config;
    EGLint count = 0;
    if (!eglChooseConfig(display, attributes, &config, 1, &count) || count != 1)
        goto out;
    const EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attributes);
    if (context == EGL_NO_CONTEXT || !eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, context))
        goto out;
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    printf("NATIVE_SHARED_RENDERER=%.200s\n", renderer ? renderer : "unknown");
    if (!renderer || !strcasestr(renderer, "panfrost") || !strstr(renderer, "T830")) {
        fprintf(stderr, "Refusing to verify a software or different GPU renderer\n");
        goto out;
    }
    PFNEGLCREATEIMAGEKHRPROC create_image = (PFNEGLCREATEIMAGEKHRPROC)eglGetProcAddress("eglCreateImageKHR");
    destroy_image = (PFNEGLDESTROYIMAGEKHRPROC)eglGetProcAddress("eglDestroyImageKHR");
    PFNGLEGLIMAGETARGETTEXTURE2DOESPROC target_image =
        (PFNGLEGLIMAGETARGETTEXTURE2DOESPROC)eglGetProcAddress("glEGLImageTargetTexture2DOES");
    if (!create_image || !destroy_image || !target_image)
        goto out;
    const EGLint image_attributes[] = {
        EGL_WIDTH, 720, EGL_HEIGHT, 1280, EGL_LINUX_DRM_FOURCC_EXT, DRM_FORMAT_XRGB8888,
        EGL_DMA_BUF_PLANE0_FD_EXT, dma, EGL_DMA_BUF_PLANE0_OFFSET_EXT, 0,
        EGL_DMA_BUF_PLANE0_PITCH_EXT, (EGLint)stride, EGL_NONE};
    image = create_image(display, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT, NULL, image_attributes);
    if (image == EGL_NO_IMAGE_KHR) {
        fprintf(stderr, "DMA-BUF EGLImage import failed: %#x\n", eglGetError());
        goto out;
    }
    puts("NATIVE_SHARED_EGLIMAGE_IMPORT_OK");
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    target_image(GL_TEXTURE_2D, image);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    if (glGetError() != GL_NO_ERROR || !draw_imported_texture(texture)) {
        fprintf(stderr, "Imported-buffer GPU drawing/readback failed\n");
        goto out;
    }
    puts("NATIVE_SHARED_GPU_RENDER_READBACK_OK pixels=4096");
    struct dma_buf_sync sync = {.flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ};
    if (ioctl(dma, DMA_BUF_IOCTL_SYNC, &sync)) {
        perror("DMA-BUF CPU read begin");
        goto out;
    }
    size_t length = (size_t)stride * 1280;
    void *map = mmap(NULL, length, PROT_READ, MAP_SHARED, dma, 0);
    bool bytes_ok = map != MAP_FAILED && validate_exported_bytes(map, length, stride);
    if (map != MAP_FAILED)
        munmap(map, length);
    sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
    if (ioctl(dma, DMA_BUF_IOCTL_SYNC, &sync) || !bytes_ok) {
        fprintf(stderr, "Exported DMA-BUF CPU bytes did not match the shader\n");
        goto out;
    }
    puts("NATIVE_SHARED_CPU_BUFFER_OK pixels=4096");
    if (drmPrimeFDToHandle(native, dma, &handle))
        goto out;
    uint32_t handles[4] = {handle}, strides[4] = {stride}, offsets[4] = {0};
    if (drmModeAddFB2(native, 720, 1280, DRM_FORMAT_XRGB8888, handles, strides, offsets, &fb, 0))
        goto out;
    puts("NATIVE_SHARED_FB_OBJECT_OK; buffer never attached to a plane");
    result = 0;
out:
    if (fb)
        drmModeRmFB(native, fb);
    if (handle) {
        struct drm_gem_close close_handle = {.handle = handle};
        drmIoctl(native, DRM_IOCTL_GEM_CLOSE, &close_handle);
    }
    if (initialized) {
        if (texture)
            glDeleteTextures(1, &texture);
        if (image != EGL_NO_IMAGE_KHR && destroy_image)
            destroy_image(display, image);
        eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        if (context != EGL_NO_CONTEXT)
            eglDestroyContext(display, context);
        eglTerminate(display);
    }
    if (gpu_gbm)
        gbm_device_destroy(gpu_gbm);
    if (dma >= 0)
        close(dma);
    if (bo)
        gbm_bo_destroy(bo);
    if (display_gbm)
        gbm_device_destroy(display_gbm);
    if (allocation >= 0)
        close(allocation);
    if (native >= 0)
        close(native);
    if (gpu >= 0)
        close(gpu);
    return result;
}
