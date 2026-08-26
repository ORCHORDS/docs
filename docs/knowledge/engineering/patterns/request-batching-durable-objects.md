# Request Batching via Durable Objects: Coalescing Writes into Bulk D1 Operations

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Individual Worker requests each write one row to D1 — an event, a metric sample, a
user action log. At 100 req/s, that is 100 separate D1 `INSERT` statements per
second. D1 charges per query and has a maximum of 6 write requests per second on
the free tier (25 on paid). Row-by-row inserts also carry per-statement overhead.
You need to absorb individual writes at high throughput and flush them to D1 in bulk
batches, reducing cost and write pressure without losing any records.

---

## Context

A Durable Object instance acts as a write buffer for a logical partition (tenant,
table, or shard). Individual Workers send their records to the DO over its HTTP
interface; the DO accumulates them in memory and periodically flushes a bulk D1
`INSERT` with `db.batch()`. The flush is triggered by either a size threshold or
a wall-clock interval (Durable Object `alarm`).

```
Worker A ─┐
Worker B ─┤── POST /buffer ──► DO: BatchBuffer
Worker C ─┘                         │
                                    ├── buffer[]=record[]
                                    │
                            alarm() or size threshold
                                    │
                                    └── D1.batch([INSERT …, INSERT …, …])
```

Only one DO instance exists per key (e.g. per `tenantId`), so the buffer is
consistent across all Worker invocations for that key without distributed locking.

---

## Section 1 — Durable Object: BatchBuffer

```typescript
// do/batch-buffer.ts

interface BufferedRecord {
  id:        string;
  eventType: string;
  payload:   string;    // JSON-serialised payload
  createdAt: string;
}

export interface Env {
  DB: D1Database;
}

export class BatchBuffer implements DurableObject {
  private buffer: BufferedRecord[] = [];

  // Flush when the buffer hits this size — prevents unbounded memory growth
  private readonly MAX_BATCH_SIZE = 250;

  // Alarm interval: flush every N milliseconds even if batch is not full
  private readonly FLUSH_INTERVAL_MS = 2_000;

  constructor(
    private readonly state: DurableObjectState,
    private readonly env:   Env,
  ) {
    // Restore in-memory buffer from DO storage on cold start
    this.state.blockConcurrencyWhile(async () => {
      this.buffer = (await this.state.storage.get<BufferedRecord[]>('buffer')) ?? [];
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/buffer' && request.method === 'POST') {
      const record = await request.json<BufferedRecord>();
      this.buffer.push(record);

      // Persist in-flight buffer to storage so a DO eviction doesn't lose records
      await this.state.storage.put('buffer', this.buffer);

      // Ensure the alarm is armed for the next flush window
      const existing = await this.state.storage.getAlarm();
      if (!existing) {
        await this.state.storage.setAlarm(Date.now() + this.FLUSH_INTERVAL_MS);
      }

      // Eagerly flush if we hit the size threshold
      if (this.buffer.length >= this.MAX_BATCH_SIZE) {
        await this.flush();
      }

      return Response.json({ buffered: true, queueDepth: this.buffer.length });
    }

    if (url.pathname === '/flush' && request.method === 'POST') {
      const flushed = await this.flush();
      return Response.json({ flushed });
    }

    return new Response('Not Found', { status: 404 });
  }

  async alarm(): Promise<void> {
    await this.flush();
    // Re-arm the alarm only if there are still records pending
    if (this.buffer.length > 0) {
      await this.state.storage.setAlarm(Date.now() + this.FLUSH_INTERVAL_MS);
    }
  }

  private async flush(): Promise<number> {
    if (this.buffer.length === 0) return 0;

    const batch  = this.buffer.splice(0, this.MAX_BATCH_SIZE);

    try {
      const stmts = batch.map((r) =>
        this.env.DB
          .prepare('INSERT OR IGNORE INTO events (id, event_type, payload, created_at) VALUES (?, ?, ?, ?)')
          .bind(r.id, r.eventType, r.payload, r.createdAt),
      );

      await this.env.DB.batch(stmts);

      // Persist the (now smaller) buffer — omit spliced records
      await this.state.storage.put('buffer', this.buffer);

      console.log(JSON.stringify({ event: 'batch_flushed', count: batch.length }));
      return batch.length;
    } catch (err) {
      // On D1 error, restore the batch to the front of the buffer
      this.buffer.unshift(...batch);
      await this.state.storage.put('buffer', this.buffer);
      console.error(JSON.stringify({ event: 'batch_flush_error', error: String(err), count: batch.length }));
      return 0;
    }
  }
}
```

---

## Section 2 — Worker: Sending Records to the DO

```typescript
// worker.ts

export interface Env {
  BATCH_BUFFER: DurableObjectNamespace;
  DB:           D1Database;
}

interface EventPayload {
  tenantId:  string;
  eventType: string;
  data:      Record<string, unknown>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    const { tenantId, eventType, data } = await request.json<EventPayload>();

    // Route to a DO instance keyed by tenantId — one buffer per tenant
    const id  = env.BATCH_BUFFER.idFromName(tenantId);
    const stub = env.BATCH_BUFFER.get(id);

    const record = {
      id:        crypto.randomUUID(),
      eventType,
      payload:   JSON.stringify(data),
      createdAt: new Date().toISOString(),
    };

    const resp = await stub.fetch('https://do/buffer', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(record),
    });

    return Response.json({ accepted: true, ...(await resp.json<object>()) }, { status: 202 });
  },
};
```

