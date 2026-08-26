# Outbox Pattern for Reliable Event Publishing from Cloudflare Workers

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Worker updates domain state in D1 and then attempts to publish an event to Cloudflare Queues, but a failure between the two steps means either the event is lost or published without the state update being committed. You need atomic event publishing so downstream consumers always see exactly what was persisted, with no silent data loss.

## Context

The Outbox pattern solves the dual-write problem by treating event publication as a two-phase process. The domain event is written to an `outbox` table inside the same D1 transaction as the state change, making it atomic by construction. A separate Cron Worker polls the outbox, publishes each unpublished row to Queues, and marks it `published`. Because D1 is the source of truth, a Worker crash at any point leaves the system in a recoverable state. Idempotency on the consumer side completes the reliability guarantee.

## Outbox Table Schema and Transactional Write

```typescript
// schema.sql (run via wrangler d1 execute)
// CREATE TABLE outbox (
//   id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
//   event_id    TEXT NOT NULL UNIQUE,   -- idempotency key
//   event_type  TEXT NOT NULL,
//   payload     TEXT NOT NULL,          -- JSON
//   status      TEXT NOT NULL DEFAULT 'pending',  -- pending | published | failed
//   attempts    INTEGER NOT NULL DEFAULT 0,
//   created_at  INTEGER NOT NULL DEFAULT (unixepoch()),
//   published_at INTEGER,
//   deleted_at  INTEGER
// );
// CREATE INDEX idx_outbox_status ON outbox(status, created_at);

import { Env } from './types';

export interface DomainEvent {
  event_id: string;   // UUID v4, caller-supplied for idempotency
  event_type: string;
  payload: unknown;
}

export async function saveOrderWithOutbox(
  env: Env,
  order: { id: string; customerId: string; total: number },
  event: DomainEvent,
): Promise<void> {
  const payloadJson = JSON.stringify(event.payload);

  // Single D1 batch = atomic transaction
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO orders (id, customer_id, total, created_at)
       VALUES (?, ?, ?, unixepoch())`,
    ).bind(order.id, order.customerId, order.total),

    env.DB.prepare(
      `INSERT INTO outbox (event_id, event_type, payload)
       VALUES (?, ?, ?)
       ON CONFLICT(event_id) DO NOTHING`,
    ).bind(event.event_id, event.event_type, payloadJson),
  ]);
}
```

## Cron Worker: Polling and Publishing

```typescript
// cron-worker.ts  —  wrangler.toml: crons = ["*/1 * * * *"]
import { Env } from './types';

const BATCH_SIZE = 50;
const MAX_ATTEMPTS = 5;
const BASE_BACKOFF_MS = 500;

export async function publishOutbox(env: Env): Promise<void> {
  const rows = await env.DB.prepare(
    `SELECT id, event_id, event_type, payload, attempts
     FROM   outbox
     WHERE  status = 'pending'
       AND  (deleted_at IS NULL OR deleted_at > unixepoch())
     ORDER  BY created_at
     LIMIT  ?`,
  ).bind(BATCH_SIZE).all<OutboxRow>();

  for (const row of rows.results) {
    try {
      await env.EVENT_QUEUE.send(
        { event_id: row.event_id, event_type: row.event_type, payload: JSON.parse(row.payload) },
        { contentType: 'json' },
      );

      await env.DB.prepare(
        `UPDATE outbox
         SET status = 'published', published_at = unixepoch(), attempts = attempts + 1
         WHERE id = ?`,
      ).bind(row.id).run();
    } catch (err) {
      const nextAttempt = row.attempts + 1;
      const newStatus = nextAttempt >= MAX_ATTEMPTS ? 'failed' : 'pending';
      const backoffSeconds = Math.pow(2, nextAttempt) * (BASE_BACKOFF_MS / 1000);

      await env.DB.prepare(
        `UPDATE outbox
         SET attempts = ?, status = ?,
             created_at = unixepoch() + ?   -- delay next pick-up
         WHERE id = ?`,
      ).bind(nextAttempt, newStatus, backoffSeconds, row.id).run();

      console.error(`outbox: failed to publish ${row.event_id}`, err);
    }
  }
}

