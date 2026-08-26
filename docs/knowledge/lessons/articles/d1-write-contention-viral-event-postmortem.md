# Postmortem: D1 Write Contention During Viral Event Caused 10-Minute Outage

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production
- **Severity:** P1 — customer-facing writes fully blocked for 10 minutes

---

## Symptom

At 14:23 UTC a music collaboration feature was shared by a creator with 2.1 million followers. Within 90 seconds, inbound write traffic to the platform's primary D1 database increased 47x above the previous peak. The Worker returned HTTP 503 for all mutation endpoints. Read-only pages remained available. The outage lasted 10 minutes and 18 seconds before mitigation took effect.

---

## Context

D1 is Cloudflare's globally distributed SQLite-as-a-service. Each D1 database has a single authoritative primary that serialises writes; reads are served from regional read replicas. The platform used one D1 database per user workspace and one shared "catalogue" database for public discovery data. During the viral event, thousands of concurrent Workers attempted to write engagement events (plays, likes, project forks) to the shared catalogue D1 database simultaneously. SQLite's write serialisation model became a hard bottleneck at this scale.

The on-call engineer received a PagerDuty alert at 14:24 UTC — 60 seconds after impact began — because the synthetic canary checks a write-path endpoint every 60 seconds.

---

## Timeline

| UTC | Event |
|-----|-------|
| 14:22:51 | Creator posts share link on social platform |
| 14:23:18 | Inbound request rate climbs past 2,000 RPS (baseline: 43 RPS) |
| 14:23:41 | First `SQLITE_BUSY` errors logged in Workers observability |
| 14:24:00 | Canary write check fails; PagerDuty fires |
| 14:24:35 | On-call acknowledges; begins investigation |
| 14:26:10 | Hypothesis: catalogue D1 is saturated |
| 14:28:00 | Decision: disable non-critical engagement writes, redirect to KV queue |
| 14:29:45 | Deployment of feature-flagged write bypass begins rolling out |
| 14:33:36 | 503 rate drops below 1%; outage declared over |
| 14:35:00 | Full traffic normalises |

---

## Root Cause Analysis

### Primary: D1 Write Serialisation Under Burst

SQLite (and by extension D1) permits only one writer at a time. Under the viral spike, hundreds of Workers attempted concurrent `INSERT` statements against the catalogue database within the same wall-clock second. D1's internal queue of pending write requests exhausted, and the service returned `SQLITE_BUSY` / HTTP 503 to callers that exceeded the wait timeout. The platform had no circuit breaker or write-path backpressure mechanism.

### Contributing: Engagement Events Written Synchronously

The platform wrote engagement data (plays, likes, forks) inline with the HTTP response cycle. The Worker awaited `db.prepare(...).run()` before returning a response. This tied Worker CPU slots to database write latency under contention, amplifying the problem: Workers piled up waiting for the database rather than failing fast and freeing the slot.

### Contributing: Single Shared Catalogue Database

All public content lived in a single D1 database. There was no sharding strategy. During normal traffic this was acceptable; at viral scale it became a single point of failure for all write operations.

### Contributing: Canary Polling Interval Too Coarse

A 60-second synthetic check interval meant the outage was already 60 seconds old before any alert fired. MTTD was structurally limited by the polling cadence.

---

## Technical Sections

### 1. D1 Write Throughput Limits and SQLite Serialisation

D1 is not a distributed write-scalable database. Its consistency model is "single writer, multiple reader": all writes go to one primary node and are then replicated. The practical write throughput ceiling is several hundred writes per second for small transactions on a lightly contended database; it drops sharply when many concurrent workers attempt writes simultaneously because each must acquire an exclusive lock.

Teams that need high write throughput on D1 must either:
- Reduce write concurrency (queue writes, batch, rate-limit)
- Reduce write frequency (aggregate in memory or KV first, flush periodically)
- Shard data across multiple D1 databases by a stable partition key

### 2. The Correct Pattern: Write-Behind Queue via Cloudflare Queues

The mitigation applied during the incident — bypassing direct D1 writes and routing to a KV-backed queue — is the canonical pattern for high-burst engagement data on D1.

The corrected architecture:
1. Worker receives engagement event, does zero-latency enqueue to Cloudflare Queues (`env.ENGAGEMENT_QUEUE.send(event)`)
2. Worker returns 202 immediately; no D1 write in the critical path
3. A Queue consumer Worker runs in the background, batching up to 100 events and writing them to D1 in a single transaction

This decouples the inbound burst from the D1 write rate, absorbs traffic spikes naturally, and allows the consumer to self-throttle by controlling its own concurrency.

```ts
// Before (synchronous, contention-prone)
await env.DB.prepare(
  'INSERT INTO plays (project_id, user_id, ts) VALUES (?, ?, ?)'
).bind(projectId, userId, Date.now()).run();

// After (enqueue; consumer writes in batch)
await env.ENGAGEMENT_QUEUE.send({ projectId, userId, ts: Date.now() });
```

### 3. D1 Sharding Strategy

When a single D1 database is not sufficient, the next step is to shard. Effective shard keys for catalogue data include:

