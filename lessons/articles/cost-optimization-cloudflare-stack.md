# Cost Optimization Lessons from the Cloudflare Stack

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A team migrates a monolith to Cloudflare Workers + D1 + R2 + KV. The first month's bill is
three times higher than the spreadsheet estimate. Investigation reveals that the cost model
was misunderstood at three levels: the billing unit (requests, not CPU-hours), the
interaction costs between primitives (a single user action may fan out to 10+ KV reads),
and the cost of accidentally warming egress paths that were free in the old architecture.

Cloudflare's pricing is genuinely competitive but the cost model is different from AWS/GCP
and the same optimization intuitions do not transfer directly.

## Context

The Cloudflare developer stack bills on fundamentally different dimensions than traditional
cloud:

| Primitive | Primary billing dimension |
|-----------|--------------------------|
| Workers | Requests + CPU time (Workers Unbound/Standard) |
| KV | Read operations + Write operations + Storage GB |
| R2 | Operations (Class A/B) + Storage GB (no egress fee) |
| D1 | Rows read + Rows written + Storage GB |
| Durable Objects | Requests + Duration (GB-seconds) + Storage reads/writes |
| Queues | Messages delivered + Bytes |
| Analytics Engine | Data points written (reads are free) |

The absence of egress fees for R2 and Workers is not a trick — it is structural, Cloudflare
does not charge for traffic leaving its network to the internet. This fundamentally changes
the optimization strategy versus AWS S3 + Lambda, where egress is often the largest line
item.

## Lesson 1 — KV is Not a Free Cache

KV reads are cheap individually (fractions of a cent per million reads on the paid plan)
but compound quickly when every request triggers multiple KV reads. Common patterns that
silently inflate KV bills:

**Anti-pattern: Per-request config reads.** A Worker reads 5 feature flags from KV on
every request. At 10 million daily requests, that is 50 million KV reads per day. Batch
config into a single KV key and read it once, deserializing in the Worker.

**Anti-pattern: KV as a session store without TTL.** Stale session keys accumulate in KV
storage. A 1 KB session object left with no TTL costs nothing in reads if unused but
accumulates storage costs. Set explicit TTLs on all KV entries that are not permanent
configuration. Audit KV key counts monthly with the `kv:key list` command (paginated).

**Better pattern:** Cache frequently-read KV values in the Worker's in-memory cache for the
duration of a request using a module-scoped `Map`. Workers isolates are reused across
requests on the same PoP (within the same isolate lifetime), so a module-level cache can
survive for hundreds of requests before the isolate is recycled. Read KV once per isolate
lifecycle using a `lastFetched` timestamp guard, not once per request.

```typescript
// module-level cache
let configCache: Config | null = null;
let configFetchedAt = 0;
const CONFIG_TTL_MS = 30_000;

async function getConfig(env: Env): Promise<Config> {
  const now = Date.now();
  if (configCache && now - configFetchedAt < CONFIG_TTL_MS) return configCache;
  configCache = JSON.parse(await env.CONFIG.get('app-config') ?? '{}');
  configFetchedAt = now;
  return configCache!;
}
```

## Lesson 2 — D1 Row Reads Are the Hidden Cost Driver

D1 bills on rows read, not query count. A query with `SELECT *` that returns 1,000 rows
costs 1,000 row reads even if the client uses only 5 fields. Optimization strategies:

**SELECT only the columns you need.** Replace `SELECT *` with an explicit column list in
every production query. This is also good hygiene for schema evolution.

**Add indexes before load, not after.** A table scan on an unindexed column reads every
row in the table. On a 100,000-row table, a missing index on a `WHERE` clause turns a
10-row-read query into a 100,000-row-read query. Run `EXPLAIN QUERY PLAN` against all
production queries and verify no `SCAN TABLE` without a preceding `SEARCH TABLE USING INDEX`.

**Paginate aggressively.** Never expose an endpoint that returns unbounded result sets from
D1. All list endpoints must have a `LIMIT` clause, and the default limit should be 25-50
rows. Server-side cursors using the `rowid` or a created_at timestamp are more efficient
than `OFFSET` pagination (which still reads all skipped rows).

**Cache D1 query results in KV for read-heavy, write-light data.** The cost of a KV read
(fractions of a cent per million) is much lower than a D1 query that scans thousands of
rows. For data that changes at most hourly (product catalog, pricing, config), compute
the result once, store it in KV, and invalidate on write.

## Lesson 3 — Durable Objects Duration Billing Requires Active Management

Durable Objects charge for wall-clock duration (GB-seconds) while the DO is active. A DO
stays "active" (and billing) as long as there is an open WebSocket connection, an in-flight
request, or it has not yet reached its idle timeout (~10 seconds by default).

**Patterns that silently run up DO duration costs:**

- Long-running WebSocket connections that keep the DO alive between messages
- Alarm loops that fire every second instead of every minute
- DO storage reads that are slower than expected under heavy D1 contention, keeping the DO
  active longer per request

**Mitigation:** Set an explicit `setTimeout` inside the DO's fetch handler to force a
response within a bounded time. Never use a DO as a polling loop with sub-second alarms
unless the traffic volume justifies the cost. Use DO alarms for work that runs no more
than once per minute per DO instance.

