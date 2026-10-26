"""Toolbox actions never accept arbitrary commands or widen the local scan."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'system/security-toolbox/backend.py'
spec = importlib.util.spec_from_file_location('j701f_toolbox_backend', PATH)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class LocalScope(unittest.TestCase):
    def test_large_lan_is_capped_to_24(self):
        packet = '[{"addr_info":[{"family":"inet","scope":"global","local":"192.168.1.139","prefixlen":16}]}]'
        with patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, packet)):
            self.assertEqual(backend.local_network(), '192.168.1.0/24')
            argv, timeout, _ = backend.action('lan')
        self.assertEqual(argv[-1], '192.168.1.0/24')
        self.assertEqual(argv[0], 'nmap')
        self.assertLessEqual(timeout, 90)

    def test_port_check_stays_in_local_subnet(self):
        with patch.object(backend, 'local_network', return_value='192.168.1.0/24'):
            argv, timeout, _ = backend.action('ports', '192.168.1.1')
            self.assertEqual(argv[-1], '192.168.1.1')
            self.assertLessEqual(timeout, 35)
            for target in ('8.8.8.8', '192.168.1.1;whoami', '192.168.0.1'):
                with self.assertRaises(ValueError):
                    backend.action('ports', target)

    def test_no_wifi_address_refuses_scan(self):
        with patch.object(subprocess, 'run', side_effect=FileNotFoundError()):
            with self.assertRaises(ValueError):
                backend.action('lan')

    def test_commands_are_fixed_argv_and_bounded(self):
        for name in ('wifi', 'bluetooth'):
            argv, timeout, _ = backend.action(name)
            self.assertNotIn(argv[0], ('sh', 'bash'))
            self.assertLessEqual(timeout, 30)
        with self.assertRaises(ValueError):
            backend.action('nmap -A 0.0.0.0/0')


if __name__ == '__main__':
    unittest.main()
