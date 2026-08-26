# event-loop-blocking-json-stringify

**Issue:** Calling `JSON.stringify` on a large object blocks the Node.js event loop, causing request timeouts
**Date:** 2026-08-11
**Status:** documented

## Symptom
Under load, incoming HTTP requests queue up or time out. APM traces show a single long synchronous span with no I/O. The CPU-bound work is serializing a large object to JSON for logging or caching.

## Root cause
`JSON.stringify` is synchronous and single-threaded. Serializing megabyte-scale objects (large arrays, deeply nested configs, full DB result sets) can take tens to hundreds of milliseconds, blocking all other work on the event loop.

## Fix
1. Stream large objects with a streaming JSON serializer (`fast-json-stringify`, `json-stream-stringify`).
2. Offload to a Worker thread:
```ts
import { Worker, isMainThread, parentPort, workerData } from 'worker_threads';
// Serialize in worker, post result back
```
3. Reduce payload size: select only needed fields before stringifying.
4. Use `response.json()` on Response objects (streams automatically in Fetch API environments).

## Detection
```
grep -rn "JSON.stringify" src/ --include="*.ts"
```
Profile with `--prof` or clinic.js; look for long synchronous ticks.

## Related
- `worker-cpu-limit-exceeded.md`
- `node-unhandled-rejection-crash.md`
