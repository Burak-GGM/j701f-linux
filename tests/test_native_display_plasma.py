"""Synthetic Plasma evidence and real PTY process cleanup; no GUI/GPU used."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


TRIAL = module('plasma_trial', 'tools/run-native-display-trial.py')
GUI = module('plasma_gui', 'tools/native-display-gui.py')
SUPPORT = 'OpenGL renderer string: Mali-T830 MC1 (Panfrost)\n'
GEARS = '''GEARS_EGL_SIZE width=720 height=1280
GEARS_GL_RENDERER=Mali-T830 MC1 (Panfrost)
100 frames in 5.0 seconds = 20.000 FPS
298 frames in 5.0 seconds = 59.600 FPS
299 frames in 5.0 seconds = 59.800 FPS
297 frames in 5.0 seconds = 59.400 FPS
'''
NATIVE = dict(mode='native', completed=True, drm_devices={'card2': 'exynos-drm'},
              kwin_drm_fds=['/dev/dri/card2'], native_active_state=True)


class PlasmaEvidenceTests(unittest.TestCase):
    def test_warmup_excluded_and_no_zero_copy_or_appearance_claim(self):
        result = TRIAL.analyse_plasma(NATIVE, GEARS, SUPPORT)
        self.assertTrue(result['measurement_valid'])
        self.assertEqual(result['median_app_swap_fps'], 59.6)
        self.assertEqual(result['egl_size'], (720, 1280))
        self.assertFalse(result['scanout_copy_verified_absent'])
        self.assertEqual(result['physical_appearance'], 'unseen')

    def test_real_gpu_required_for_application_and_compositor(self):
        for gears, support in ((GEARS.replace('Panfrost', 'llvmpipe'), SUPPORT),
                               (GEARS, SUPPORT.replace('Panfrost', 'llvmpipe'))):
            self.assertFalse(TRIAL.analyse_plasma(NATIVE, gears, support)['measurement_valid'])

    def test_native_session_must_open_exynos_without_firmware_drm(self):
        for measurement in (dict(NATIVE, kwin_drm_fds=[]),
                            dict(NATIVE, drm_devices={'card2': 'exynos-drm', 'card0': 'simple-framebuffer'}),
                            dict(NATIVE, completed=False), dict(NATIVE, mode='unknown')):
            self.assertFalse(TRIAL.analyse_plasma(measurement, GEARS, SUPPORT)['measurement_valid'])
        self.assertFalse(TRIAL.analyse_plasma(dict(NATIVE, native_active_state=False), GEARS, SUPPORT)['measurement_valid'])

    def test_no_geometry_or_insufficient_samples_is_not_a_comparison(self):
        for gears in (GEARS.replace('GEARS_EGL_SIZE', 'missing'),
                      GEARS.replace('720', '0'), '\n'.join(GEARS.splitlines()[:-1]), ''):
            self.assertFalse(TRIAL.analyse_plasma(NATIVE, gears, SUPPORT)['measurement_valid'])

    def test_missing_or_stale_native_prerequisite_refuses_plasma(self):
        report = dict(baseline_boot_sha256='boot', kernel_image_sha256='image')
        previous = dict(automatic_return_verified=True, native_hardware_verified=True,
                        pll_initialization=dict(first_init_verified=True),
                        shared_buffer_render=dict(shared_gpu_buffer_verified=True, framebuffer_object_verified=True),
                        before=dict(boot_sha256='boot'), source_build=dict(kernel_image_sha256='image'))
        TRIAL.require_native_prerequisite(previous, report)
        for key in previous:
            changed = dict(previous)
            del changed[key]
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                TRIAL.require_native_prerequisite(changed, report)
        with self.assertRaises(RuntimeError):
            TRIAL.require_native_prerequisite(previous, dict(report, baseline_boot_sha256='other'))


class PtyBenchmarkTests(unittest.TestCase):
    def test_helper_refuses_missing_watchdog_before_any_system_command(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(GUI, 'command') as call, \
                patch.object(sys, 'argv', ['native-display-gui.py', 'baseline']):
            with self.assertRaisesRegex(RuntimeError, 'armed root'):
                GUI.main()
        call.assert_not_called()

    def test_helper_refuses_wrong_watchdog_ancestry_before_system_commands(self):
        env = dict(J701F_DISPLAY_TRIAL_ARMED='1', J701F_DISPLAY_SUPERVISOR_PID='12345')
        with patch.dict(os.environ, env, clear=True), patch.object(GUI.os, 'geteuid', return_value=0), \
                patch.object(GUI.Path, 'read_text', return_value='PPid:\t999\n'), \
                patch.object(GUI, 'command') as call, \
                patch.object(sys, 'argv', ['native-display-gui.py', 'native']):
            with self.assertRaisesRegex(RuntimeError, 'child of watchdog'):
                GUI.main()
        call.assert_not_called()

    def test_actual_pty_delivers_lines_and_only_child_is_terminated(self):
        real_popen = subprocess.Popen
        processes = []
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder)/'fake-gears.py'
            script.write_text('import sys,time\nprint("TTY="+str(sys.stdout.isatty()),flush=True)\n'
                              'print("synthetic frame line",flush=True)\ntime.sleep(10)\n')

            def launch(argv, **kwargs):
                env = dict(kwargs['env'])
                env.pop('LD_PRELOAD', None)
                process = real_popen([sys.executable, str(script)], **dict(kwargs, env=env))
                processes.append(process)
                return process

            before = len(list(Path('/proc/self/fd').iterdir()))
            with patch.object(GUI.subprocess, 'Popen', side_effect=launch):
                log = GUI.sample_gears(dict(os.environ), {}, seconds=0.3)
            self.assertIn('TTY=True', log)
            self.assertIn('synthetic frame line', log)
            self.assertIsNotNone(processes[0].poll())
            self.assertEqual(len(list(Path('/proc/self/fd').iterdir())), before)

    def test_launch_failure_closes_both_pty_fds(self):
        before = len(list(Path('/proc/self/fd').iterdir()))
        with patch.object(GUI.subprocess, 'Popen', side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):
                GUI.sample_gears(dict(os.environ), {}, seconds=0.1)
        self.assertEqual(len(list(Path('/proc/self/fd').iterdir())), before)


if __name__ == '__main__':
    unittest.main()
