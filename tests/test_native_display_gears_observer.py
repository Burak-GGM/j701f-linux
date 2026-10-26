"""Actual ELF preload forwarding against a synthetic EGL backend, no GPU."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('cc') and Path('/usr/include/EGL/egl.h').exists(), 'C/EGL headers required')
class GearsObserverTests(unittest.TestCase):
    def test_swap_results_forwarded_and_no_swap_interval_change(self):
        with tempfile.TemporaryDirectory(prefix='j701f-gears-observer-') as folder:
            root = Path(folder)
            backend = root/'fake.c'
            backend.write_text(r'''
#include <EGL/egl.h>
#include <GLES2/gl2.h>
static int swaps, intervals, queries, names;
EGLBoolean eglSwapBuffers(EGLDisplay d, EGLSurface s) {
    (void)d; (void)s; swaps++; return swaps == 17 ? EGL_FALSE : EGL_TRUE;
}
EGLBoolean eglSwapInterval(EGLDisplay d, EGLint i) {
    (void)d; (void)i; intervals++; return EGL_TRUE;
}
EGLBoolean eglQuerySurface(EGLDisplay d, EGLSurface s, EGLint a, EGLint *v) {
    (void)d; (void)s; queries++; *v = a == EGL_WIDTH ? 720 : 1280; return EGL_TRUE;
}
const GLubyte *glGetString(GLenum n) {
    (void)n; names++; return (const GLubyte *)"Mali-T830 MC1 (Panfrost)";
}
int get_swaps(void) { return swaps; }
int get_intervals(void) { return intervals; }
int get_queries(void) { return queries; }
int get_names(void) { return names; }
''')
            app = root/'app.c'
            app.write_text(r'''
#include <EGL/egl.h>
#include <stdio.h>
int get_swaps(void), get_intervals(void), get_queries(void), get_names(void);
int main(void) {
    int errors=0;
    for (int i=1; i<=400; i++)
        if (eglSwapBuffers(EGL_NO_DISPLAY, EGL_NO_SURFACE) != (i==17 ? EGL_FALSE : EGL_TRUE)) errors++;
    printf("swaps=%d intervals=%d queries=%d names=%d errors=%d\n",
           get_swaps(),get_intervals(),get_queries(),get_names(),errors);
    return errors;
}
''')
            flags = ['cc', '-std=c11', '-Wall', '-Wextra', '-Werror']
            subprocess.run(flags+['-fPIC', '-shared', str(backend), '-o', str(root/'libfakeegl.so')], check=True)
            observer = root/'observer.so'
            subprocess.run(flags+['-fPIC', '-shared', str(ROOT/'tools/native-display-gears-info.c'),
                                  '-lEGL', '-lGLESv2', '-ldl', '-o', str(observer)], check=True)
            binary = root/'app'
            subprocess.run(flags+[str(app), '-L'+str(root), '-lfakeegl', '-Wl,-rpath,'+str(root),
                                  '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], env=dict(os.environ, LD_PRELOAD=str(observer)),
                                    capture_output=True, text=True, check=True)
            self.assertIn('swaps=400 intervals=0 queries=600 names=1 errors=0', result.stdout)
            self.assertEqual(result.stderr.count('GEARS_EGL_SIZE width=720 height=1280'), 1)
            self.assertEqual(result.stderr.count('GEARS_GL_RENDERER=Mali-T830 MC1 (Panfrost)'), 1)


if __name__ == '__main__':
    unittest.main()