interface OutboxRow {
  id: string;
  event_id: string;
  event_type: string;
  payload: string;
  attempts: number;
}
```

## Retention Policy and Soft Delete

Keep published rows for auditing but prevent unbounded table growth by soft-deleting after a retention window.

```typescript
// retention-worker.ts  —  crons = ["0 3 * * *"]
export async function pruneOutbox(env: Env): Promise<void> {
  const RETENTION_DAYS = 30;
  await env.DB.prepare(
    `UPDATE outbox
     SET deleted_at = unixepoch()
     WHERE status = 'published'
       AND published_at < unixepoch() - ?`,
  ).bind(RETENTION_DAYS * 86400).run();
}
```

## Idempotency on the Consumer Side

```typescript
// queue-consumer.ts
export async function handleQueueMessage(env: Env, msg: QueueMessage): Promise<void> {
  const event = msg.body as { event_id: string; event_type: string; payload: unknown };

  // Idempotency check — UNIQUE constraint on event_id prevents double-processing
  const insert = await env.DB.prepare(
    `INSERT INTO processed_events (event_id, processed_at)
     VALUES (?, unixepoch())
     ON CONFLICT(event_id) DO NOTHING`,
  ).bind(event.event_id).run();

  if (insert.meta.changes === 0) {
    // Already processed; ack without side effects
    msg.ack();
    return;
  }

  await dispatchEvent(env, event);
  msg.ack();
}
```

## Anti-patterns

- **Fire-and-forget after commit** — publishing to Queues outside the D1 batch means a Worker crash after the commit but before the send silently drops the event.
- **Polling too aggressively** — a 1-second cron is the minimum on Workers; use batching (`LIMIT 50`) rather than reducing the interval.
- **Deleting published rows immediately** — losing the audit trail makes replay and debugging impossible; always use soft delete with a retention window.
- **Shared event_id generation** — let the caller supply the `event_id` UUID before the transaction so it can be retried safely without generating duplicates.

## Gotchas

- D1 `batch()` executes statements atomically only within a single database; cross-database atomicity is not supported.
- `ON CONFLICT(event_id) DO NOTHING` silently swallows duplicate inserts — verify with `meta.changes === 0` if you need to detect them.
- Cloudflare Queues `send()` can throw on transient errors; always wrap in try/catch and update the outbox row rather than letting the Cron Worker crash.
- The `created_at` backoff trick (shifting the timestamp forward) works because the poll query orders by `created_at`; if you add a `retry_after` column the logic becomes clearer.
- D1 does not support stored procedures; all retry logic must live in the Worker.

## Verification

```bash
# Apply schema
wrangler d1 execute example project-db --file=schema.sql --env production

# Inspect pending outbox rows
wrangler d1 execute example project-db \
  --command="SELECT event_type, status, attempts, datetime(created_at,'unixepoch') FROM outbox WHERE status='pending' LIMIT 20" \
  --env production

# Trigger cron manually for local testing
wrangler dev --test-scheduled
curl "http://localhost:8787/__scheduled?cron=*%2F1+*+*+*+*"

# Count published vs failed
wrangler d1 execute example project-db \
  --command="SELECT status, COUNT(*) FROM outbox GROUP BY status" \
  --env production
```

## Related

- `event-carried-state-transfer-workers-queues.md`
- `read-model-projection-d1-queues-workers.md`
- `hexagonal-architecture-workers-ports-adapters.md`

## Sources

- Cloudflare D1 Batch API — https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
- Cloudflare Queues Producer API — https://developers.cloudflare.com/queues/configuration/javascript-apis/#producer
- Cloudflare Cron Triggers — https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Microservices Patterns: Transactional Outbox — https://microservices.io/patterns/data/transactional-outbox.html
