export function percentile(values, quantile) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(quantile * sorted.length) - 1)];
}

export function summarise(intervals) {
  if (intervals.some(value => !Number.isFinite(value) || value <= 0)) {
    throw new Error('Invalid frame interval');
  }
  const total = intervals.reduce((sum, value) => sum + value, 0);
  return {
    interval_count: intervals.length,
    measured_ms: total,
    callback_rate_hz: total ? intervals.length * 1000 / total : null,
    median_ms: percentile(intervals, .5),
    p95_ms: percentile(intervals, .95),
    p99_ms: percentile(intervals, .99),
    max_ms: intervals.length ? Math.max(...intervals) : null,
    intervals_over_25ms: intervals.filter(value => value > 25).length,
    intervals_over_50ms: intervals.filter(value => value > 50).length,
    missed_60hz_intervals_estimate: intervals.reduce(
      (count, value) => count + Math.max(0, Math.round(value / (1000 / 60)) - 1), 0),
  };
}
