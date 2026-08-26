# workers-cpu-profiling

**Issue:** Cloudflare Worker exceeds CPU time limits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers have strict CPU time limits. Exceeding them causes the Worker to terminate with a 1101 error. CPU-intensive operations are the most common causes.

## Pattern / Solution
1. Use wrangler dev --local to profile locally with Chrome DevTools attached.\n2. Use performance.now() timing API to measure code sections.\n3. Offload heavy computation: use Durable Objects for stateful work, D1 for data queries.\n4. Prefer native Worker APIs (crypto.subtle, TextEncoder) over pure-JS implementations.\n5. Cache computed results in KV to avoid recomputation.

## Gotchas
- I/O time (fetch, KV read) does not count toward CPU time limit.\n- crypto.subtle operations are native and fast; pure-JS crypto is not.\n- Wrangler local emulation may not accurately reflect production CPU limits.

## Related
cloudflare-workers-performance, workers-cold-start-optimization, kv-read-performance
