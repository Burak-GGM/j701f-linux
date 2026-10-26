/* Headless J701F Panfrost verification. Never opens a display or input device.
 * --inspect only reads DRM identity. --render verifies one GLES shader frame.
 * --self-test validates the shader/readback pipeline without claiming hardware.
 */
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <gbm.h>
#include <xf86drm.h>
#include <fcntl.h>
#include <glob.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

enum { EDGE = 64, UNAVAILABLE = 2 };

static bool extension(const char *all, const char *name)
{
    if (!all) return false;
    size_t length = strlen(name);
    for (const char *p = all; (p = strstr(p, name)); p += length)
        if ((p == all || p[-1] == ' ') && (p[length] == ' ' || !p[length])) return true;
    return false;
}

static GLuint shader(GLenum type, const char *source)
{
    GLuint object = glCreateShader(type);
    glShaderSource(object, 1, &source, NULL);
    glCompileShader(object);
    GLint okay = GL_FALSE;
    glGetShaderiv(object, GL_COMPILE_STATUS, &okay);
    if (!okay) {
        char log[1024] = {0}; glGetShaderInfoLog(object, sizeof(log), NULL, log);
        fprintf(stderr, "Shader compilation failed: %.1000s\n", log);
        glDeleteShader(object); return 0;
    }
    return object;
}

static bool draw_and_verify(void)
{
    const char *vertex = "attribute vec2 position; void main(){gl_Position=vec4(position,0.0,1.0);}";
    const char *fragment = "precision mediump float; void main(){"
        "float odd=mod(floor(gl_FragCoord.x)+floor(gl_FragCoord.y),2.0);"
        "gl_FragColor=vec4(1.0-odd,odd,0.0,1.0);}";
    GLuint vs = shader(GL_VERTEX_SHADER, vertex), fs = shader(GL_FRAGMENT_SHADER, fragment);
    if (!vs || !fs) { glDeleteShader(vs); glDeleteShader(fs); return false; }
    GLuint program = glCreateProgram();
    glAttachShader(program, vs); glAttachShader(program, fs);
    glBindAttribLocation(program, 0, "position"); glLinkProgram(program);
    GLint linked = GL_FALSE; glGetProgramiv(program, GL_LINK_STATUS, &linked);
    GLuint texture = 0, fbo = 0, vbo = 0;
    bool result = false;
    if (!linked) { fprintf(stderr, "Shader linking failed\n"); goto out; }
    glGenTextures(1, &texture); glBindTexture(GL_TEXTURE_2D, texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, EDGE, EDGE, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    glGenFramebuffers(1, &fbo); glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        fprintf(stderr, "Offscreen framebuffer incomplete\n"); goto out;
    }
    const GLfloat points[] = {-1,-1, 1,-1, -1,1, 1,1};
    glGenBuffers(1, &vbo); glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(points), points, GL_STATIC_DRAW);
    glViewport(0, 0, EDGE, EDGE); glDisable(GL_DITHER); glDisable(GL_BLEND);
    glUseProgram(program); glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, NULL);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4); glFinish();
    unsigned char pixels[EDGE * EDGE * 4];
    glReadPixels(0, 0, EDGE, EDGE, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    if (glGetError() != GL_NO_ERROR) { fprintf(stderr, "GLES rendering/readback error\n"); goto out; }
    for (unsigned y = 0; y < EDGE; y++) for (unsigned x = 0; x < EDGE; x++) {
        const unsigned char *p = pixels + (y * EDGE + x) * 4;
        bool odd = (x + y) & 1;
        if (p[0] != (odd ? 0 : 255) || p[1] != (odd ? 255 : 0) || p[2] || p[3] != 255) {
            fprintf(stderr, "Shader output mismatch at %u,%u\n", x, y); goto out;
        }
    }
    result = true;
out:
    glDeleteBuffers(1, &vbo); glDeleteFramebuffers(1, &fbo); glDeleteTextures(1, &texture);
    glDeleteProgram(program); glDeleteShader(vs); glDeleteShader(fs);
    return result;
}

static int panfrost_fd(const char *path, bool write_access)
{
    struct stat info;
    if (lstat(path, &info) || !S_ISCHR(info.st_mode)) return -1;
    int fd = open(path, (write_access ? O_RDWR : O_RDONLY) | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) { perror(path); return -1; }
    if (drmGetNodeTypeFromFd(fd) != DRM_NODE_RENDER) { close(fd); return -1; }
    drmVersionPtr version = drmGetVersion(fd);
    bool okay = version && version->name && !strcmp(version->name, "panfrost");
    printf("DRM_NODE=%s DRM_DRIVER=%.80s\n", path, version && version->name ? version->name : "unknown");
    if (version) drmFreeVersion(version);
    if (!okay) { close(fd); return -1; }
    return fd;
}

