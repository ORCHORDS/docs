# Web Workers and SharedArrayBuffer — Browser Parallelism Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your browser application processes a 50 MB CSV upload. During parsing,
the UI freezes for 23 seconds — no scrolling, no button clicks, no
progress indicator. Users think the app has crashed. The main thread
is blocked because JavaScript is single-threaded by default and CSV
parsing is CPU-bound work that cannot be broken into small enough
async chunks to maintain 60fps responsiveness.

## Context

Web Workers run JavaScript on background threads with their own event
loop, enabling true parallelism in the browser. In 2026, three data-
sharing mechanisms exist: structured clone (copies data — safe but
slow for large buffers), transferable objects (zero-copy ownership
transfer), and SharedArrayBuffer (shared memory with Atomics for
thread-safe access). OffscreenCanvas moves rendering to workers.
Comlink simplifies the postMessage API into transparent async proxies.
The key principle: offload CPU-bound work that takes more than 50ms
to workers, but keep I/O-bound work on the main thread where the
event loop handles it efficiently.

## When workers help vs hurt

```
Beneficial (CPU-bound, parallelizable):
  → Image/video processing, canvas rendering
  → CSV/JSON parsing of large datasets
  → Cryptography, hashing
  → ML inference (WASM-based models)
  → Search indexing, sorting large arrays
  → Physics simulations, pathfinding

Not beneficial (I/O-bound):
  → HTTP requests, database queries, file reads
  → These are already async via the event loop
  → Workers add 5-30ms startup overhead without parallelism gain

Rule of thumb:
  → Tasks under 50ms: keep on main thread
  → Tasks 50-200ms: consider offloading if on interaction path
  → Tasks 200ms+: always use workers
  → Main-thread budget: >8-10ms on interaction path → offload
```

## Data transfer mechanisms

```javascript
// 1. Structured clone (default) — copies data, safe but slow
// Noticeable at ~1MB frequent, ~10MB occasional
worker.postMessage({ data: largeArrayBuffer });

// 2. Transferable objects — zero-copy, sender loses access
// Nearly instant regardless of size
worker.postMessage({ data: largeArrayBuffer }, [largeArrayBuffer]);
// largeArrayBuffer.byteLength === 0 after this line

// Transferable types: ArrayBuffer, ImageBitmap, OffscreenCanvas,
// MessagePort, ReadableStream, WritableStream
```

```javascript
// 3. SharedArrayBuffer — shared memory, requires cross-origin isolation
// Check availability first
if (self.crossOriginIsolated) {
  const sab = new SharedArrayBuffer(1024);
  const view = new Int32Array(sab);
  worker.postMessage({ buffer: sab });
} else {
  // Fall back to transferables
  const ab = new ArrayBuffer(1024);
  worker.postMessage(ab, [ab]);
}
```

## COOP/COEP headers for SharedArrayBuffer

```
SharedArrayBuffer was disabled after Spectre/Meltdown.
Re-enable with cross-origin isolation:

Required HTTP headers:
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: require-corp

Verification:
  self.crossOriginIsolated === true

Catch: every resource (images, scripts, iframes, fonts) must be
same-origin OR have Cross-Origin-Resource-Policy: cross-origin

This breaks many third-party integrations (analytics, ads, embeds).
Evaluate compatibility before enabling.
```

## Atomics API

```javascript
// Thread-safe operations on SharedArrayBuffer views
const sab = new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT * 100);
const view = new Int32Array(sab);

// Atomic read/write (indivisible)
Atomics.store(view, 0, 42);
const val = Atomics.load(view, 0);

// Atomic increment
Atomics.add(view, 1, 1);

// Compare-and-swap
Atomics.compareExchange(view, 0, 42, 99);

// Synchronization — blocking (workers only, never main thread)
Atomics.wait(view, 0, expectedValue);
Atomics.notify(view, 0, 1);

// Non-blocking wait (safe for main thread)
const result = Atomics.waitAsync(view, 0, expectedValue);
await result.value;
```

## OffscreenCanvas

```javascript
// Main thread — transfer canvas control to worker
const canvas = document.querySelector('canvas');
const offscreen = canvas.transferControlToOffscreen();
const worker = new Worker('render-worker.js');
worker.postMessage({ canvas: offscreen }, [offscreen]);

// render-worker.js — rendering off the main thread
onmessage = (evt) => {
  const canvas = evt.data.canvas;
  const ctx = canvas.getContext('2d');

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    // Heavy rendering — main thread stays responsive
    requestAnimationFrame(draw);
  }
  draw();
};
```

