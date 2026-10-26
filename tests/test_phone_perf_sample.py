"""Check measurement integrity: units, guest accounting, partial output and reboot."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('perf_sample', ROOT / 'tools/phone-perf-sample.py')
PERF = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PERF)


def sample(index, uptime, cpu, available, swap_free, faults, boot=100):
    return f'''BEGIN {index} {uptime} 1000
CPU cpu {cpu}
BOOT_TIME {boot}
MEM MemTotal: 1000
MEM MemAvailable: {available}
MEM SwapTotal: 200
MEM SwapFree: {swap_free}
VM pgmajfault {faults}
CPU_KHZ /sys/policy0/scaling_cur_freq 1586000
DEVFREQ_HZ /sys/devfreq/11400000.gpu/cur_freq 343000000
THERMAL_MC /sys/thermal/thermal_zone0 soc-thermal 40000
ONLINE 0-7
PSI_UNAVAILABLE cpu
PSI_UNAVAILABLE memory
PSI_UNAVAILABLE io
PANFROST_PURGE 2
END {index} {uptime + .02}
'''


def capture(boot=100):
    # First eight CPU counters include guest time already within user/nice.
    # Extra guest fields must not be counted a second time.
    return ('KERNEL 7.1.13-BURAK-PANFROST-01\n'
            + sample(0, 10, '100 0 100 600 200 0 0 0 50 0', 500, 200, 3)
            + sample(1, 11, '110 0 110 660 220 0 0 0 60 0', 300, 100, 5, boot))


class PhonePerfTests(unittest.TestCase):
    def test_units_aggregate_busy_and_counter_deltas(self):
        parsed = PERF.parse_capture(capture())
        summary = PERF.summarise(parsed)
        self.assertFalse(parsed['incomplete_sample'])
        self.assertEqual(summary['cpu_busy_percent'], 20)
        self.assertEqual(summary['min_available_kib'], 300)
        self.assertEqual(summary['max_swap_used_kib'], 100)
        self.assertEqual(summary['vm_delta']['pgmajfault'], 2)
        self.assertEqual(summary['median_read_duration_ms'], 20)
        self.assertEqual(parsed['samples'][0]['devfreq_hz']['/sys/devfreq/11400000.gpu/cur_freq'], 343000000)

    def test_missing_pressure_remains_unavailable(self):
        first = PERF.parse_capture(capture())['samples'][0]
        self.assertEqual(first['psi'], {})
        self.assertEqual(first['psi_unavailable'], ['cpu', 'memory', 'io'])

    def test_thermal_type_can_contain_spaces(self):
        first = PERF.parse_capture(capture().replace('soc-thermal', 'package sensor'))['samples'][0]
        self.assertEqual(first['thermal_mc']['/sys/thermal/thermal_zone0']['type'], 'package sensor')

    def test_per_core_accounting_and_disappearing_core(self):
        raw = capture().replace('BEGIN 0 10 1000\n',
                                'BEGIN 0 10 1000\nCPU cpu0 10 0 10 50 0 0 0 0\nCPU cpu1 0 0 0 20 0 0 0 0\n')
        raw = raw.replace('BEGIN 1 11 1000\n', 'BEGIN 1 11 1000\nCPU cpu0 30 0 30 60 0 0 0 0\n')
        summary = PERF.summarise(PERF.parse_capture(raw))
        self.assertEqual(summary['per_core_busy_percent'], {'cpu0': 80.0})

    def test_truncated_stream_retains_only_completed_samples(self):
        parsed = PERF.parse_capture(capture().split('END 1')[0] + 'END 1')
        self.assertTrue(parsed['incomplete_sample'])
        self.assertEqual(len(parsed['samples']), 1)
        self.assertIsNone(PERF.summarise(parsed)['cpu_busy_percent'])

    def test_reboot_invalidates_aggregate(self):
        with self.assertRaisesRegex(ValueError, 'Reboot'):
            PERF.summarise(PERF.parse_capture(capture(boot=101)))

    def test_missing_core_counters_refused(self):
        with self.assertRaisesRegex(ValueError, 'CPU'):
            PERF.parse_capture(capture().replace('CPU cpu 100 0 100 600 200 0 0 0 50 0\n', ''))

    def test_counter_reset_invalidates_aggregate(self):
        with self.assertRaisesRegex(ValueError, 'Counter reset'):
            PERF.summarise(PERF.parse_capture(capture().replace('110 0 110 660 220', '90 0 90 560 180')))


if __name__ == '__main__':
    unittest.main()
