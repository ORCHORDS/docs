# Tail Worker Request Sampling

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Full request/response logging is prohibitively expensive at high traffic volumes. You want detailed trace data for debugging and performance analysis, but only for a small fraction of requests — say 1% — to keep costs manageable while still capturing real-world behaviour.

## Context

Cloudflare Tail Workers receive a stream of `TailEvent` objects for every request handled by a target Worker. By default every event is forwarded, but you can apply sampling logic in the Tail Worker itself: check a random number, record the trace ID in KV for hot lookups, and persist the full span payload in D1 for querying.

This pattern gives you:
- ~100x reduction in storage cost compared to logging everything
- Deterministic trace retrieval (look up any trace ID in KV to know whether it was sampled)
- SQL-queryable span data in D1 for dashboards and ad-hoc analysis

---

## Section 1 — Tail Worker entrypoint with 1% sampling

```typescript
// tail-sampler/src/index.ts
import type { TailEvent, TailItem } from '@cloudflare/workers-types';

export interface Env {
  SAMPLED_IDS: KVNamespace;   // stores traceId -> "1" with 24h TTL
  SPANS_DB: D1Database;       // persists sampled span rows
  SAMPLE_RATE: string;        // e.g. "0.01" for 1%
}

function shouldSample(rate: number): boolean {
  return Math.random() < rate;
}

function extractTraceId(event: TailItem): string {
  // Prefer a canonical trace-id header injected by the origin Worker
  const headers = event.request?.headers ?? {};
  return (
    (headers as Record<string, string>)['x-trace-id'] ??
    crypto.randomUUID()
  );
}

export default {
  async tail(events: TailEvent[], env: Env, ctx: ExecutionContext): Promise<void> {
    const rate = parseFloat(env.SAMPLE_RATE ?? '0.01');

    const sampled = events.filter(() => shouldSample(rate));
    if (sampled.length === 0) return;

    ctx.waitUntil(processSampled(sampled, env));
  },
};

async function processSampled(events: TailEvent[], env: Env): Promise<void> {
  for (const event of events) {
    for (const item of event) {
      const traceId = extractTraceId(item);
      await Promise.all([
        storeInKV(traceId, env),
        storeInD1(traceId, item, env),
      ]);
    }
  }
}
```

## Section 2 — KV storage for fast trace-ID lookup

```typescript
// tail-sampler/src/kv.ts
export async function storeInKV(
  traceId: string,
  env: { SAMPLED_IDS: KVNamespace }
): Promise<void> {
  // 24-hour TTL — keeps KV lean; old traces are automatically evicted
  await env.SAMPLED_IDS.put(traceId, '1', { expirationTtl: 86_400 });
}

export async function isSampled(
  traceId: string,
  env: { SAMPLED_IDS: KVNamespace }
): Promise<boolean> {
  const val = await env.SAMPLED_IDS.get(traceId);
  return val === '1';
}
```

## Section 3 — D1 schema and span persistence

```sql
-- migrations/0001_create_spans.sql
CREATE TABLE IF NOT EXISTS sampled_spans (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id    TEXT    NOT NULL,
  timestamp   INTEGER NOT NULL,  -- Unix ms
  method      TEXT,
  url         TEXT,
  status      INTEGER,
  duration_ms INTEGER,
  outcome     TEXT,
  logs        TEXT,   -- JSON array of console.log lines
  created_at  INTEGER DEFAULT (unixepoch() * 1000)
);

CREATE INDEX idx_spans_trace ON sampled_spans(trace_id);
CREATE INDEX idx_spans_ts    ON sampled_spans(timestamp);
```

```typescript
// tail-sampler/src/d1.ts
import type { TailItem } from '@cloudflare/workers-types';

export async function storeInD1(
  traceId: string,
  item: TailItem,
  env: { SPANS_DB: D1Database }
): Promise<void> {
  const logs = item.logs?.map((l) => l.message?.join(' ') ?? '').filter(Boolean) ?? [];

  await env.SPANS_DB.prepare(
    `INSERT INTO sampled_spans
       (trace_id, timestamp, method, url, status, duration_ms, outcome, logs)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    traceId,
    item.event?.request ? Date.now() : (item.timestamp ?? Date.now()),
    item.request?.method ?? null,
    item.request?.url ?? null,
    item.response?.status ?? null,
    item.cpuTime ?? null,
    item.outcome ?? null,
    JSON.stringify(logs)
  ).run();
}
```

## Section 4 — wrangler.toml configuration

```toml
# tail-sampler/wrangler.toml
name = "tail-sampler"
main = "src/index.ts"
compatibility_date = "2025-10-01"

# Declare this Worker as a tail consumer of the origin Worker
tail_consumers = [{ service = "my-origin-worker" }]

[vars]
SAMPLE_RATE = "0.01"

[[kv_namespaces]]
binding = "SAMPLED_IDS"
id      = "<your-kv-namespace-id>"

[[d1_databases]]
binding  = "SPANS_DB"
database_name = "spans"
database_id   = "<your-d1-database-id>"
```

```bash
# Deploy
wrangler deploy --config tail-sampler/wrangler.toml

# Apply migration
wrangler d1 migrations apply spans --remote
```

## Anti-patterns

- **Sampling inside the origin Worker** — adds latency to the hot path. Always do it in the Tail Worker.
- **Using a fixed modulo on request count** — introduces bias against bursty traffic patterns. Use `Math.random()` per event.
- **Storing raw `TailEvent` JSON in KV** — KV values have a 25 MB cap but more importantly KV is not queryable. Use D1 for structured span storage.
- **Infinite KV TTLs** — sampled trace IDs accumulate without bound. Always set an `expirationTtl`.

## Gotchas

- `TailEvent` is an `AsyncIterable<TailItem>` — iterate with `for...of` or spread to an array before mapping.
- `ctx.waitUntil()` is required; returning a promise from `tail()` without it may be cut off when the isolate is evicted.
- D1 write throughput is currently ~1000 row-writes/second per database on the free tier; size your sample rate accordingly.
- KV consistency is eventual — a downstream service checking `isSampled()` immediately after ingestion may see a cache miss.

## Verification

```bash
# Check recent spans in D1
wrangler d1 execute spans --remote \
  --command "SELECT trace_id, method, url, status, duration_ms FROM sampled_spans ORDER BY timestamp DESC LIMIT 20;"

# Confirm KV key exists for a known trace
wrangler kv key get --namespace-id=<id> "<trace-id>"

# Live tail the Tail Worker itself for debugging
wrangler tail tail-sampler
```

## Related

- `workers-real-user-monitoring-beacon.md` — Analytics Engine-based RUM pipeline
- `workers-log-redaction-pii-tail.md` — PII scrubbing before Logpush forwarding
- Cloudflare Tail Workers docs: https://developers.cloudflare.com/workers/observability/tail-workers/

## Sources

- https://developers.cloudflare.com/workers/observability/tail-workers/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- https://developers.cloudflare.com/d1/
