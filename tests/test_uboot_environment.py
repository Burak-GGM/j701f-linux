import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('uboot_builder', ROOT / 'tools/build-j701f-uboot.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class GeneratedEnvironmentTests(unittest.TestCase):
    GOOD = '#define CONFIG_EXTRA_ENV_TEXT "bootcmd=j701f_ramboot\\0bootdelay=0\\0stderr=nulldev\\0stdin=nulldev\\0stdout=nulldev\\0"'

    def test_real_generated_string(self):
        self.assertEqual(builder.check_generated_environment(self.GOOD)['bootcmd'], 'j701f_ramboot')

    def test_reproduces_failed_candidate_shell_comment(self):
        broken = self.GOOD.replace('"bootcmd=', '"=# Linux supplies USB\\0bootcmd=')
        with self.assertRaisesRegex(ValueError, 'key'):
            builder.check_generated_environment(broken)

    def test_duplicate_boot_command(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            builder.check_generated_environment(self.GOOD.replace('"bootcmd=', '"bootcmd=other\\0bootcmd='))

    def test_changed_command(self):
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            builder.check_generated_environment(self.GOOD.replace('j701f_ramboot', 'run bootcmd'))


if __name__ == '__main__':
    unittest.main()
