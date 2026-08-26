# D1 High-Throughput Ingestion via Workers Queues

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case
An event-heavy endpoint (click-tracking, IoT telemetry, webhook fan-in) must persist thousands
of rows per second to D1, but direct per-request INSERT calls saturate D1's write throughput
and inflate Worker CPU billing.

## Context
D1's per-database write limit is enforced at the SQLite WAL level; many small single-row
INSERTs are far less efficient than a single multi-row INSERT because each write requires a
WAL flush. Workers Queues decouple the hot ingest path from the database write path: the
producer Worker acknowledges the HTTP request immediately after enqueuing, while a separate
consumer Worker drains the queue in configurable batches (up to 10 000 messages or 30 s,
whichever comes first) and writes them to D1 in a single prepared-statement batch call.
This pattern trades near-real-time visibility for throughput, which is acceptable for
analytics, logging, and audit workloads.

## Schema

```sql
-- migrations/0001_events.sql
CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id   TEXT    NOT NULL,
  event_type  TEXT    NOT NULL,
  payload     TEXT    NOT NULL,   -- JSON blob
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX IF NOT EXISTS idx_events_tenant_created
  ON events (tenant_id, created_at DESC);

-- Dead-letter sink for poison messages
CREATE TABLE IF NOT EXISTS events_dlq (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_body    TEXT    NOT NULL,
  error       TEXT    NOT NULL,
  failed_at   INTEGER NOT NULL DEFAULT (unixepoch())
);
```

## Producer Worker (HTTP → Queue)

```typescript
// src/producer.ts
export interface Env {
  EVENT_QUEUE: Queue<EventMessage>;
}

interface EventMessage {
  tenantId: string;
  eventType: string;
  payload: Record<string, unknown>;
  enqueueTs: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    let body: EventMessage;
    try {
      body = await request.json<EventMessage>();
    } catch {
      return new Response('Invalid JSON', { status: 400 });
    }

    await env.EVENT_QUEUE.send({
      tenantId:  body.tenantId,
      eventType: body.eventType,
      payload:   body.payload,
      enqueueTs: Date.now(),
    });

    return Response.json({ queued: true }, { status: 202 });
  },
};
```

## Consumer Worker (Queue → D1 Batch)

```typescript
// src/consumer.ts
export interface Env {
  DB: D1Database;
}

interface EventMessage {
  tenantId: string;
  eventType: string;
  payload: Record<string, unknown>;
  enqueueTs: number;
}

export default {
  async queue(batch: MessageBatch<EventMessage>, env: Env): Promise<void> {
    const messages = batch.messages;

    // Build one multi-row INSERT per batch — far cheaper than N single INSERTs.
    const placeholders = messages
      .map((_, i) => `(?${i * 3 + 1}, ?${i * 3 + 2}, ?${i * 3 + 3})`)
      .join(', ');

    const values = messages.flatMap((m) => [
      m.body.tenantId,
      m.body.eventType,
      JSON.stringify(m.body.payload),
    ]);

    try {
      await env.DB.prepare(
        `INSERT INTO events (tenant_id, event_type, payload) VALUES ${placeholders}`
      )
        .bind(...values)
        .run();

      // Acknowledge all messages only after a successful write.
      batch.ackAll();
    } catch (err) {
      // Retry the whole batch (Queues will re-deliver up to maxRetries times).
      // Poison individual messages are nacked individually on last retry.
      const isLastRetry = messages.some((m) => m.attempts >= 3);
      if (isLastRetry) {
        // Write survivors to DLQ, ack the rest.
        for (const msg of messages) {
          if (msg.attempts >= 3) {
            await env.DB.prepare(
              'INSERT INTO events_dlq (raw_body, error) VALUES (?1, ?2)'
            )
              .bind(JSON.stringify(msg.body), String(err))
              .run();
            msg.ack();
          } else {
            msg.retry();
          }
        }
      } else {
        batch.retryAll();
      }
    }
  },
};
```

## wrangler.toml Configuration