## Lesson 4 — R2 Class A vs Class B Operations

R2 differentiates between:
- **Class A operations** (write-like): PUT, POST, COPY, multipart upload — more expensive
- **Class B operations** (read-like): GET, HEAD — cheaper

Common mistakes:
- Using `PUT` for upserts when the object already exists. A read-modify-write cycle costs
  one Class B + one Class A. If you only need to write and do not need to read-before-write,
  use PUT directly.
- Issuing HEAD requests to check object existence before every write. On high-throughput
  ingestion pipelines this doubles Class A costs. Design the pipeline to be idempotent
  (PUT is idempotent in R2) and skip the pre-check.
- Multipart uploads for objects under 10 MB. Multipart uploads cost additional Class A
  operations per part. Use single-PUT for objects under 100 MB unless memory constraints
  require streaming.

R2 has no egress fee, so serving assets directly from R2 via a Worker is cheaper than S3 +
CloudFront for high-traffic use cases. The break-even point is typically at ~1 TB/month of
egress where the egress fee savings exceed any operation-count difference.

## Lesson 5 — Workers CPU Time on Standard vs Unbound

Workers Standard (the default plan) includes CPU time up to 10ms per request in the base
price and then charges for overages. Workers Unbound charges by CPU millisecond consumed,
with no per-request overhead cost. The choice matters:

- **Request-heavy, compute-light** workloads (API routing, auth checks, redirect logic):
  Standard is cheaper. CPU per request is low, so the per-request cost is the ceiling.
- **Compute-heavy, request-moderate** workloads (image transformation, PDF generation,
  cryptographic operations): Unbound is cheaper. Pay for actual CPU without per-request
  markup.

Profile CPU time using `ctx.waitUntil(Promise.resolve())` with a timing wrapper around
expensive operations, then export to Analytics Engine. Do this before choosing a billing
plan, not after the first bill arrives.

## Anti-patterns

**Over-relying on KV for write-heavy workloads.** KV write costs are roughly 10x KV read
costs. Workflows that write to KV on every request (hit counters, last-seen timestamps) are
better served by Workers Analytics Engine (cheap writes, free reads) or D1 batched inserts.

**Using Queues as a retry buffer for D1 writes without batching.** A failed D1 write that
re-queues itself and is retried individually costs one message delivered per retry. Batch
the failed writes into a single insert and retry once, not per-row.

**Not using `ctx.waitUntil` for non-critical writes.** Keeping a response waiting while
the Worker writes a log to D1 or KV adds latency and keeps the CPU billing clock running.
Move non-critical writes to `ctx.waitUntil` so the response is returned first.

**Ignoring the free tier during development and then being surprised at production scale.**
The Workers free tier (100k requests/day) covers many development patterns but the free
KV limits (100k reads/day) are easily exceeded by a single integration test suite that
reads config on every test case.

## Gotchas

- **KV `list()` is more expensive than KV `get()`**. A `list()` call counts as a single
  read operation but scans the key namespace. Avoid using `list()` in hot paths.

- **Analytics Engine write costs add up on high-frequency events.** Tracking every
  individual item view in a high-traffic catalog at 1 data point per view can become a
  significant line item. Sample high-frequency events (1-in-10 or 1-in-100) if absolute
  accuracy is not required.

- **D1 billing counts rows read by the SQLite engine, including rows read during index
  lookups.** A query that uses a composite index may still read more rows than you expect
  if the index is not covering (i.e., the engine must look up the main table for non-indexed
  columns). Use covering indexes for the most cost-critical queries.

- **Cloudflare bills are lag-reported.** The bill for a given UTC day appears in the
  dashboard 24-48 hours later. Cost spikes from a misconfigured deploy may not be visible
  until two days after the incident.

## Verification

Monthly cost hygiene checklist:

- [ ] KV key count audited; stale keys with no TTL identified and pruned
- [ ] D1 `EXPLAIN QUERY PLAN` run on top-10 query patterns; no table scans
- [ ] Workers CPU time p99 measured and billing plan verified as correct
- [ ] R2 operation breakdown (Class A vs B) reviewed in the dashboard
- [ ] Durable Object alarm frequencies reviewed; none firing faster than once per minute
- [ ] Analytics Engine data point volume reviewed; sampling rate adjusted if needed
- [ ] Cost anomaly alert configured on Cloudflare billing (threshold: 20% above 30-day avg)

## Related

- `cloudflare-storage-primitive-selection.md`
- `developer-experience-dx-cloudflare-workers.md`
- `ai-cost-finops-2026.md`
- `n-plus-one-queries-compound-at-scale.md`
- `feature-flag-lifecycle-management.md`
- `cache-invalidation-is-harder-than-caching.md`

## Sources

- Cloudflare Workers pricing documentation (2025)
- Cloudflare KV pricing documentation
- Cloudflare D1 pricing documentation (rows read billing model)
- Cloudflare R2 pricing documentation (Class A/B operations)
- Cloudflare Durable Objects billing documentation (duration GB-seconds)
- Cloudflare Analytics Engine documentation
