#!/usr/bin/env python3
"""Bounded read-only phone counters for a coordinated browser trial.

No file installation, settings changes, process control or media playback.
The matching phone lock is mandatory even though individual reads are cheap.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
PHONE = os.environ.get('J701F_PHONE_IP') or (
    (ROOT / '.phone-ip').read_text().strip() if (ROOT / '.phone-ip').exists() else 'j701f.local')

SCRIPT = r'''
set -eu
export LC_ALL=C
printf 'KERNEL %s\n' "$(uname -r)"
i=0
while [ "$i" -lt SAMPLE_COUNT ]; do
    read up rest < /proc/uptime
    printf 'BEGIN %s %s %s\n' "$i" "$up" "$(date +%s)"
    awk '$1 ~ /^cpu([0-9]+)?$/ {print "CPU",$0} $1=="btime" {print "BOOT_TIME",$2}' /proc/stat
    awk '$1 ~ /^(MemTotal:|MemFree:|MemAvailable:|Buffers:|Cached:|SReclaimable:|Shmem:|SwapTotal:|SwapFree:|Dirty:|Writeback:)$/ {print "MEM",$1,$2}' /proc/meminfo
    awk '$1 ~ /^(pgmajfault|pswpin|pswpout|oom_kill|pgscan_direct|pgscan_kswapd|pgsteal_direct|pgsteal_kswapd)$/ {print "VM",$1,$2}' /proc/vmstat
    for p in /sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq; do
        [ -r "$p" ] || continue
        read v < "$p"; printf 'CPU_KHZ %s %s\n' "$p" "$v"
    done
    read online < /sys/devices/system/cpu/online
    printf 'ONLINE %s\n' "$online"
    for p in /sys/class/devfreq/*/cur_freq; do
        [ -r "$p" ] || continue
        read v < "$p"; printf 'DEVFREQ_HZ %s %s\n' "$p" "$v"
    done
    for p in /sys/class/thermal/thermal_zone*; do
        [ -r "$p/type" ] && [ -r "$p/temp" ] || continue
        read kind < "$p/type"; read v < "$p/temp"
        printf 'THERMAL_MC %s %s %s\n' "$p" "$kind" "$v"
    done
    for kind in cpu memory io; do
        if [ -r "/proc/pressure/$kind" ]; then
            awk -v kind="$kind" '{print "PSI",kind,$0}' "/proc/pressure/$kind"
        else
            printf 'PSI_UNAVAILABLE %s\n' "$kind"
        fi
    done
    p=/sys/module/panfrost/parameters/shrinker_purge
    if [ -r "$p" ]; then read v < "$p"; printf 'PANFROST_PURGE %s\n' "$v"; fi
    read up rest < /proc/uptime
    printf 'END %s %s\n' "$i" "$up"
    i=$((i+1))
    [ "$i" -ge SAMPLE_COUNT ] || sleep 1
done
'''


def parse_capture(raw):
    result = {'kernel': None, 'samples': [], 'incomplete_sample': False}
    sample = None
    lines = raw.splitlines()
    trailing_fragment = bool(raw and not raw.endswith('\n'))
    if trailing_fragment:
        lines = lines[:-1]
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        tag, *values = parts
        if tag == 'KERNEL' and sample is None:
            result['kernel'] = ' '.join(values)
        elif tag == 'BEGIN':
            if sample is not None:
                raise ValueError('Nested sample')
            index, uptime, epoch = values
            if int(index) != len(result['samples']):
                raise ValueError('Non-sequential samples')
            sample = dict(index=int(index), uptime_start_s=float(uptime), epoch_s=int(epoch),
                          memory_kib={}, vm={}, cpu_khz={}, devfreq_hz={}, thermal_mc={},
                          psi={}, psi_unavailable=[], per_core_ticks={})
        elif sample is None:
            raise ValueError('Unexpected output outside sample: ' + tag)
        elif tag == 'CPU':
            if len(values) < 9 or (values[0] != 'cpu'
                                  and not (values[0].startswith('cpu') and values[0][3:].isdigit())):
                raise ValueError('Missing aggregate CPU counters')
            ticks = [int(v) for v in values[1:9]]
            if values[0] == 'cpu': sample['cpu_ticks'] = ticks
            else: sample['per_core_ticks'][values[0]] = ticks
        elif tag == 'BOOT_TIME':
            sample['boot_epoch_s'] = int(values[0])
        elif tag in ('MEM', 'VM', 'CPU_KHZ', 'DEVFREQ_HZ'):
            key, value = values
            field = {'MEM': 'memory_kib', 'VM': 'vm', 'CPU_KHZ': 'cpu_khz',
                     'DEVFREQ_HZ': 'devfreq_hz'}[tag]
            sample[field][key.rstrip(':')] = int(value)
        elif tag == 'THERMAL_MC':
            if len(values) < 3:
                raise ValueError('Invalid thermal reading')
            path, kind, value = values[0], ' '.join(values[1:-1]), values[-1]
            sample['thermal_mc'][path] = dict(type=kind, value=int(value))
        elif tag == 'PSI':
            kind, category, *counters = values
            sample['psi'].setdefault(kind, {})[category] = dict(
                field.split('=', 1) for field in counters)
        elif tag == 'PSI_UNAVAILABLE':
            sample['psi_unavailable'].extend(values)
        elif tag == 'ONLINE':
            sample['online'] = values[0]
        elif tag == 'PANFROST_PURGE':
            sample['panfrost_shrinker_purge'] = int(values[0])
        elif tag == 'END':
            index, uptime = values
            if int(index) != sample['index'] or not {'cpu_ticks', 'boot_epoch_s'} <= sample.keys():
                raise ValueError('Invalid sample end or missing CPU data')
            if not {'MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'} <= sample['memory_kib'].keys():
                raise ValueError('Missing memory counters')
            sample['uptime_end_s'] = float(uptime)
            sample['read_duration_ms'] = round(
                (sample['uptime_end_s'] - sample['uptime_start_s']) * 1000, 3)
            if sample['read_duration_ms'] < 0:
                raise ValueError('Uptime moved backwards')
            result['samples'].append(sample)
            sample = None
        else:
            raise ValueError('Unexpected sample field: ' + tag)
    result['incomplete_sample'] = sample is not None or trailing_fragment
    return result


def summarise(capture):
    samples = capture['samples']
    if not samples:
        return None
    summary = dict(sample_count=len(samples),
                   span_s=samples[-1]['uptime_end_s'] - samples[0]['uptime_start_s'],
                   min_available_kib=min(s['memory_kib']['MemAvailable'] for s in samples),
                   max_swap_used_kib=max(s['memory_kib']['SwapTotal'] - s['memory_kib']['SwapFree']
                                         for s in samples),
                   median_read_duration_ms=statistics.median(s['read_duration_ms'] for s in samples),
                   max_read_duration_ms=max(s['read_duration_ms'] for s in samples),
                   vm_delta={}, cpu_busy_percent=None, per_core_busy_percent={})
    if len(samples) > 1:
        if len({s['boot_epoch_s'] for s in samples}) != 1:
            raise ValueError('Reboot during capture')
        delta = [b - a for a, b in zip(samples[0]['cpu_ticks'], samples[-1]['cpu_ticks'])]
        if any(v < 0 for v in delta) or summary['span_s'] <= 0:
            raise ValueError('Counter reset or reboot during capture')
        total = sum(delta)
        if total:
            summary['cpu_busy_percent'] = round(100 * (total - delta[3] - delta[4]) / total, 3)
        for core in samples[0]['per_core_ticks'].keys() & samples[-1]['per_core_ticks'].keys():
            delta = [b - a for a, b in zip(samples[0]['per_core_ticks'][core],
                                         samples[-1]['per_core_ticks'][core])]
            if any(v < 0 for v in delta):
                raise ValueError('CPU counter reset: ' + core)
            total = sum(delta)
            summary['per_core_busy_percent'][core] = (
                round(100 * (total - delta[3] - delta[4]) / total, 3) if total else None)
        for key in samples[0]['vm'].keys() & samples[-1]['vm'].keys():
            value = samples[-1]['vm'][key] - samples[0]['vm'][key]
            if value < 0:
                raise ValueError('VM counter reset: ' + key)
            summary['vm_delta'][key] = value
    return summary


def require_lock(worker, seconds):
    lock = ROOT / 'build/coord/locks/phone'
    if (lock / 'owner').read_text().strip() != worker:
        raise ValueError('Acquire the matching phone lock first')
    expiry = int((lock / 'time').read_text()) + 60 * int((lock / 'ttl').read_text())
    if expiry - time.time() < seconds + 60:
        raise ValueError('Renew phone lock before sampling')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=('codex', 'claude'), default='codex')
    parser.add_argument('--samples', type=int, default=18)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not 2 <= args.samples <= 45:
        parser.error('samples must be 2–45 (one-second sleeps between samples)')
    output = args.out.resolve()
    if not output.is_relative_to(ROOT / 'build') or output.suffix != '.json' or output.exists():
        parser.error('Choose a new build/*.json output')
    require_lock(args.worker, args.samples + 10)
    command = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8',
               '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
               '-o', 'StrictHostKeyChecking=yes', '-o',
               'UserKnownHostsFile=' + str(ROOT / 'build/phone-ssh-known-hosts'),
               'burak-alpine@' + PHONE, 'sh -s']
    started = datetime.now(timezone.utc).isoformat()
    timed_out = False
    try:
        run = subprocess.run(command, input=SCRIPT.replace('SAMPLE_COUNT', str(args.samples)),
                             text=True, capture_output=True, timeout=args.samples + 10)
        raw, stderr, status = run.stdout, run.stderr, run.returncode
    except subprocess.TimeoutExpired as error:
        raw = error.stdout or b''
        stderr = error.stderr or b''
        if isinstance(raw, bytes): raw = raw.decode(errors='replace')
        if isinstance(stderr, bytes): stderr = stderr.decode(errors='replace')
        status, timed_out = None, True
    parse_error = None
    try:
        capture = parse_capture(raw)
        summary = summarise(capture)
    except ValueError as error:
        capture, summary, parse_error = None, None, str(error)
    report = dict(schema='j701f-phone-perf-v1', scope='phone', worker=args.worker,
                  host_started_utc=started, host_finished_utc=datetime.now(timezone.utc).isoformat(),
                  ssh_status=status, timed_out=timed_out, stderr=stderr,
                  requested_samples=args.samples, capture=capture, summary=summary,
                  valid=status == 0 and not timed_out and capture is not None
                        and bool(capture['kernel']) and not capture['incomplete_sample']
                        and len(capture['samples']) == args.samples,
                  limits=['One-second sleeps plus sampling cost, not exactly 1 Hz',
                          'CPU percentage is aggregate busy time across all cores; excludes iowait',
                          'Aggregate CPU load cannot identify or rule out a single-thread bottleneck',
                          'sysfs frequencies are driver-reported, not physical measurements',
                          'Counters include all concurrent system activity',
                          'Sampling itself adds load; retain read-duration measurements',
                          'No panel presentation timestamps, app attribution or black-tile detection'])
    if parse_error:
        report.update(parse_error=parse_error, raw_stdout=raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(output), 'valid': report['valid'], 'summary': report['summary']}))
    return 0 if report['valid'] else 3


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit('Phone performance capture: ' + str(error))