- **By content type** — one D1 per entity type (projects, artists, samples). Avoids cross-type contention but requires cross-database joins to be handled in application code.
- **By creator ID modulo N** — each creator's public content lives in `catalogue_${creatorId % SHARD_COUNT}`. Queries that must span all shards require fan-out, so keep shard count small (4–16).
- **By time bucket** — recent engagement in a "hot" D1, archived data in "cold" D1s. Fits time-series engagement data naturally.

Sharding adds complexity. Prefer write-behind queues first; shard only if queue throughput is also insufficient.

### 4. Circuit Breaker for D1 Writes

Any Worker that writes to D1 should implement a circuit breaker:

```ts
async function writeWithCircuitBreaker(db, stmt) {
  const start = Date.now();
  try {
    const result = await db.prepare(stmt.sql).bind(...stmt.params).run();
    return result;
  } catch (err) {
    if (err.message.includes('SQLITE_BUSY') || err.message.includes('503')) {
      // open circuit: fail fast for next N requests
      await env.CIRCUIT_KV.put('db_circuit_open', '1', { expirationTtl: 30 });
      throw new DatabaseContendedError('D1 write circuit open', { cause: err });
    }
    throw err;
  }
}
```

The circuit state can live in KV (cheap, fast reads, eventual consistency across Workers is acceptable for a circuit signal). Workers should check the circuit flag at the top of the mutation handler and return 429 immediately if the circuit is open, rather than piling up waiting for D1.

### 5. Observability: Detecting Write Contention Early

The incident would have been detected 45 seconds earlier with real-time D1 error rate monitoring rather than synthetic canary polling. Recommended instrumentation:

- Emit a `d1_write_error` span event on every `SQLITE_BUSY` or HTTP 503 response from D1
- Alert when the 1-minute rolling error rate exceeds 5% of D1 write attempts
- Dashboard: D1 writes/sec, error rate, P95 write latency — correlated with Worker request rate

Cloudflare's Workers Analytics Engine is the appropriate sink; it supports high-cardinality time-series and is queryable via the GraphQL Analytics API.

### 6. Canary Interval Reduction

A 60-second synthetic canary check is too coarse for a P1 write-path outage. The platform migrated to a 15-second canary interval for critical write endpoints after this incident, reducing maximum structural MTTD from 60 seconds to 15 seconds.

---

## Anti-Patterns

- **Synchronous engagement writes in the hot path.** Writes that are not strictly required before the response is returned should never be awaited inline.
- **Single D1 database for all public catalogue data.** A shared global write target is a single point of failure for bursty write traffic.
- **No circuit breaker on D1 writes.** Without a circuit breaker, every Worker slots up waiting for a saturated database instead of failing fast and freeing resources.
- **Canary-only alerting for write paths.** Synthetic polling is a lagging indicator. Real-time error-rate alerts are required alongside canaries.
- **Ignoring `SQLITE_BUSY` in error logs.** A handful of busy errors per minute is a warning sign of approaching saturation; teams often dismiss these as transient noise.

---

## Gotchas

- D1 read replicas do NOT help write throughput. Reads scale horizontally; writes do not. This surprises teams migrating from traditional distributed databases.
- Cloudflare Queues delivery is "at least once". The write-behind consumer must be idempotent (use `ON CONFLICT DO NOTHING` or a deduplication key in D1).
- D1 `batch()` does not bypass the write lock; it is still a single transaction. Batching reduces round-trips but does not increase parallelism.
- The D1 `--local` flag in Wrangler uses an in-process SQLite file, which has no concurrency limit. Local testing cannot reproduce production write contention.
- KV used as a queue substitute has no delivery guarantees. Use Cloudflare Queues for durable, ordered, at-least-once delivery.

---

## Verification

Post-remediation verification steps executed on 2026-08-23:

1. Load test: `wrk -t 50 -c 500 -d 30s` against the engagement endpoint. Error rate: 0.02% (baseline noise). Previously: 94% under same load.
2. Consumer lag monitoring: Queue depth remained below 1,000 messages throughout the load test; consumer caught up within 8 seconds of burst.
3. Circuit breaker test: Manually opened the circuit flag in KV; confirmed all Workers returned 429 within one KV read TTL (approximately 60ms).
4. Canary: 15-second interval canary confirmed operational on staging and production.

---

## Action Items

| Item | Owner | Due |
|------|-------|-----|
| Migrate all engagement writes to Cloudflare Queues | Platform team | 2026-09-05 |
| Implement D1 write circuit breaker in shared Worker lib | Platform team | 2026-09-01 |
| Add D1 write error-rate alert (threshold: 5% over 1 min) | Observability | 2026-08-29 |
| Reduce all write-path canary intervals to 15 seconds | Observability | 2026-08-28 |
| Document D1 sharding strategy in architecture runbook | Platform team | 2026-09-12 |

---

## Related

- `queue-consumers-must-be-idempotent.md`
- `retry-storm-queue-poison-message.md`
- `cloudflare-storage-primitive-selection.md`
- `circuit-breaker-prevents-cascade-failure.md`
- `capacity-forecast-error-review-loop.md`

---

## Sources

- Cloudflare D1 documentation — limits and guidance: https://developers.cloudflare.com/d1/
- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- SQLite WAL mode and concurrency: https://www.sqlite.org/wal.html
- Workers Analytics Engine: https://developers.cloudflare.com/analytics/analytics-engine/
