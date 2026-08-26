# cloudflare-workers-limits-resource-planning

**Issue:** Capacity planning for Cloudflare Workers under example project
         traffic volumes — CPU time, memory, subrequest budgets,
         KV ops/sec, and D1 query throughput
**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

Workers return 1101 (Worker exceeded CPU time limit) or 1015
(Worker rate limited) errors under peak traffic. KV reads start
returning 429s. D1 queries time out. The free/bundled plan cannot
absorb the load but there is no clear checklist for knowing when
to upgrade and what the ceiling of each plan actually is.

## Context

example project (Web App / Server / Platform) traffic arrives in bursts
— marketing campaign spikes, batch cron jobs firing at the same
wall-clock time, and mobile push-driven API calls all coincide.
Each Worker invocation runs inside an isolate; limits are applied
per-isolate, not globally per account on the free tier. On the
paid (unbound) plan limits expand substantially, and Cloudflare
imposes a separate per-account request rate that scales with the
subscription tier.

---

## Plan Comparison Table

| Limit                  | Free / Bundled         | Workers Paid (Unbound) |
|------------------------|------------------------|------------------------|
| CPU time per request   | 10 ms                  | 30 s (soft); 5 min+    |
| Wall-clock time        | 30 s                   | no hard cap            |
| Memory per isolate     | 128 MB                 | 128 MB (same)          |
| Subrequests (fetch)    | 50 per invocation      | 1 000 per invocation   |
| Workers KV reads/day   | 100 000 (free)         | unlimited (metered)    |
| Workers KV writes/day  | 1 000 (free)           | unlimited (metered)    |
| D1 rows read/day       | 5 M (free)             | 25 B (metered)         |
| D1 rows written/day    | 100 K (free)           | 50 M (metered)         |
| R2 Class A ops/month   | 1 M (free)             | metered past 10 M      |
| R2 Class B ops/month   | 10 M (free)            | metered past 100 M     |
| Cron triggers          | 5 crons                | unlimited              |
| Script size (bundle)   | 1 MB compressed        | 10 MB compressed       |
| Concurrent connections | 6 open fetch()         | 6 (same)               |

All numbers from the Cloudflare developer docs as of 2026-08.
Check https://developers.cloudflare.com/workers/platform/limits/
for the latest values before planning.

---

## CPU Time: What Counts

CPU time is measured as pure JavaScript execution time inside the
isolate. It excludes time spent waiting on:
- Fetch subrequests (network I/O)
- KV, D1, R2, Durable Object reads (binding I/O)
- `waitUntil()` callbacks (run after response is sent)

This means a Worker that awaits 20 KV reads in series may take
2 000 ms wall-clock but only consume 8 ms of CPU time. Profile
with `wrangler dev --cpu-profiling` to isolate hot paths.

```ts
// Anti-pattern: serial KV reads inflate wall-clock
const a = await env.KV.get("key:a");
const b = await env.KV.get("key:b");

// Pattern: parallel KV reads — same CPU, half the wall-clock
const [a, b] = await Promise.all([
  env.KV.get("key:a"),
  env.KV.get("key:b"),
]);
```

---

## KV Ops/Sec — The Hidden Ceiling

KV has a per-key write rate limit of 1 write/second regardless
of plan. High-write use cases (counters, session state) hit this
invisibly. The 429 is silently retried by the runtime for a short
window; after that the write is dropped with no error surface.

```
Observed behaviour on burst write workloads:
  Key "session:active_count" written at 50 req/s
  → ~49 writes/s are silently lost
  → Metric drifts without any error in logs
```

Mitigation strategies:

| Pattern                    | How it Helps                         |
|----------------------------|--------------------------------------|
| Durable Objects counter    | Serialised writes, no loss           |
| KV + DO hybrid             | DO for hot key, KV for cold reads    |
| Analytics Engine           | High-throughput append-only metrics  |
| Workers Queues + batch DO  | Decouple write bursts from source    |

---

## D1 Throughput Planning

D1 runs on SQLite with global read replicas. Writes always go to
the primary (us-east or eu-west, depending on bucket location).
Read replicas propagate within ~50 ms of a commit.

```
Per-database limits (paid tier):
  Max database size:   10 GB
  Max rows per query:  100 000
  Max query duration:  30 s
  Concurrent writes:   1 (SQLite serialises)
  Read replica regions: all CF regions automatically
```

Capacity table for example project request volumes:

| Requests/day | D1 reads needed | D1 writes needed | Risk Level |
|--------------|-----------------|------------------|------------|
| <50 K        | <500 K          | <50 K            | Free tier  |
| 50 K–1 M     | 500 K–10 M      | 50 K–1 M         | Paid tier  |
| 1 M–10 M     | 10 M–100 M      | 1 M–10 M         | Paid + DO  |
| >10 M        | >100 M          | >10 M            | Hyperdrive |

For write-heavy workloads above 1 M/day, consider:
1. Batch inserts via Workers Queues consumers
2. Durable Object write coalescing before D1 flush
3. Hyperdrive (external Postgres) for full relational write scale

---

## Upgrade Path: Bundled → Unbound

```
Step 1: Audit current usage
  wrangler tail --format json | jq '.cpuTime'
  Dashboard → Workers Analytics → CPU Time P95

Step 2: Enable the paid plan
  Dashboard → Account Home → Plans → Workers Paid ($5/mo base)

Step 3: Opt each Worker into Unbound mode
  # wrangler.toml
  [usage_model]
  # Remove this line OR set explicitly:
  usage_model = "standard"   # bundled behaviour (default)
  # Switch to:
  usage_model = "unbound"    # billed per CPU-ms

Step 4: Set CPU limits defensively
  # Prevent runaway Workers inflating the bill
  [limits]
  cpu_ms = 10_000  # 10 s soft ceiling per invocation
```

Unbound billing is $0.02 per 1 M CPU-ms beyond the included
10 M CPU-ms/mo. A Worker running 30 ms of CPU per request at
1 M requests/day costs ≈ $18/day in excess CPU alone. Plan
capacity headroom before enabling for high-traffic Workers.

---

## Subrequest Budget Planning

```
Budget allocation per invocation type:

| Invocation type       | Typical subreqs | Budget left |
|-----------------------|-----------------|-------------|
| SSR HTML page         | 3–5             | 995 (paid)  |
| API aggregation route | 8–15            | 985 (paid)  |
| Webhook fan-out       | 10–50           | 950 (paid)  |
| Image transform cron  | 100–300         | 700 (paid)  |
| Full crawl Worker     | 500–900         | 100 (paid)  |
```

On the free/bundled plan the 50-subrequest limit is hit by
webhook fan-out Workers almost immediately. These must be on
the paid plan or restructured to use Queues for fan-out.

---

## Anti-patterns

- **Relying on free tier KV for production write workloads.** The
  1 write/s per-key limit is a hard physical constraint, not just
  a plan limit. Upgrade alone does not fix it.
- **Measuring wall-clock as a proxy for CPU.** A 2 000 ms
  wall-clock response can be under 10 ms of CPU; profile before
  upgrading.
- **Forgetting `waitUntil()` time counts against wall-clock, not
  CPU.** Long background tasks after the response are safe on CPU
  but can still be killed if the runtime reclaims the isolate.
- **Enabling unbound on all Workers simultaneously.** Only high-
  CPU Workers benefit; low-CPU Workers pay more per invocation
  on unbound.

## Gotchas

- Memory limit is 128 MB on both plans. Importing large WASM
  modules or holding large in-memory caches counts against this.
  There is no upgrade path for memory — redesign if hitting it.
- The 6-concurrent-fetch limit is per-isolate, not per-account.
  Parallel Promise.all() with more than 6 fetch() calls will
  queue internally. Batch sizes should stay ≤ 6 in the hot path.
- D1 row limits are on the number of rows scanned, not returned.
  A `SELECT *` on a table with 500 K rows with no index scans all
  500 K rows even if LIMIT 1 is applied.
- Cron triggers count CPU time against the Worker's account
  budget even though there is no user waiting. Long crons should
  use `waitUntil()` and keep each invocation under 30 s CPU.

## Verification

- **CPU check:** `wrangler tail --format json | jq '.cpuTime'`
  → P95 should be < 80 % of plan ceiling
- **KV check:** Dashboard → KV → Analytics → Operations/s
  → No write key exceeding 0.9/s sustained
- **D1 check:** Dashboard → D1 → your-db → Analytics
  → rows read/day trending vs plan threshold
- **Live:** `curl -w "%{time_total}" https://api.example.com/`
  → wall-clock < 2 s for API routes

## Related

- `cloudflare/d1-best-practices.md`
- `cloudflare/kv-best-practices.md`
- `cloudflare/workers-best-practices.md`
- `cloudflare/durable-objects-best-practices.md`
- `infra/capacity-planning-forecasting.md`

## Source URLs

- https://developers.cloudflare.com/workers/platform/limits/
- https://developers.cloudflare.com/kv/platform/limits/
- https://developers.cloudflare.com/d1/platform/limits/
- https://developers.cloudflare.com/workers/reference/pricing/
