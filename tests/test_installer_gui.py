"""Host-only safety checks for the graphical installer command boundary."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('j701f_installer_gui', ROOT / 'tools/installer-gui.py')
gui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gui)


class InstallerGuiTests(unittest.TestCase):
    def setUp(self):
        self.values = {
            'release': str(ROOT / 'build/release'),
            'phone_ip': '192.0.2.1',
            'known_hosts': str(ROOT / 'build/phone-ssh-known-hosts'),
            'mtp_sd': '',
            'from_recovery': False,
            'backup_userdata': True,
            'reboot': False,
            'bundle': str(ROOT / 'build/first-install'),
            'sd': '',
            'output': str(ROOT / 'build/j701f-install.zip'),
            'embed': False,
        }

    def test_release_dry_run_has_no_write_flags(self):
        command = gui.build_command('release', self.values)
        self.assertEqual(command[:3], [sys.executable, '-u', str(ROOT / 'scripts/install-release.py')])
        for flag in ('--execute', '--erase-userdata', '--backup-userdata', '--reboot'):
            self.assertNotIn(flag, command)
        self.assertEqual(command[command.index('--phone-ip') + 1], '192.0.2.1')

    def test_recovery_write_uses_backup_and_no_network_address(self):
        self.values.update(from_recovery=True, reboot=True)
        command = gui.build_command('release', self.values, write=True)
        for flag in ('--from-recovery', '--execute', '--erase-userdata', '--backup-userdata', '--reboot'):
            self.assertIn(flag, command)
        self.assertNotIn('--phone-ip', command)

    def test_running_system_write_requires_ipv4(self):
        self.values['phone_ip'] = ''
        with self.assertRaises(ValueError):
            gui.build_command('release', self.values, write=True)
        self.values['phone_ip'] = 'not-an-ip'
        with self.assertRaises(ValueError):
            gui.build_command('release', self.values, write=True)

    def test_first_install_stage_is_opt_in_and_needs_sd(self):
        command = gui.build_command('first', self.values)
        self.assertNotIn('--stage', command)
        with self.assertRaises(ValueError):
            gui.build_command('first', self.values, write=True)
        self.values['sd'] = '/media/card'
        command = gui.build_command('first', self.values, write=True)
        self.assertIn('--stage', command)
        self.assertEqual(command[command.index('--sd') + 1], '/media/card')

    def test_zip_command_never_contains_phone_or_odin(self):
        self.values['embed'] = True
        command = gui.build_command('zip', self.values, write=True)
        self.assertEqual(command[2], str(ROOT / 'tools/build-recovery-zip.py'))
        self.assertIn('--embed', command)
        self.assertNotIn('odin4', ' '.join(command))
        self.assertNotIn('--execute', command)

    def test_usb_detection_filters_serial_and_rejects_ambiguity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            tty, dev = root / 'tty', root / 'dev'
            tty.mkdir(); dev.mkdir()
            for number, serial in ((0, gui.SERIAL_ID), (1, 'another-device')):
                usb = root / f'usb{number}'
                usb.mkdir()
                (usb / 'serial').write_text(serial + '\n')
                node = tty / f'ttyACM{number}'
                node.mkdir()
                (node / 'device').symlink_to(usb, target_is_directory=True)
                (dev / node.name).touch()
            ports = gui.diagnostic_ports(tty, dev)
            self.assertEqual(ports, [dev / 'ttyACM0'])
            self.assertEqual(gui.require_one_phone(ports), dev / 'ttyACM0')
            with self.assertRaises(ValueError):
                gui.require_one_phone([])
            with self.assertRaises(ValueError):
                gui.require_one_phone(ports * 2)

    def test_wipe_requires_exact_phrase_and_backup_warning(self):
        prompts = []
        def yes(title, message):
            prompts.append(title)
            return True
        def phrase(title, message):
            return 'ERASE USERDATA'
        self.assertTrue(gui.confirm_write('release', self.values, yes, phrase))
        self.assertEqual(prompts, ['Erase USERDATA'])
        self.assertFalse(gui.confirm_write('release', self.values, yes, lambda *_: 'erase userdata'))
        self.values['backup_userdata'] = False
        self.values['reboot'] = True
        prompts.clear()
        self.assertTrue(gui.confirm_write('release', self.values, yes, phrase))
        self.assertEqual(prompts, ['No backup selected', 'Reboot after installation', 'Erase USERDATA'])
        self.assertFalse(gui.confirm_write('release', self.values, lambda *_: False, phrase))

    def test_sd_stage_and_zip_overwrite_have_separate_confirmations(self):
        self.assertTrue(gui.confirm_write('first', self.values, lambda *_: True,
                                          lambda *_: 'STAGE SD'))
        self.assertFalse(gui.confirm_write('first', self.values, lambda *_: True,
                                           lambda *_: 'ERASE USERDATA'))
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'installer.zip'
            target.touch()
            self.values['output'] = str(target)
            self.assertFalse(gui.confirm_write('zip', self.values, lambda *_: True,
                                               lambda *_: 'STAGE SD'))
            self.assertTrue(gui.confirm_write('zip', self.values, lambda *_: True,
                                              lambda *_: 'REPLACE ZIP'))


if __name__ == '__main__':
    unittest.main()
