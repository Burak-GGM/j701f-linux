import {summarise, percentile} from './stats.mjs';

const feed = document.querySelector('#feed');
for (let index = 0; index < 96; index++) {
  const card = document.createElement('article');
  const heading = document.createElement('h2');
  heading.textContent = `Card ${String(index + 1).padStart(2, '0')} · local content`;
  const pattern = document.createElement('div');
  pattern.className = 'pattern';
  pattern.style.backgroundPosition = `${index * 7}px 0`;
  const text = document.createElement('p');
  text.textContent = 'A fixed page with text, coloured patterns, borders and shadows. '
    + 'Every run uses the same content without network requests, video or audio.';
  const dots = document.createElement('div');
  dots.className = 'dots';
  for (let n = 0; n < 7; n++) dots.append(document.createElement('span'));
  card.append(heading, pattern, text, dots);
  feed.append(card);
}

const status = document.querySelector('#status');
let active = null;
let lastReport = null;
let tapSequence = 0;
const round = value => Math.round(value * 1000) / 1000;

function finish(state, reason) {
  if (!active) return;
  const run = active;
  active = null;
  cancelAnimationFrame(run.frame);
  clearTimeout(run.watchdog);
  const report = {
    schema: 'j701f-scroll-v1',
    state, reason,
    valid: state === 'complete' && run.intervals.length >= 10,
    config: run.config,
    environment: run.environment,
    viewport: {
      policy: run.config.viewport_policy,
      final_css: [innerWidth, innerHeight],
      height_range_css: run.heightRange,
      events: run.viewportEvents,
    },
    visibility_events: run.visibility,
    raf: summarise(run.intervals),
    input: {
      provenance: 'Page event timestamps; trusted is not proof of physical input',
      sample_count: run.taps.length,
      handler_delay_p95_ms: percentile(run.taps.map(tap => tap.event_to_handler_ms), .95),
      handler_to_next_raf_p95_ms: percentile(
        run.taps.filter(tap => tap.handler_to_next_raf_ms !== null)
          .map(tap => tap.handler_to_next_raf_ms), .95),
      samples: run.taps,
    },
    scroll: {start_y: run.startY, end_y: scrollY, max_y: run.maxY},
    intervals_ms: run.intervals.map(round),
    limits: [
      'requestAnimationFrame callback pacing, not panel presentation timestamps',
      'Programmatic scroll; native finger scrolling requires a separate test',
      'No proof of absence of black tiles or physical input-to-photon latency',
      'Local synthetic workload; not a network/browser-startup benchmark',
      'Toolbar policy permits bounded height changes; it cannot identify their cause',
    ],
  };
  if (!report.valid && state === 'complete') {
    report.state = 'invalid'; report.reason = 'Too few measured intervals';
  }
  lastReport = report;
  document.querySelector('#start').disabled = false;
  document.querySelector('#stop').disabled = true;
  document.querySelector('#result').hidden = false;
  document.querySelector('#json').textContent = JSON.stringify(report, null, 2);
  status.textContent = `${report.state}: ${report.reason}`;
  run.resolve(report);
}