## Worker pool pattern

```javascript
// Simple pool with round-robin dispatch
const POOL_SIZE = navigator.hardwareConcurrency - 2;
const workers = Array.from(
  { length: POOL_SIZE },
  () => new Worker('task-worker.js')
);
let nextWorker = 0;

function dispatch(task) {
  return new Promise((resolve) => {
    const worker = workers[nextWorker];
    nextWorker = (nextWorker + 1) % POOL_SIZE;
    worker.onmessage = (e) => resolve(e.data);
    worker.postMessage(task);
  });
}
```

```javascript
// Comlink — transparent async proxies (recommended)
// worker.js
import * as Comlink from 'comlink';

const api = {
  async heavyComputation(data) {
    return processData(data);
  }
};
Comlink.expose(api);

// main.js
import * as Comlink from 'comlink';
const worker = new Worker('worker.js', { type: 'module' });
const api = Comlink.wrap(worker);

const result = await api.heavyComputation(myData);

// Transfer large buffers with Comlink
const buf = new ArrayBuffer(1_000_000);
await api.process(Comlink.transfer(buf, [buf]));
```

## Anti-patterns

- **Spawning a new worker per task** — worker startup costs 5-30ms.
  Use a persistent worker pool and dispatch tasks to it.
- **Chatty postMessage communication** — fewer, bigger messages beat
  many tiny ones. Design coarse-grained APIs between main thread
  and workers.
- **Posting large arrays without transfer** — always use the transfer
  list for ArrayBuffers. Without it, structured clone copies megabytes
  of data on every message.
- **Polling SharedArrayBuffer in tight loops** — use `Atomics.waitAsync()`
  instead. Tight polling turns the CPU into a space heater.
- **Cold WASM initialization per task** — initialize WASM modules once
  in a persistent worker, not on every task dispatch.

## Gotchas

- **No DOM access in workers** — workers cannot touch the DOM,
  `window`, or `document`. Use OffscreenCanvas for rendering and
  postMessage to update the UI.
- **`Atomics.wait()` blocks the thread** — never call it on the main
  thread. Use `Atomics.waitAsync()` which returns a promise instead.
- **COOP/COEP breaks third-party scripts** — enabling cross-origin
  isolation for SharedArrayBuffer requires every loaded resource to
  opt in with CORP headers. Third-party analytics and ad scripts
  often do not set these.
- **Module workers and bundler support** — `new Worker('x.js',
  {type: 'module'})` is supported in modern browsers but may need
  bundler configuration (Vite, webpack 5 with worker-loader).
- **Memory leaks from unreferenced workers** — call `worker.terminate()`
  when done. Orphaned workers continue running and consuming memory.

## Verification

- CPU-intensive operations (>50ms) run in Web Workers.
- Large buffer transfers use transferable objects, not structured clone.
- Worker pool size matches `navigator.hardwareConcurrency - 2`.
- SharedArrayBuffer usage gates on `crossOriginIsolated` check.
- OffscreenCanvas used for heavy rendering workloads.
- Workers are properly terminated when no longer needed.

## Related

- `documentation/categories/performance/critical-rendering-path-css-optimization.md`
- `documentation/categories/performance/sse-vs-websockets-real-time-streaming.md`
- `documentation/categories/frontend/view-transitions-api-page-navigation.md`

## Source URLs (verified 2026-08-16)

- Web Workers vs Worker Threads vs SharedArrayBuffer 2026 — https://www.pkgpulse.com/guides/web-workers-vs-worker-threads-vs-sharedarraybuffer-2026
- High-Performance JavaScript: Web Workers, SharedArrayBuffer, and Atomics — https://dev.to/rigalpatel001/high-performance-javascript-simplified-web-workers-sharedarraybuffer-and-atomics-3ig1
- 7 Worker + SharedArrayBuffer Tricks for Jank-Free UIs — https://medium.com/@bhagyarana80/7-worker-sharedarraybuffer-tricks-for-jank-free-uis-c1da3c4600f8
- OffscreenCanvas: Speed Up Canvas Operations with a Web Worker — https://web.dev/articles/offscreen-canvas
