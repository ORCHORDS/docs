# workers-resource-limits

**Issue:** Workers plan limits — CPU, memory, subrequest caps
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your Pages Function returns `1101` (CPU time exceeded) or
`1102` (memory exceeded) under load. The function worked fine
for weeks, then suddenly started failing.

## Root cause
Each CF Workers plan has hard limits:
- **Free:** 10ms CPU per request, 30s wall clock
- **Bundled (default $5/mo):** 30s CPU per request, 30s wall
  clock, 50 subrequests
- **Unbound (paid):** 30s CPU per request, 30s wall clock, 1000
  subrequests

**Source:** CF Workers limits:
https://developers.cloudflare.com/workers/platform/limits/

For Pages Functions, the limits are slightly different:
- 10s (Free) / 30s (Paid) wall clock
- 30s CPU (Unbound only)

> "The CPU time limit is the amount of time your Worker spends
> in actual computation. Time spent waiting on I/O (fetch, KV,
> D1) does not count toward the CPU time limit, but does count
> toward the wall-clock limit."

## 1101 = CPU time exceeded
You have a tight CPU-bound loop. Common causes:
- Synchronous JSON parsing of a huge object (>1 MB)
- Tight loop in JavaScript (e.g. `for (let i = 0; i < 1e9; i++)`)
- Synchronous crypto (PBKDF2 with too many iterations)
- Regex backtracking

Fix:
- Stream large JSON with `request.json()` (no, wait, that's
  async — but the parse is sync internally). For huge JSON, use
  a streaming JSON parser.
- Move heavy compute to a Durable Object (separate CPU budget)
- Cap regex input size; use a regex linter

## 1102 = Memory exceeded
The Worker allocated too much memory. Common causes:
- Loading a huge file into memory (e.g. parsing a 1 GB JSON)
- Recursive data structures
- Memory leak (unclosed references)

Fix:
- Stream files instead of loading into memory
- Paginate large queries
- Use `Response.body` streams for large responses

## 1103 = Wall clock exceeded
The request took too long (network I/O + compute). Common causes:
- Slow vendor API (10s vendor call)
- N+1 queries (100 subrequests sequentially)
- Unbounded retries

Fix:
- Use a timeout for vendor calls (5-10s)
- Parallelize independent subrequests with `Promise.all`
- Add a circuit breaker (see `circuit-breaker-pattern.md`)

## 50 / 1000 subrequest cap
Each Worker can make at most 50 (Bundled) or 1000 (Unbound)
subrequests per request. Subrequests include:
- `fetch()` calls (to other services)
- `KV.get()` / `KV.put()` / `KV.list()`
- `env.DB.*` (D1 calls)
- `env.R2.*` (R2 calls)

> "A subrequest is any call to `fetch()` or to a Cloudflare
> binding (KV, D1, R2, Durable Object, etc.)."

If you hit the cap, common causes:
- Fan-out reads (querying 100 user IDs sequentially)
- Reading a paginated list (page 1 → 10 records, page 2 → 10
  records, ...50 pages)
- D1 query that's too broad (the query itself doesn't count,
  but if it returns 1000 rows and you fetch related data per
  row, that's 1000 subrequests)

Fix:
- Use `Promise.all()` to parallelize
- Batch queries (`IN (?, ?, ?, ...)` instead of N queries)
- Cache results in KV (one KV read instead of N D1 reads)
- Use a Durable Object to hold the in-memory state (no
  subrequest needed)

## Verification
- **Test:** `test/limits.test.ts > 1000-row batch query stays
  under 50 subrequests` — passes
- **Live:** CF Analytics shows p99 CPU time well under limit
- **Alerts:** PagerDuty when 1101/1102/1103 error rate >0.1%

## Gotchas
- **CF retries 1101/1102/1103 with backoff** in some cases.
  The user sees 5xx twice, then a success. That's why the
  failure mode is silent (you see retries, not failures).
- **CPU time ≠ wall clock time.** A function that does 1s of
  compute + 29s of network I/O is fine on Unbound (1s CPU,
  30s wall); fails on Bundled (1s CPU fine, 30s wall fine,
  wait actually OK). The limits interact.
- **The 1000-subrequest cap is for Unbound.** If you're on
  Bundled (50), upgrade to Unbound or batch aggressively.
- **DO-to-Worker RPC does NOT count as a subrequest.** It uses
  a different primitive (RPC). Useful for fan-out patterns.
- **The free plan has a 100k req/day cap.** 100k is plenty for
  dev; production should be on a paid plan.

## Related
- `circuit-breaker-pattern.md`
- `retry-with-jitter.md`
- `per-tenant-durable-object.md` (uses DO as a separate CPU
  budget)
- CF Workers limits: https://developers.cloudflare.com/workers/platform/limits/
