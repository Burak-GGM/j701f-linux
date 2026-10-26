"""Compile actual loader init with host OF mocks; no hardware operations."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/kmod/ea8061s/j701f-display-overlay.c'
MOCK = r'''
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define __init
#define CONFIG_EXYNOS_IOMMU 0
#define IS_ENABLED(x) iommu_config
#define pr_info(...) ((void)0)
struct device_node { int id; bool available; };
struct property { int unused; };
struct platform_device { struct { void *driver; } dev; };
static bool allow_apply;
static int result=-EAGAIN, overlay_id;
static unsigned char display_overlay_blob[]={1,2,3,4};
static struct device_node nodes[4]={{0,false},{1,false},{2,true},{3,true}};
static struct platform_device devices[2];
static struct property prop;
static int board=1, iommu_config, fb_bound, mmu_bound, apply_error, remove_error;
static int remove_calls, apply_calls, put_count;
static bool of_machine_is_compatible(const char *name) { (void)name; return board; }
static struct device_node *of_find_node_by_path(const char *path)
{
    if (strstr(path,"display-controller")) return &nodes[0];
    if (strstr(path,"dsi@")) return &nodes[1];
    if (strstr(path,"iommu@")) return &nodes[2];
    return &nodes[3];
}
static bool of_device_is_available(struct device_node *n) { return n->available; }
static struct platform_device *of_find_device_by_node(struct device_node *n)
{
    int i=n->id==3;
    devices[i].dev.driver=(i ? fb_bound : mmu_bound) ? &prop : NULL;
    return &devices[i];
}
static void platform_device_put(struct platform_device *p) { (void)p; }
static struct property *of_find_property(struct device_node *n, const char *name, void *length)
{ (void)n; (void)name; (void)length; return &prop; }
static int of_remove_property(struct device_node *n, struct property *p)
{ (void)n; (void)p; remove_calls++; return remove_error; }
static int of_overlay_fdt_apply(const void *blob, unsigned size, int *id, void *base)
{ (void)blob; (void)size; (void)base; apply_calls++; *id=7; return apply_error; }
static void of_node_put(struct device_node *n) { if(n) put_count++; }
'''
MAIN = r'''
int main(int argc, char **argv)
{
    if(argc!=2) return 2;
    allow_apply=true;
    switch(atoi(argv[1])) {
    case 1: allow_apply=false; break;
    case 2: board=0; break;
    case 3: iommu_config=1; break;
    case 4: nodes[0].available=true; break;
    case 5: nodes[1].available=true; break;
    case 6: fb_bound=1; break;
    case 7: mmu_bound=1; break;
    case 8: remove_error=-EIO; break;
    case 9: apply_error=-EIO; break;
    }
    int ret=j701f_overlay_init();
    printf("{\"return\":%d,\"result\":%d,\"apply\":%d,\"remove\":%d,\"puts\":%d}\n",
           ret,result,apply_calls,remove_calls,put_count);
    return 0;
}
'''


@unittest.skipUnless(shutil.which('clang'), 'Host clang required')
class OverlayGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='j701f-overlay-guards-')
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name)
        source = SOURCE.read_text()
        body = source[source.index('static int __init j701f_overlay_init'):source.index('module_init(')]
        (path/'mock.c').write_text(MOCK+body+MAIN)
        cls.exe = path/'mock'
        subprocess.run(['clang','-std=c11','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined',str(path/'mock.c'),'-o',str(cls.exe)],
                       check=True, capture_output=True, text=True)

    def run_case(self, case):
        return json.loads(subprocess.check_output([str(self.exe),str(case)],text=True,
                           env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')))

    def test_requires_opt_in_and_correct_machine_and_kernel(self):
        for case in (1,2,3):
            with self.subTest(case=case):
                r=self.run_case(case)
                self.assertEqual((r['return'],r['remove'],r['apply']),(-1,0,0))

    def test_refuses_active_controllers_and_bound_firmware_or_mmu(self):
        for case in (4,5,6,7):
            with self.subTest(case=case):
                r=self.run_case(case)
                self.assertLess(r['return'],0)
                self.assertEqual((r['remove'],r['apply'],r['puts']),(0,0,4))

    def test_remove_failure_never_enables_native_graph(self):
        r=self.run_case(8)
        self.assertEqual((r['return'],r['apply'],r['puts']),(-5,0,4))

    def test_partial_apply_failure_keeps_module_resident_for_reset(self):
        r=self.run_case(9)
        self.assertEqual((r['return'],r['result'],r['remove'],r['apply'],r['puts']),(0,-5,1,1,4))

    def test_normal_apply_releases_node_references(self):
        r=self.run_case(0)
        self.assertEqual((r['return'],r['result'],r['remove'],r['apply'],r['puts']),(0,0,1,1,4))


if __name__ == '__main__':
    unittest.main()
