#!/usr/bin/env node
// Attach only to an already-open benchmark tab on a loopback CDP endpoint.
// Never opens/navigates unrelated tabs, changes browser settings or plays media.
import {readFile, writeFile, mkdir, access} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const options = {endpoint: 'http://127.0.0.1:9222', url: 'http://127.0.0.1:8765/',
  scope: 'host-check', worker: 'codex', seconds: 12, warmup: 2, viewport: 'fixed'};
for (let index = 0; index < args.length; index += 2) {
  const key = args[index].replace(/^--/, '');
  if (!['endpoint', 'url', 'scope', 'worker', 'seconds', 'warmup', 'viewport', 'out'].includes(key)
      || args[index + 1] === undefined) throw new Error('Unknown/missing option: ' + args[index]);
  options[key] = args[index + 1];
}
const require = (value, message) => { if (!value) throw new Error(message); };
require(typeof WebSocket === 'function',
  'WebSocket unavailable: use Node 22+ or node --experimental-websocket on Node 20');
const local = value => ['127.0.0.1', 'localhost', '[::1]'].includes(value.hostname);
const endpoint = new URL(options.endpoint);
const pageURL = new URL(options.url);
require(endpoint.protocol === 'http:' && local(endpoint), 'Use a loopback HTTP CDP endpoint');
require(pageURL.protocol === 'http:' && local(pageURL), 'Benchmark must use loopback HTTP');
require(!endpoint.username && !endpoint.password && !pageURL.username && !pageURL.password,
  'No credentials in benchmark URLs');
require(['host-check', 'phone'].includes(options.scope), 'scope must be host-check or phone');
require(['codex', 'claude'].includes(options.worker), 'Unknown lock worker');
require(['fixed', 'toolbar'].includes(options.viewport), 'viewport must be fixed or toolbar');
require(options.out, 'Choose a new --out file under build/');
const output = path.resolve(options.out);
require(output.startsWith(ROOT + '/build/') && output.endsWith('.json'), 'Output must be build/*.json');
let exists = false;
try { await access(output); exists = true; } catch (error) { if (error.code !== 'ENOENT') throw error; }
require(!exists, 'Output already exists; choose another run label');
const seconds = Number(options.seconds), warmup = Number(options.warmup);
require(Number.isFinite(seconds) && seconds >= .5 && seconds <= 60
  && Number.isFinite(warmup) && warmup >= 0 && warmup <= 10, 'Invalid bounded run duration');
if (options.scope === 'phone') {
  const locks = path.join(ROOT, 'build/coord/locks/phone');
  const owner = (await readFile(path.join(locks, 'owner'), 'utf8')).trim();
  const started = Number(await readFile(path.join(locks, 'time'), 'utf8'));
  const ttl = Number(await readFile(path.join(locks, 'ttl'), 'utf8'));
  require(owner === options.worker && started + ttl * 60 - Date.now() / 1000 > seconds + warmup + 60,
    'Acquire/renew the phone lock before a phone benchmark');
}
const targetsResponse = await fetch(new URL('/json/list', endpoint), {signal: AbortSignal.timeout(8000)});
require(targetsResponse.ok, 'CDP target list failed');
const targets = await targetsResponse.json();
const matches = targets.filter(target => target.type === 'page' && target.url === pageURL.href);
require(matches.length === 1, 'Open exactly one benchmark tab at the requested URL first');
const target = matches[0];
const socketURL = new URL(target.webSocketDebuggerUrl);
require(socketURL.protocol === 'ws:' && local(socketURL), 'CDP websocket must stay on loopback');
const hashes = {};
for (const file of ['index.html', 'style.css', 'stats.mjs', 'bench.js']) {
  hashes[file] = createHash('sha256').update(await readFile(path.join(ROOT, 'bench/scroll', file))).digest('hex');
}
const ws = new WebSocket(socketURL);
await new Promise((resolve, reject) => {
  const timer = setTimeout(() => { ws.close(); reject(new Error('CDP websocket open timeout')); }, 8000);
  ws.addEventListener('open', () => { clearTimeout(timer); resolve(); }, {once: true});
  ws.addEventListener('error', () => { clearTimeout(timer); reject(new Error('CDP websocket failed')); }, {once: true});
});
let sequence = 0;
const pending = new Map();
ws.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  const request = pending.get(message.id);
  if (!request) return;
  pending.delete(message.id); clearTimeout(request.timer);
  if (message.error) request.reject(new Error(JSON.stringify(message.error)));
  else request.resolve(message.result);
});
ws.addEventListener('close', () => {
  for (const request of pending.values()) {
    clearTimeout(request.timer); request.reject(new Error('CDP socket closed'));
  }
  pending.clear();
});
function send(method, params = {}, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(method + ' timed out')); }, timeout);
    pending.set(id, {resolve, reject, timer});
    ws.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression, timeout = 10000) {
  const response = await send('Runtime.evaluate', {
    expression, awaitPromise: true, returnByValue: true,
  }, timeout);
  require(!response.exceptionDetails, 'Page exception: ' + JSON.stringify(response.exceptionDetails));
  return response.result.value;
}
const startedAt = new Date().toISOString();
try {
  const identity = await evaluate('({schema:window.scrollBench?.schema, url:location.href, '
    + 'visible:document.visibilityState, running:window.scrollBench?.running})');
  require(identity?.schema === 'j701f-scroll-v1' && identity.url === pageURL.href,
    'Target is not the expected benchmark');
  require(identity.visible === 'visible' && identity.running === false, 'Idle foreground tab required');
  const report = await evaluate(`window.scrollBench.start(${JSON.stringify({
    duration_ms: seconds * 1000, warmup_ms: warmup * 1000,
    viewport_policy: options.viewport,
  })})`, (seconds + warmup + 20) * 1000);
  require(report?.schema === 'j701f-scroll-v1', 'Invalid benchmark report');
  await mkdir(path.dirname(output), {recursive: true});
  await writeFile(output, JSON.stringify({
    scope: options.scope, worker: options.worker, started_at: startedAt,
    controller_expected_asset_hashes: hashes, page: report,
    limits: ['CDP controller expects an existing foreground test tab',
      'Host-check results are functional checks, never phone performance evidence',
      'No kernel clocks, memory pressure, compositor flips or panel timestamps collected'],
  }, null, 2) + '\n', {flag: 'wx'});
  console.log(JSON.stringify({output, scope: options.scope, valid: report.valid,
    state: report.state, raf: report.raf}));
  if (!report.valid) process.exitCode = 3;
} catch (error) {
  try { await evaluate('window.scrollBench?.cancel()'); } catch { /* connection may be gone */ }
  throw error;
} finally {
  ws.close();
}
