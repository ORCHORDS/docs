# worker-cpu-limit-exceeded

**Issue:** Cloudflare Worker exceeds the 50ms (free) / 30s (paid) CPU time limit, returning a 1102 error
**Date:** 2026-08-11
**Status:** documented

## Symptom
Workers returns HTTP 1102 or the error `Worker exceeded CPU time limit`. The worker script does not produce a response; the error originates from the Cloudflare runtime.

## Root cause
Cloudflare Workers enforce a CPU time limit (wall clock time spent executing JS, excluding I/O wait). Free tier: 10ms request / 50ms total. Paid tier: 30s CPU. Heavy computations, large JSON parsing, cryptographic operations, or tight loops can exhaust this.

## Fix
1. Profile with `wrangler dev --local` and `console.time`.
2. Move heavy computation to a Durable Object (which has longer limits) or a queue consumer.
3. Use `crypto.subtle` (WebCrypto) for hash operations — it is hardware-accelerated and doesn't count against CPU in the same way as pure JS.
4. Stream large payloads instead of buffering.

## Detection
Check `wrangler tail` for `cpu_time` in the log metadata. Add `console.time('label')` / `console.timeEnd('label')` around suspect sections.

## Related
- `worker-memory-limit-exceeded.md`
- `worker-subrequest-limit.md`
- `event-loop-blocking-json-stringify.md`
