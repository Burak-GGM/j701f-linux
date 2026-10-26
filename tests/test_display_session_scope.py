"""Run the real shell scope guard against scratch files, never live processes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT/'tools/native-display-trial.sh').read_text()
GUARD = 'kwin=$(pidof kwin_wayland)' + SCRIPT.split('kwin=$(pidof kwin_wayland)', 1)[1].split(
    'timeout -s KILL 15 rc-service sddm stop', 1)[0]


class DisplayScopeTests(unittest.TestCase):
    def run_guard(self, scope='/c1', kind='wayland', service='sddm-autologin',
                  supervisor_inside=False, trial_inside=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'proc/123').mkdir(parents=True)
            (root/'proc/123/cgroup').write_text('0::'+scope+'\n')
            (root/'cgroup/c1').mkdir(parents=True)
            (root/'cgroup/c1/cgroup.kill').touch()
            procs = root/'cgroup/c1/cgroup.procs'
            procs.write_text('123\n' + ('29000\n' if supervisor_inside else ''))
            (root/'bin').mkdir()
            for name, code in {
                'pidof': 'echo 123',
                'loginctl': 'case "$4" in Type) echo "$SCOPE_TYPE";; '
                            'Service) echo "$SCOPE_SERVICE";; *) exit 1;; esac',
            }.items():
                path = root/'bin'/name
                path.write_text('#!/bin/sh\n'+code+'\n')
                path.chmod(0o755)
            code = GUARD.replace('/proc/', str(root/'proc')+'/').replace(
                'gui_scope=/sys/fs/cgroup$scope', 'gui_scope='+str(root/'cgroup')+'$scope')
            if trial_inside:
                code = 'echo $$ >> '+str(procs)+'\n'+code
            return subprocess.run(['sh', '-ec', code+'\necho SCOPE_ALLOWED\n'],
                env=dict(os.environ, PATH=str(root/'bin')+':'+os.environ['PATH'],
                         SCOPE_TYPE=kind, SCOPE_SERVICE=service,
                         J701F_DISPLAY_SUPERVISOR_PID='29000'),
                text=True, capture_output=True)

    def test_only_verified_local_sddm_wayland_scope_is_allowed(self):
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('SCOPE_ALLOWED', result.stdout)

    def test_root_or_other_scope_is_refused(self):
        for scope in ('/', '/user.slice', '/c1/../../', '/c1-extra'):
            with self.subTest(scope=scope):
                self.assertNotEqual(self.run_guard(scope=scope).returncode, 0)

    def test_non_wayland_or_other_login_service_is_refused(self):
        for opts in ({'kind': 'tty'}, {'service': 'sshd'}):
            with self.subTest(opts=opts):
                self.assertNotEqual(self.run_guard(**opts).returncode, 0)

    def test_scope_containing_trial_or_watchdog_is_refused(self):
        for opts in ({'supervisor_inside': True}, {'trial_inside': True}):
            with self.subTest(opts=opts):
                self.assertNotEqual(self.run_guard(**opts).returncode, 0)


if __name__ == '__main__':
    unittest.main()