---

## Section 3 — wrangler.toml

```toml
name = "event-ingestion"

[[durable_objects.bindings]]
name       = "BATCH_BUFFER"
class_name = "BatchBuffer"

[[migrations]]
tag  = "v1"
new_classes = ["BatchBuffer"]

[[d1_databases]]
binding       = "DB"
database_name = "events-db"
database_id   = "<your-d1-db-id>"
```

---

## Section 4 — D1 Schema and Index

```sql
CREATE TABLE events (
  id          TEXT PRIMARY KEY,
  event_type  TEXT    NOT NULL,
  payload     TEXT    NOT NULL,
  created_at  TEXT    NOT NULL
);

CREATE INDEX idx_events_type_created ON events (event_type, created_at DESC);
```

`INSERT OR IGNORE` handles duplicate delivery (at-least-once from Workers) using
the `id` as the idempotency key.

---

## Section 5 — Partitioning Strategy

One DO instance per tenant works when tenants generate < 250 events per 2-second
window. For tenants with higher write rates, shard the buffer:

```typescript
// Shard by tenantId + time bucket to distribute load across DO instances
function bufferKey(tenantId: string, shardsPerTenant = 4): string {
  const shard = Math.floor(Math.random() * shardsPerTenant);
  return `${tenantId}:${shard}`;
}

const id = env.BATCH_BUFFER.idFromName(bufferKey(tenantId));
```

With 4 shards per tenant each handling 250 rows per flush, a single tenant can
sustain ~500 events/s with 2-second flush intervals.

---

## Anti-patterns

**Buffering in Worker module-level state instead of a DO** — Workers are stateless and
ephemeral. Module-level arrays disappear on each invocation or after idle eviction.
Only a Durable Object provides durable, request-consistent in-memory state.

**Not persisting the buffer to DO storage** — if the DO is evicted mid-buffer, all
records are lost. Write `state.storage.put('buffer', this.buffer)` after every
push and after every flush.

**Flushing synchronously on every Worker request** — this defeats the purpose. The
Worker should POST to the DO and return 202 immediately; the DO decides when to flush.

**Using a single global DO for all tenants** — one DO instance is single-threaded.
All write traffic serialised through one instance caps throughput. Key by tenant (or
shard) to scale horizontally.

---

## Gotchas

- **Durable Object alarms have a minimum fire interval of 1 second.** Sub-second
  flush intervals require the size-threshold path, not the alarm.
- **DO storage has a 128 KiB value size limit.** With 250 records at ~500 bytes each,
  the buffer JSON is ~125 KiB — close to the limit. Keep records compact or reduce
  `MAX_BATCH_SIZE` if payloads are large.
- **`db.batch()` is a single D1 network round-trip but each statement in the batch
  counts toward D1 write limits.** Batching reduces latency overhead, not the write
  quota directly. Monitor D1 metrics for write-limit errors.
- **The alarm fires at most once per second.** If the DO is evicted between alarm
  fires, storage is durable but the alarm itself must be re-set on the next `fetch`.
  Check and arm the alarm in `fetch` as shown above.
- **`INSERT OR IGNORE` requires `id` to be the PRIMARY KEY.** Using `ON CONFLICT`
  clauses instead allows custom upsert behaviour but adds SQL complexity.

---

## Verification

```bash
# 1. Send 10 rapid events for tenant-123 (should buffer, not flush yet)
for i in $(seq 1 10); do
  curl -X POST https://events.example.com/ \
    -H "Content-Type: application/json" \
    -d "{\"tenantId\":\"tenant-123\",\"eventType\":\"page_view\",\"data\":{\"page\":\"/home\"}}"
done

# 2. Wait for alarm fire (2 s) then query D1 — expect 10 rows
wrangler d1 execute events-db --command "SELECT COUNT(*) FROM events WHERE event_type='page_view'"

# 3. Send 250+ events rapidly — should trigger size-threshold flush mid-burst
for i in $(seq 1 260); do
  curl -s -X POST https://events.example.com/ \
    -H "Content-Type: application/json" \
    -d "{\"tenantId\":\"tenant-123\",\"eventType\":\"click\",\"data\":{}}" &
done
wait

wrangler d1 execute events-db --command "SELECT COUNT(*) FROM events"
```

---

## Related

- `unit-of-work-pattern-d1-workers.md` — batch D1 writes in a single transaction
- `outbox-pattern-d1-reliable-publishing.md` — reliable event emission via D1 outbox
- `distributed-lock-durable-objects.md` — Durable Objects for mutual exclusion
- `fan-out-queues-workers.md` — distribute batch-flushed events to downstream consumers
- `competing-consumers-workers-queues.md` — parallel queue processing after batch ingest

---

## Sources

- Cloudflare Durable Objects — developers.cloudflare.com/durable-objects/
- Cloudflare Durable Objects Alarms — developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare D1 `batch()` API — developers.cloudflare.com/d1/worker-api/d1-database/#batch
- "Buffered Writes Pattern", enterprise integration patterns — enterpriseintegrationpatterns.com
