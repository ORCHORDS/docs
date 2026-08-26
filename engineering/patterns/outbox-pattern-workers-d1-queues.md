# Transactional Outbox Pattern with D1 and Workers Queues

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Worker writes a record to D1 and needs to emit a domain event (e.g., to a downstream queue consumer), but a crash between the DB write and the `queue.send()` call causes silent data loss. You need an atomic guarantee that the event is always delivered exactly once after the business transaction commits.

---

## Context

The transactional outbox pattern co-locates the event payload in the same database transaction as the business change, eliminating the dual-write hazard. A separate Cron Worker polls the `outbox` table for unpublished rows, enqueues them to Workers Queues, and marks them published only after the enqueue acknowledges success. This gives at-least-once delivery with a single source of truth. D1's `db.batch()` API makes the two-row atomic write straightforward. The polling interval and batch size are tunable to control throughput vs. latency trade-offs.

---

## Schema — D1 Outbox Table

```sql
CREATE TABLE IF NOT EXISTS outbox (
  id           TEXT    PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  aggregate_id TEXT    NOT NULL,
  event_type   TEXT    NOT NULL,
  payload      TEXT    NOT NULL,   -- JSON blob
  published_at TEXT    DEFAULT NULL,
  created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
  ON outbox (created_at)
  WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS orders (
  id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  user_id    TEXT NOT NULL,
  total_cents INTEGER NOT NULL,
  status     TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
```

---

## Implementation — Business Logic Worker

```typescript
// src/handlers/create-order.ts
import { Env } from '../types';

interface OrderPayload {
  userId: string;
  totalCents: number;
  items: Array<{ sku: string; qty: number }>;
}

export async function handleCreateOrder(
  payload: OrderPayload,
  env: Env,
): Promise<Response> {
  const orderId = crypto.randomUUID();
  const eventId = crypto.randomUUID();

  const orderInsert = env.DB.prepare(
    `INSERT INTO orders (id, user_id, total_cents, status)
     VALUES (?1, ?2, ?3, 'pending')`,
  ).bind(orderId, payload.userId, payload.totalCents);

  const outboxInsert = env.DB.prepare(
    `INSERT INTO outbox (id, aggregate_id, event_type, payload)
     VALUES (?1, ?2, ?3, ?4)`,
  ).bind(
    eventId,
    orderId,
    'order.created',
    JSON.stringify({
      orderId,
      userId: payload.userId,
      totalCents: payload.totalCents,
      items: payload.items,
    }),
  );

  // Atomic: both statements succeed or both fail
  await env.DB.batch([orderInsert, outboxInsert]);

  return Response.json({ orderId }, { status: 201 });
}
```

---

## Implementation — Outbox Relay Cron Worker

```typescript
// src/cron/outbox-relay.ts
import { Env } from '../types';

const BATCH_SIZE = 100;

interface OutboxRow {
  id: string;
  aggregate_id: string;
  event_type: string;
  payload: string;
  created_at: string;
}

export async function runOutboxRelay(env: Env): Promise<void> {
  const rows = await env.DB.prepare(
    `SELECT id, aggregate_id, event_type, payload, created_at
     FROM outbox
     WHERE published_at IS NULL
     ORDER BY created_at ASC
     LIMIT ?1`,
  )
    .bind(BATCH_SIZE)
    .all<OutboxRow>();

  if (!rows.results.length) return;

  const messages = rows.results.map((row) => ({
    body: {
      id: row.id,
      aggregateId: row.aggregate_id,
      eventType: row.event_type,
      payload: JSON.parse(row.payload),
      occurredAt: row.created_at,
    },
    contentType: 'json' as const,
  }));

  // Enqueue first — if this fails we retry next cron tick
  await env.DOMAIN_EVENTS_QUEUE.sendBatch(messages);

  // Mark published only after successful enqueue
  const ids = rows.results.map((r) => r.id);
  const placeholders = ids.map((_, i) => `?${i + 1}`).join(', ');
  await env.DB.prepare(
    `UPDATE outbox
     SET published_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
     WHERE id IN (${placeholders})`,
  )
    .bind(...ids)
    .run();

  console.log(`[outbox-relay] published ${ids.length} events`);
}

// Wrangler scheduled handler
export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext) {
    ctx.waitUntil(runOutboxRelay(env));
  },
};
```

---

## Integration — wrangler.toml

```toml
name = "outbox-relay"
main = "src/cron/outbox-relay.ts"
compatibility_date = "2024-09-23"

[[d1_databases]]
binding    = "DB"
database_name = "my-app-db"
database_id   = "<your-d1-id>"

[[queues.producers]]
binding    = "DOMAIN_EVENTS_QUEUE"
queue      = "domain-events"

[[queues.consumers]]
queue      = "domain-events"
max_batch_size    = 50
max_batch_timeout = 5
max_retries       = 3
dead_letter_queue = "domain-events-dlq"

[triggers]
crons = ["* * * * *"]   # every minute
```

---

## Anti-patterns

- **Fire-and-forget queue.send() inside the business handler** — loses the event if the Worker is evicted before the call completes; always use the outbox table instead.
- **Marking published before enqueue** — if the queue call fails the row is silently dropped; always enqueue first.
- **Querying outbox without an index on `published_at IS NULL`** — SQLite partial indexes make unpublished-row scans O(unpublished) not O(total).
- **Deleting outbox rows immediately** — keep rows for at least 7 days for auditability; add a separate purge cron.

---

## Gotchas

- D1 `db.batch()` is atomic within a single D1 region; cross-region replication lag is separate from the transaction guarantee.
- Workers Queues `sendBatch()` has a 256 KB per-message and 4 MB per-batch limit; chunk large payloads or store them in R2 and put the R2 key in the event.
- The cron Worker runs at most once per minute; for sub-minute latency consider a Queue consumer that writes back to trigger immediate processing.
- If the relay crashes after enqueue but before marking published, the same events re-enqueue; consumers must be idempotent (deduplicate on `id`).

---

## Verification

```bash
# Check unpublished backlog
wrangler d1 execute my-app-db --remote \
  --command "SELECT count(*) AS backlog FROM outbox WHERE published_at IS NULL;"

# Inspect latest events
wrangler d1 execute my-app-db --remote \
  --command "SELECT id, event_type, published_at FROM outbox ORDER BY created_at DESC LIMIT 10;"

# Tail relay logs
wrangler tail outbox-relay --format pretty

# Send a test order and watch the outbox fill then drain
curl -X POST https://my-worker.example.com/orders \
  -H 'Content-Type: application/json' \
  -d '{"userId":"u1","totalCents":4999,"items":[{"sku":"ABC","qty":1}]}'
```

---

## Related

- `saga-pattern-workers-durable-objects.md`
- `retry-with-jitter-pattern-workers.md`

---

## Sources

- Cloudflare D1 batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Queues sendBatch — https://developers.cloudflare.com/queues/reference/javascript-apis/#producer
- Microservices Patterns — Transactional Outbox — https://microservices.io/patterns/data/transactional-outbox.html
