# nodejs-worker-threads

**Issue:** CPU-intensive Node.js work blocks the event loop
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Node.js Worker Threads (available since v10.5, stable in v12) run JavaScript in parallel threads, separate from the main event loop.

## Pattern / Solution
1. Import Worker, isMainThread, parentPort, workerData from worker_threads.\n2. In main thread: create Worker and listen for message events.\n3. In worker: use parentPort.postMessage to return results.\n4. Use a worker pool (piscina library) for repeated tasks.\n5. Transfer ArrayBuffers between threads to avoid copying.

## Gotchas
- Workers have their own memory space; modules must be re-required in each worker.\n- Worker startup time (~30ms) makes them unsuitable for very short tasks.\n- Unhandled errors in workers crash the worker, not the main process.

## Related
nodejs-event-loop-lag, web-worker-offloading, nodejs-cluster-patterns
