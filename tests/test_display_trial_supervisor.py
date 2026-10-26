"""Deadline/FD checks with no watchdog device access and no reboot on host."""
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('supervisor', ROOT / 'tools/display-trial-supervisor.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EndResetWait(Exception):
    pass


class SupervisorTests(unittest.TestCase):
    def exercise(self, trial=False, timeout=15, machine=b'samsung,j7velte\0', child_status=None):
        clock = [0]
        messages = io.StringIO()
        writes = []

        def sleep(seconds):
            if 'DISPLAY_TRIAL_WATCHDOG_RESET_PENDING' in messages.getvalue():
                raise EndResetWait
            clock[0] += seconds

        def ioctl(fd, request, value, mutate):
            self.assertEqual(fd, 37)
            self.assertIn(request, (mod.WDIOC_SETTIMEOUT, mod.WDIOC_GETTIMEOUT))
            value[0] = timeout

        argv = ['supervisor', '--execute', '--seconds', '10']
        argv += ['--trial', '/tmp/display.sh'] if trial else ['--rehearsal']
        child = SimpleNamespace(poll=lambda: child_status, returncode=child_status)
        with contextlib.ExitStack() as s:
            s.enter_context(patch('sys.argv', argv))
            s.enter_context(patch.object(mod.os, 'geteuid', return_value=0))
            s.enter_context(patch.object(mod.os, 'uname', return_value=SimpleNamespace(release='7.1.13-TEST')))
            s.enter_context(patch.object(mod.Path, 'read_bytes', return_value=machine))
            s.enter_context(patch.object(mod.Path, 'read_text', side_effect=lambda p=None: 'Y'))
            s.enter_context(patch.object(mod.Path, 'resolve', return_value=Path('/tmp/display.sh')))
            s.enter_context(patch.object(mod.Path, 'is_file', return_value=True))
            s.enter_context(patch.object(mod.os, 'open', return_value=37))
            close = s.enter_context(patch.object(mod.os, 'close'))
            s.enter_context(patch.object(mod.os, 'write', side_effect=lambda fd, value: writes.append((clock[0], fd, value))))
            synced_logs = []
            s.enter_context(patch.object(mod.os, 'sync', side_effect=lambda: synced_logs.append(messages.getvalue())))
            s.enter_context(patch.object(mod.fcntl, 'ioctl', side_effect=ioctl))
            s.enter_context(patch.object(mod.signal, 'signal'))
            spawn = s.enter_context(patch.object(mod.subprocess, 'Popen', return_value=child))
            s.enter_context(patch.object(mod.time, 'monotonic', side_effect=lambda: clock[0]))
            s.enter_context(patch.object(mod.time, 'sleep', side_effect=sleep))
            s.enter_context(contextlib.redirect_stdout(messages))
            if machine != b'samsung,j7velte\0' or not 5 <= timeout <= 30:
                with self.assertRaises(SystemExit):
                    mod.main()
            else:
                with self.assertRaises(EndResetWait):
                    mod.main()
            self.assertFalse(close.called, 'Never disarm or magic-close watchdog')
            if 'DISPLAY_TRIAL_WATCHDOG_RESET_PENDING' in messages.getvalue():
                self.assertIn('DISPLAY_TRIAL_WATCHDOG_RESET_PENDING', synced_logs[-1],
                              'Persist the final reset marker before the hardware reset')
        return messages.getvalue(), writes, spawn

    def test_rehearsal_stops_feeding_at_deadline_without_child(self):
        log, writes, spawn = self.exercise()
        self.assertIn('RESET_PENDING', log)
        self.assertEqual(max(t for t, _, _ in writes), 9)
        self.assertFalse(spawn.called)
        self.assertTrue(all(value == b'.' for _, _, value in writes))

    def test_stuck_child_cannot_extend_deadline_or_inherit_fd(self):
        _, writes, spawn = self.exercise(trial=True)
        self.assertEqual(max(t for t, _, _ in writes), 9)
        self.assertTrue(spawn.call_args.kwargs['close_fds'])
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        self.assertEqual(spawn.call_args.kwargs['env']['J701F_DISPLAY_TRIAL_ARMED'], '1')

    def test_failed_child_still_ends_in_reset(self):
        log, writes, _ = self.exercise(trial=True, child_status=1)
        self.assertIn('CHILD_EXIT status=1', log)
        self.assertIn('RESET_PENDING', log)
        self.assertEqual(len(writes), 1)

    def test_wrong_board_or_timeout_never_starts_trial(self):
        for opts in ({'machine': b'other\0'}, {'timeout': 120}):
            with self.subTest(opts=opts):
                _, _, spawn = self.exercise(trial=True, **opts)
                self.assertFalse(spawn.called)


if __name__ == '__main__':
    unittest.main()
