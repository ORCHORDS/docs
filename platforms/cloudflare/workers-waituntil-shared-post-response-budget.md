# Workers waitUntil Shared Post-Response Budget

**Issue:** Splitting background work across several `ctx.waitUntil()` calls does not create several execution windows. All tasks share one post-invocation deadline and can be cancelled together when it expires.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls
- Reserve `ctx.waitUntil()` for non-response-critical work that can safely finish after the response. Await anything needed for response correctness.
- For HTTP Workers, budget all registered work against the shared limit of up to 30 seconds after the response is sent or the client disconnects.
- Make tasks idempotent and independently observable. Rejection of one registered promise does not stop the others, similar to `Promise.allSettled`.
- Move work needing durable delivery, retries, or a longer window to Cloudflare Queues. Use Tail Workers for logs and exception export.
- Do not add `waitUntil()` merely to keep a streamed response alive while the client is still receiving it.
- Track cancellation warnings in Workers Logs or Tail Workers and alert on repeated deadline exhaustion.

## Verification
- Deploy a probe with several registered tasks whose combined wall time crosses the post-response deadline and confirm unfinished work is cancelled and logged.
- Force one task to reject and confirm independent tasks still settle.
- Kill the client connection and verify response-critical data was already committed while optional work remains retry-safe.

## Gotchas
`waitUntil()` is a lifetime extension, not a durable job system, and it does not waive CPU, subrequest, memory, or other Worker limits.

## Official sources
- https://developers.cloudflare.com/workers/runtime-apis/context/