int main(int argc, char **argv)
{
    bool render = false, selftest = false;
    const char *device = NULL;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--render")) render = true;
        else if (!strcmp(argv[i], "--inspect")) { /* default */ }
        else if (!strcmp(argv[i], "--self-test")) selftest = true;
        else if (!strcmp(argv[i], "--device") && i + 1 < argc) device = argv[++i];
        else { fprintf(stderr, "Usage: %s [--inspect|--render] [--device /dev/dri/renderD128] | --self-test\n", argv[0]); return 1; }
    }
    if (selftest && (render || device)) { fprintf(stderr, "Self-test cannot verify a device\n"); return 1; }
    alarm(15);
    int fd = -1;
    if (!selftest) {
        if (device) fd = panfrost_fd(device, render);
        else {
            glob_t nodes = {0};
            if (!glob("/dev/dri/renderD*", 0, NULL, &nodes))
                for (size_t i = 0; i < nodes.gl_pathc && fd < 0; i++) fd = panfrost_fd(nodes.gl_pathv[i], render);
            globfree(&nodes);
        }
        if (fd < 0) {
            puts("PANFROST_UNAVAILABLE: no accessible Panfrost DRM render node; hardware rendering not attempted");
            return UNAVAILABLE;
        }
        if (!render) {
            puts("PANFROST_DRM_IDENTITY_FOUND: rendering and acceleration are still unverified"); close(fd); return 0;
        }
    }
    struct gbm_device *gbm = selftest ? NULL : gbm_create_device(fd);
    if (!selftest && !gbm) { fprintf(stderr, "GBM initialization failed\n"); close(fd); return 1; }
    EGLDisplay display = eglGetPlatformDisplay(selftest ? EGL_PLATFORM_SURFACELESS_MESA : EGL_PLATFORM_GBM_KHR,
                                              gbm, NULL);
    EGLContext context = EGL_NO_CONTEXT;
    int result = 1;
    EGLint major, minor;
    if (display == EGL_NO_DISPLAY || !eglInitialize(display, &major, &minor)) {
        fprintf(stderr, "EGL initialization failed: 0x%x\n", eglGetError()); goto finish;
    }
    const char *vendor = eglQueryString(display, EGL_VENDOR);
    printf("EGL_VERSION=%d.%d EGL_VENDOR=%.80s\n", major, minor, vendor ? vendor : "unknown");
    if (!extension(eglQueryString(display, EGL_EXTENSIONS), "EGL_KHR_surfaceless_context") ||
        !eglBindAPI(EGL_OPENGL_ES_API)) { fprintf(stderr, "Surfaceless GLES unavailable\n"); goto finish; }
    const EGLint attributes[] = {EGL_SURFACE_TYPE, 0, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                                EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8,
                                EGL_ALPHA_SIZE, 8, EGL_NONE};
    EGLConfig config; EGLint count = 0;
    if (!eglChooseConfig(display, attributes, &config, 1, &count) || count != 1) {
        fprintf(stderr, "No suitable GLES configuration\n"); goto finish;
    }
    const EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attributes);
    if (context == EGL_NO_CONTEXT || !eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, context)) {
        fprintf(stderr, "GLES context failed: 0x%x\n", eglGetError()); goto finish;
    }
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    printf("GL_RENDERER=%.120s\n", renderer ? renderer : "unknown");
    if (!selftest && (!renderer || !strcasestr(renderer, "panfrost") || !strstr(renderer, "T830"))) {
        fprintf(stderr, "Refusing to call a different GPU or software renderer J701F acceleration\n"); goto finish;
    }
    if (!draw_and_verify()) goto finish;
    puts(selftest ? "PIPELINE_SELF_TEST_PASS: 4096 shader pixels verified; hardware_verified=false" :
         "PANFROST_T830_RENDER_PASS: DRM identity, hardware renderer and 4096 shader pixels verified");
    result = 0;
finish:
    if (display != EGL_NO_DISPLAY) {
        eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
        if (context != EGL_NO_CONTEXT) eglDestroyContext(display, context);
        eglTerminate(display);
    }
    if (gbm) gbm_device_destroy(gbm);
    if (fd >= 0) close(fd);
    return result;
}