function start(options = {}) {
  if (active) throw new Error('A run is already active');
  if (document.visibilityState !== 'visible') throw new Error('Foreground tab required');
  const config = {
    duration_ms: options.duration_ms ?? 12000,
    warmup_ms: options.warmup_ms ?? 2000,
    speed_css_px_s: options.speed_css_px_s ?? 700,
    nominal_refresh_hz: 60,
    card_count: 96,
    viewport_policy: options.viewport_policy ?? 'fixed',
  };
  if (![config.duration_ms, config.warmup_ms, config.speed_css_px_s].every(Number.isFinite)
      || config.duration_ms < 500 || config.duration_ms > 60000
      || config.warmup_ms < 0 || config.warmup_ms > 10000
      || config.speed_css_px_s < 50 || config.speed_css_px_s > 3000
      || !['fixed', 'toolbar'].includes(config.viewport_policy)) {
    throw new Error('Invalid benchmark bounds');
  }
  document.querySelector('#result').hidden = true;
  scrollTo(0, 0);
  const maxY = document.documentElement.scrollHeight - innerHeight;
  if (maxY < innerHeight) throw new Error('Page must exceed one scrollable viewport');
  document.querySelector('#start').disabled = true;
  document.querySelector('#stop').disabled = false;
  const promise = new Promise(resolve => {
    active = {
      resolve, config, maxY, startY: scrollY, intervals: [], taps: [], visibility: [],
      lastHeight: innerHeight, heightRange: [innerHeight, innerHeight], viewportEvents: [],
      first: null, sampleStart: null, previous: null, frame: 0,
      environment: {
        user_agent: navigator.userAgent,
        viewport_css: [innerWidth, innerHeight], device_pixel_ratio: devicePixelRatio,
        visibility: document.visibilityState, hardware_concurrency: navigator.hardwareConcurrency,
        time_origin_epoch_ms: performance.timeOrigin,
        performance_start_ms: performance.now(), wall_start_epoch_ms: Date.now(),
        scroll_height_css: document.documentElement.scrollHeight,
      },
    };
    // Does not rely on rAF to notice hidden tabs. A delayed timer also records
    // invalidity instead of quietly treating a short sample as a completed run.
    active.watchdog = setTimeout(() => finish('invalid', 'Wall-clock watchdog'),
      config.duration_ms + config.warmup_ms + 15000);
    function frame(timestamp) {
      const run = active;
      if (!run) return;
      if (document.visibilityState !== 'visible') return finish('invalid', 'Tab hidden');
      const initialHeight = run.environment.viewport_css[1];
      const heightChanged = innerHeight !== run.lastHeight;
      // Mobile browser chrome changes height while scrolling. Opt in explicitly;
      // rotation, zoom and large resizes still invalidate the measurement.
      const permittedHeight = config.viewport_policy === 'toolbar'
        && Math.abs(innerHeight - initialHeight) <= initialHeight * .25;
      if (heightChanged || innerWidth !== run.environment.viewport_css[0]
          || devicePixelRatio !== run.environment.device_pixel_ratio) {
        run.viewportEvents.push({at_ms: round(timestamp),
          phase: run.sampleStart === null ? 'warmup' : 'measurement',
          viewport_css: [innerWidth, innerHeight], device_pixel_ratio: devicePixelRatio});
      }
      if (innerWidth !== run.environment.viewport_css[0]
          || devicePixelRatio !== run.environment.device_pixel_ratio
          || (heightChanged && !permittedHeight)) {
        return finish('invalid', 'Viewport or scale changed');
      }
      if (heightChanged) {
        run.lastHeight = innerHeight;
        run.heightRange[0] = Math.min(run.heightRange[0], innerHeight);
        run.heightRange[1] = Math.max(run.heightRange[1], innerHeight);
        run.maxY = document.documentElement.scrollHeight - innerHeight;
      }
      run.first ??= timestamp;
      const elapsed = timestamp - run.first;
      const travel = elapsed * config.speed_css_px_s / 1000;
      const period = 2 * run.maxY;
      const position = travel % period;
      scrollTo(0, position <= run.maxY ? position : period - position);
      if (elapsed >= config.warmup_ms) {
        run.sampleStart ??= timestamp;
        if (run.previous !== null) run.intervals.push(timestamp - run.previous);
        run.previous = timestamp;
        if (timestamp - run.sampleStart >= config.duration_ms) {
          return finish('complete', 'Timed sample complete');
        }
      }
      run.frame = requestAnimationFrame(frame);
    }
    status.textContent = 'Running: keep this tab in the foreground';
    active.frame = requestAnimationFrame(frame);
  });
  return promise;
}

document.addEventListener('visibilitychange', () => {
  if (!active) return;
  active.visibility.push({at_ms: performance.now(), state: document.visibilityState});
  if (document.visibilityState !== 'visible') finish('invalid', 'Tab hidden');
});
document.querySelector('#ping').addEventListener('pointerdown', event => {
  const now = performance.now();
  let origin = event.timeStamp;
  if (origin > now + 60000) origin -= performance.timeOrigin;
  const delay = now - origin;
  if (!active || !Number.isFinite(delay) || delay < 0 || delay > 60000) return;
  const run = active;
  const sample = {trusted: event.isTrusted, event_to_handler_ms: round(delay),
    handler_to_next_raf_ms: null};
  run.taps.push(sample);
  event.currentTarget.textContent = `Tap response ${++tapSequence}`;
  requestAnimationFrame(() => {
    if (active === run) sample.handler_to_next_raf_ms = round(performance.now() - now);
  });
});
document.querySelector('#start').addEventListener('click', () => {
  try { start({viewport_policy: document.querySelector('#toolbar').checked ? 'toolbar' : 'fixed'})
    .catch(error => { status.textContent = error.message; }); }
  catch (error) { status.textContent = error.message; }
});
document.querySelector('#stop').addEventListener('click', () => finish('cancelled', 'User stopped'));
document.querySelector('#save').addEventListener('click', () => {
  if (!lastReport) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(lastReport, null, 2)],
    {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url; link.download = 'j701f-scroll.json'; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
window.scrollBench = {schema: 'j701f-scroll-v1', start,
  cancel: () => finish('cancelled', 'Controller stopped'),
  get report() { return lastReport; }, get running() { return active !== null; }};
