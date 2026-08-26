# Vectorize Index Query Latency Spike After Bulk Upsert Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Incident Summary

On 2026-07-14 at 03:20 UTC a scheduled nightly job upserted 480 000 vectors into a
Vectorize index. Query latency for the semantic-search endpoint climbed from a baseline
of ~45 ms to 1 400 ms within twelve minutes of the job completing. The degraded state
persisted for 38 minutes before an index rebuild was triggered manually. No data was
lost, but the semantic-search feature was effectively unusable during peak morning
traffic in APAC regions.

---

## Context

- Vectorize index: `tracks-semantic-v2`, 1536-dimensional (OpenAI text-embedding-3-large)
- Total vectors before incident: ~3.2 million
- Vectors upserted in the job: 480 000 (15% of the existing corpus)
- Query traffic at incident peak: ~900 rps
- Workers AI binding served the embeddings used for query-time similarity search
- Index configuration: `distance_metric: cosine`, no explicit `dimensions` hint

---

## Timeline

**03:18 UTC** — Nightly `vectorize-sync` cron Worker starts. Job reads delta records
from D1 and calls `env.VECTORIZE.upsert()` in batches of 1 000 vectors.

**03:20 UTC** — All 480 batches acknowledged with HTTP 200. Job marks itself complete
in D1 and exits.

**03:22 UTC** — P95 query latency alert fires: 650 ms (threshold 250 ms).

**03:26 UTC** — On-call engineer pages in. Confirms queries returning correct results
but slowly. Suspects upstream Workers AI model load; checks rate-limit headers — all
clear.

**03:31 UTC** — Engineer attempts to correlate with deployment history; no recent
deploys. Notifies Cloudflare support via Priority ticket.

**03:44 UTC** — Cloudflare support identifies index compaction backpressure. Recommends
calling `env.VECTORIZE.rebuild()` to force an immediate index merge.

**03:58 UTC** — `rebuild()` completes. P95 latency returns to 48 ms within 90 seconds.

---

## Root Cause

Vectorize uses an LSM-like (Log-Structured Merge) segment strategy internally. Small
segments accumulate on write and are lazily merged during low-traffic periods. Inserting
480 000 vectors in a single burst created ~480 micro-segments. The ANN (Approximate
Nearest Neighbour) query planner has to merge candidate sets across all live segments
at query time. With hundreds of un-merged segments the query fan-out cost grew
super-linearly, causing the observed latency spike.

The index had not been rebuilt since the initial bulk load six weeks earlier. The
background compaction schedule, which normally keeps segment count low, had not yet
converged after the overnight job because the index was still in the middle of a
compaction cycle when the upsert flood arrived.

---

## Aggravating Factors

**No pre-job rebuild:** The nightly job did not call `rebuild()` after completing its
upsert, nor was there a post-job health check that measured segment count or query
latency.

**Batch-per-request acknowledgement gives a false "done" signal:** `upsert()` returning
200 means the data is durably accepted, not that the index is query-optimal. The
runbook treated 200 responses as "index ready."

**Monitoring gap:** The semantic-search latency alert threshold (250 ms) was set for
steady-state traffic. There was no alert on the rate of latency increase, meaning the
first page came 2 minutes into a degraded state that was already worsening.

---

## Fix

1. Added a `rebuild()` call at the end of the nightly `vectorize-sync` Worker with a
   60-second wait-and-poll loop checking `describeIndex().vectorsCount` stabilisation.
2. Added a post-upsert smoke-test query against 5 known vectors; measured latency
   logged to Analytics Engine. If P95 of smoke queries exceeds 200 ms the Worker
   self-reports an error to the on-call alerting channel.
3. Reduced upsert batch job frequency: instead of one bulk nightly run, switched to
   four 6-hourly incremental runs of ~120 000 vectors each. Smaller delta → fewer
   micro-segments per compaction cycle.

---

## Prevention

### Schedule rebuilds around large upserts

```ts
await env.VECTORIZE.upsert(vectors);
// Allow Cloudflare to acknowledge the writes, then rebuild.
await env.VECTORIZE.rebuild();
```

`rebuild()` is an async compaction operation. It does not block queries; queries remain
available throughout, just at pre-compaction speed. Fire it immediately after large
batches finish.

### Smoke-test query latency before declaring success

```ts
const testQuery = await env.VECTORIZE.query(knownEmbedding, { topK: 5 });
if (testQuery.latencyMs > LATENCY_BUDGET_MS) {
  throw new Error(`Post-upsert smoke test latency too high: ${testQuery.latencyMs}ms`);
}
```

Note: `latencyMs` is not currently a first-class field on the Vectorize response
object; measure it with `performance.now()` wrappers in the Worker.

### Stagger large upserts to stay inside compaction windows

Vectorize background compaction runs roughly every 5–10 minutes under low write
pressure. Staying under ~50 000 vectors per compaction window avoids segment
proliferation. Instrument write throughput via Analytics Engine counters.

---

## Anti-patterns

- **Treating `upsert()` 200 as "query-ready":** Write durability and query optimality
  are decoupled in any LSM-backed vector store. The 200 only means data is safe.
- **Running a single monthly or weekly bulk load without a post-load rebuild:** Each
  deferred rebuild compounds segment fragmentation.
- **Setting alert thresholds at steady-state P95 only:** A rapid rise from 50 ms to
  300 ms in 90 seconds is far more actionable than a static 250 ms threshold.
- **No regression on segment count as a leading indicator:** Segment count is a
  cheap, early signal compared to latency, which is a lagging indicator.

---

## Gotchas

- `rebuild()` is not idempotent-safe to call while a previous `rebuild()` is still
  running. Calling it concurrently from multiple Workers will not corrupt data, but the
  second call may return immediately without doing useful work. Use a Durable Object
  or KV lock to serialise rebuild calls.
- Vectorize currently does not expose a segment count or compaction state API. The only
  observable proxy is post-upsert query latency. Monitor it explicitly.
- Very large rebuilds (>10 million vectors) can take several minutes. Do not fire them
  during peak query traffic windows without validating the latency impact in staging.
- `describeIndex()` reflects accepted vector count, not indexed vector count. A vector
  may be accepted but not yet searchable for a few seconds after `upsert()`.

---

## Verification

After deploying the fix:

1. Run the nightly sync job in staging against a production-scale clone index.
2. Measure P95 query latency before and after the `rebuild()` call.
3. Confirm latency returns to baseline (≤60 ms) within 2 minutes of `rebuild()`
   completing.
4. Verify Analytics Engine dashboard shows post-upsert latency probe firing and staying
   green for 3 consecutive nights.
5. Confirm on-call runbook updated with "if Vectorize latency spikes: call rebuild()"
   as the first remediation step.

---

## Related

- `vectorize-dimension-mismatch-production-incident.md`
- `workers-ai-cold-start-latency-production-lesson.md`
- `analytics-engine-data-point-limit-exceeded.md`
- `cache-cold-start-avalanche.md`

---

## Sources

- Cloudflare Vectorize documentation: https://developers.cloudflare.com/vectorize/
- Cloudflare Vectorize `rebuild()` API reference
- Internal postmortem ticket PM-2026-041 (restricted)
- Cloudflare support ticket #CF-7721340 (Priority response)
