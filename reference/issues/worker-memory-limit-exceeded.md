# worker-memory-limit-exceeded

**Issue:** Cloudflare Worker exceeds the 128MB memory limit, causing a 1101 error or silent worker restart
**Date:** 2026-08-11
**Status:** documented

## Symptom
Worker returns HTTP 1101 ("Worker threw an exception") or intermittently fails under load. `wrangler tail` shows `exceeded memory limit`.

## Root cause
Workers are limited to 128MB of memory per isolate. Accumulating large buffers (image processing, full response bodies in memory, large KV value reads), global state that grows per request, or memory leaks across requests in long-lived isolates can hit this limit.

## Fix
1. Stream data instead of buffering: use `TransformStream` / `ReadableStream` pipelines.
2. Avoid storing request-specific data in module-level variables (isolate global scope is shared across requests in the same isolate lifetime).
3. For image or binary processing, use Cloudflare Images or R2 with pre-signed URLs.
4. Read KV values in streaming mode when possible.

## Detection
`wrangler tail --format=pretty` — look for `exceeded memory limit` in error messages. Add `performance.memory` polling if available (limited in Workers).

## Related
- `worker-cpu-limit-exceeded.md`
- `worker-subrequest-limit.md`
