# cloudflare-workers-performance

**Issue:** Cloudflare Workers add latency instead of reducing it
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Workers run at Cloudflare's edge PoPs (300+ locations). When configured correctly, they reduce TTFB by serving from the nearest edge. Misconfiguration causes subrequest chaining that adds latency.

## Pattern / Solution
1. Minimize subrequests: each fetch() in a Worker adds a round trip.\n2. Use KV for configuration and semi-static data; it is globally replicated.\n3. Use Cache API to store responses at the edge.\n4. Use streaming responses for large payloads.\n5. Profile with wrangler tail and Cloudflare Workers Analytics.

## Gotchas
- CPU time limit: 10ms on free plan, 30ms on paid, 50ms with Workers Unbound.\n- Subrequests to your origin still traverse the internet; the Worker saves only the client-to-edge leg.\n- Cold starts are rare on Cloudflare (V8 isolates start in < 1ms) but do occur for low-traffic Workers.

## Related
workers-cpu-profiling, workers-cold-start-optimization, kv-read-performance, d1-query-optimization
