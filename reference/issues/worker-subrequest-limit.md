# worker-subrequest-limit

**Issue:** A Cloudflare Worker that makes more than 50 subrequests (fetch calls) per invocation hits the subrequest limit and subsequent fetches fail
**Date:** 2026-08-11
**Status:** documented

## Symptom
After 50 `fetch()` calls within a single Worker request, additional calls throw `TypeError: Too many subrequests`. The limit is 50 for free plans; paid plans allow up to 1000 subrequests but the default cap is still 50 unless configured.

## Root cause
Cloudflare enforces a subrequest limit per Worker invocation to prevent abuse. Each `fetch()`, `caches.open().match()`, `kv.get()` that goes over the network counts as a subrequest.

## Fix
1. Batch API calls — use GraphQL or batch endpoints instead of N individual fetches.
2. Cache aggressively with the Cache API or KV to avoid repeated fetches.
3. Move fan-out logic to a Queue consumer or Durable Object that can make requests spread across multiple invocations.
4. Use `Promise.all` for parallel fetches to stay under limits while reducing latency.

## Detection
Add a subrequest counter in development:
```ts
let subrequestCount = 0;
const originalFetch = globalThis.fetch;
globalThis.fetch = (...args) => { subrequestCount++; return originalFetch(...args); };
```

## Related
- `worker-cpu-limit-exceeded.md`
- `worker-memory-limit-exceeded.md`