```toml
# wrangler.toml
name = "event-ingestion"
main = "src/producer.ts"
compatibility_date = "2026-08-01"

[[d1_databases]]
binding     = "DB"
database_name = "prod-db"
database_id   = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[queues.producers]]
queue   = "event-queue"
binding = "EVENT_QUEUE"

# Consumer is a separate Worker that shares the same D1 binding.
# Define it in wrangler.toml workers array or as a separate wrangler.toml.
[[queues.consumers]]
queue             = "event-queue"
max_batch_size    = 500       # rows per consumer invocation
max_batch_timeout = 10        # seconds to wait before flushing a partial batch
max_retries       = 3
dead_letter_queue = "event-queue-dlq"
```

## Throughput Tuning

```typescript
// src/consumer-tuned.ts
// D1 bind() accepts up to 1 000 parameters; split oversized batches.

async function insertChunked(
  db: D1Database,
  rows: Array<[string, string, string]>,
  chunkSize = 333  // 333 rows × 3 params = 999 params < 1 000 limit
): Promise<void> {
  for (let i = 0; i < rows.length; i += chunkSize) {
    const chunk = rows.slice(i, i + chunkSize);
    const placeholders = chunk
      .map((_, j) => `(?${j * 3 + 1}, ?${j * 3 + 2}, ?${j * 3 + 3})`)
      .join(', ');
    const values = chunk.flat();

    await db
      .prepare(`INSERT INTO events (tenant_id, event_type, payload) VALUES ${placeholders}`)
      .bind(...values)
      .run();
  }
}
```

## Anti-patterns
- Setting `max_batch_size` to 1 — this defeats the purpose and results in N single-row INSERTs.
- Calling `batch.ackAll()` *before* the D1 write — a Worker crash after ack permanently loses the messages.
- Building the placeholder string with string interpolation of message values instead of bound parameters — SQL injection risk.
- Using the consumer for reads or business logic — the consumer should only write; read traffic goes to D1 directly.
- Unbounded retry loops inside the consumer — always respect `msg.attempts` and route to a DLQ on exhaustion.
- Ignoring the 1 000 bound-parameter limit — queries with more params are rejected by D1 at runtime.

## Gotchas
- Workers Queues delivers *at least once* — the `events` table must tolerate duplicate `payload` rows, or add a dedup key column with a UNIQUE constraint and `ON CONFLICT IGNORE`.
- `max_batch_timeout` only applies when the queue is below `max_batch_size`; a full batch fires immediately.
- Consumer Workers bill CPU time per message processed, not per batch — large batches are more cost-efficient.
- D1 write latency is ~5–15 ms per batch regardless of row count; the bottleneck at high volume is the queue drain rate, not D1 throughput.
- The dead-letter queue configured in `wrangler.toml` is a *separate* Queues queue, not the `events_dlq` D1 table — both are useful for different failure modes.

## Verification

```bash
# Deploy both workers
npx wrangler deploy --config wrangler.producer.toml
npx wrangler deploy --config wrangler.consumer.toml

# Send 1 000 events concurrently
seq 1 1000 | xargs -P 100 -I{} \
  curl -s -X POST https://<worker>.workers.dev/event \
       -H 'Content-Type: application/json' \
       -d '{"tenantId":"t1","eventType":"click","payload":{"page":"/home"}}'

# Wait for queue to drain (~10–30 s), then verify row count
npx wrangler d1 execute prod-db \
  --command "SELECT COUNT(*) AS cnt FROM events WHERE tenant_id='t1';"
# Expected: cnt = 1000

# Check DLQ
npx wrangler d1 execute prod-db \
  --command "SELECT COUNT(*) FROM events_dlq;"
```

## Related
- [d1-batch-operations-performance.md](d1-batch-operations-performance.md)
- [d1-dead-letter-queue-retry-workers.md](d1-dead-letter-queue-retry-workers.md)
- [d1-upsert-conflict-resolution-workers.md](d1-upsert-conflict-resolution-workers.md)
- [d1-time-series-partitioning.md](d1-time-series-partitioning.md)
- [time-series-data-cloudflare-analytics-engine.md](time-series-data-cloudflare-analytics-engine.md)

## Sources
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/reference/configuration/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/queues/examples/send-batch-messages/
