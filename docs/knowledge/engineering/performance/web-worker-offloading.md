# web-worker-offloading

**Issue:** CPU-intensive work blocks the main thread
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Web Workers run in background threads, separate from the main thread. Ideal for data transformation, parsing, compression, image processing, and any CPU-bound work.

## Pattern / Solution
1. Create a worker: const worker = new Worker('/worker.js').\n2. Communicate via postMessage / onmessage (structured clone algorithm).\n3. Use Comlink for async RPC over Worker messages.\n4. Use SharedArrayBuffer + Atomics for high-frequency shared data.\n5. Consider a worker pool for parallel workloads.

## Gotchas
- Workers cannot access the DOM; only use for pure computation and data.\n- postMessage clones data by default; use Transferable objects (ArrayBuffer) to avoid copies.\n- Worker startup time (~1-5ms) is not free; pool workers for short repeated tasks.

## Related
javascript-main-thread, long-task-detection, nodejs-worker-threads
