"""Check RAM overlay scope and native trial equivalence, not panel operation."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fit_props', ROOT / 'tools/build-mainline-fit.py')
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)
OUT = ROOT / 'build/kernel/display-runtime'


@unittest.skipUnless((OUT / 'merged-native.dtb').is_file(), 'Build display overlay first')
class RuntimeTreeTests(unittest.TestCase):
    def setUp(self):
        self.base = fit.fit_properties((OUT / 'physical-base.dtb').read_bytes())
        self.native = fit.fit_properties((OUT / 'merged-native.dtb').read_bytes())
        self.trial = fit.fit_properties((ROOT / 'build/kernel/j701f-displaytrial3/exynos7870-j7velte-diagnostic.dtb').read_bytes())

    def test_only_display_nodes_and_overlay_symbols_change(self):
        allowed = ('/chosen/framebuffer@67000000/', '/soc@0/dsi@14800000/',
                   '/soc@0/display-controller@14830000/', '/soc@0/iommu@14860000/',
                   '/__symbols__/')
        changes = [key for key in self.base.keys() | self.native.keys()
                   if self.base.get(key) != self.native.get(key)]
        self.assertTrue(changes)
        self.assertEqual([key for key in changes if not key.startswith(allowed)], [])

    def test_hardware_properties_match_prepared_trial(self):
        # Phandles for newly added endpoints differ, so verify their targets
        # structurally instead of comparing meaningless numeric handle values.
        for node in ('/soc@0/dsi@14800000/', '/soc@0/display-controller@14830000/',
                     '/soc@0/iommu@14860000/'):
            keys = {k for k in self.trial if k.startswith(node)}
            for key in keys:
                if key.endswith(('/phandle', '/remote-endpoint')):
                    continue
                with self.subTest(key=key):
                    if key.endswith(('-supply', '-gpios')):
                        def reference(props, value):
                            target = next(k[:-8] for k, v in props.items()
                                          if k.endswith('/phandle') and v == value[:4])
                            return target, value[4:]
                        self.assertEqual(reference(self.native, self.native[key]),
                                         reference(self.trial, self.trial[key]))
                    else:
                        self.assertEqual(self.native.get(key), self.trial[key])
        self.assertNotIn('/soc@0/display-controller@14830000/iommus', self.native)
        dsi = '/soc@0/dsi@14800000/'
        output = dsi + 'ports/port@1/endpoint/'
        panel = dsi + 'panel@0/port/endpoint/'
        self.assertEqual(self.native[output+'remote-endpoint'], self.native[panel+'phandle'])
        self.assertEqual(self.native[panel+'remote-endpoint'], self.native[output+'phandle'])

    def test_ram_reservations_unchanged(self):
        for key, value in self.base.items():
            if key.startswith(('/reserved-memory/', '/ramoops@67900000/')):
                self.assertEqual(self.native[key], value)


if __name__ == '__main__':
    unittest.main()
