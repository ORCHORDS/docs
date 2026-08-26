# Outbox Pattern: Workers, Queues, and Reliable Event Publishing

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Worker writes a new anonymous post to D1 and must publish a `PostCreated` event to downstream
consumers (notification fan-out, feed indexing, moderation queue). If the Worker publishes to
Cloudflare Queues after committing to D1 and the Queue send fails, the event is silently lost.
Conversely, publishing before the commit means downstream consumers may process events for rows
that never persisted.

## Context

Cloudflare Workers are stateless and single-threaded per request. D1 provides ACID transactions
within a single database. Cloudflare Queues offer at-least-once delivery but sit outside the D1
transaction boundary. The Transactional Outbox Pattern bridges this gap by treating the outbox
table as part of the same atomic D1 write, then draining it asynchronously.

## Outbox Pattern Overview

Write the domain entity change and the pending event to D1 in the same transaction. A separate
relay process (a Durable Object alarm or a Scheduled Worker) reads unprocessed rows from the
outbox table and forwards them to Cloudflare Queues, marking each row delivered only after the
`queue.send()` call succeeds.

```typescript
// schema (D1 migration)
// CREATE TABLE outbox (
//   id          TEXT PRIMARY KEY,
//   event_type  TEXT NOT NULL,
//   payload     TEXT NOT NULL,
//   created_at  INTEGER NOT NULL,
//   delivered   INTEGER NOT NULL DEFAULT 0
// );

interface Env {
  DB: D1Database;
  EVENTS: Queue;
}

interface OutboxRow {
  id: string;
  event_type: string;
  payload: string;
}

async function publishPost(
  env: Env,
  post: { id: string; body: string; authorToken: string }
): Promise<void> {
  const eventId = crypto.randomUUID();
  const payload = JSON.stringify({
    postId: post.id,
    preview: post.body.slice(0, 120),
  });

  // Atomic: entity + outbox row in one D1 transaction.
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO posts (id, body, author_token, created_at)
       VALUES (?, ?, ?, unixepoch())`
    ).bind(post.id, post.body, post.authorToken),

    env.DB.prepare(
      `INSERT INTO outbox (id, event_type, payload, created_at)
       VALUES (?, 'PostCreated', ?, unixepoch())`
    ).bind(eventId, payload),
  ]);
}
```

## Outbox Relay Implementation

A Durable Object armed with an alarm wakes every 5 seconds, reads undelivered outbox rows, sends
them to the Queue in a single batch, then marks them delivered. The alarm re-arms itself so
processing is continuous without a cron binding.

```typescript
export class OutboxRelay extends DurableObject {
  private readonly BATCH = 50;

  async alarm(): Promise<void> {
    const env = this.env as Env;

    const { results } = await env.DB.prepare(
      `SELECT id, event_type, payload FROM outbox
       WHERE delivered = 0
       ORDER BY created_at ASC
       LIMIT ?`
    )
      .bind(this.BATCH)
      .all<OutboxRow>();

    if (results.length === 0) {
      this.ctx.storage.setAlarm(Date.now() + 5_000);
      return;
    }

    const messages = results.map((row) => ({
      body: { eventType: row.event_type, payload: JSON.parse(row.payload) },
    }));

    await env.EVENTS.sendBatch(messages);

    const ids = results.map((r) => r.id);
    const placeholders = ids.map(() => '?').join(',');
    await env.DB.prepare(
      `UPDATE outbox SET delivered = 1 WHERE id IN (${placeholders})`
    )
      .bind(...ids)
      .run();

    // Re-arm immediately while there may be more rows.
    this.ctx.storage.setAlarm(Date.now() + 1_000);
  }

  async ensureArmed(): Promise<void> {
    const existing = await this.ctx.storage.getAlarm();
    if (existing === null) {
      this.ctx.storage.setAlarm(Date.now() + 1_000);
    }
  }
}
```

## Queue Consumer and Idempotency

Queue consumers will receive each message at least once. Stamp every outbox event with a stable
`eventId` derived from the outbox row primary key. Consumers check a `processed_events` table
before acting, making the handler idempotent.

```typescript
interface QueueMessage {
  eventType: string;
  payload: { postId: string; preview: string };
}

export default {
  async queue(batch: MessageBatch<QueueMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      const { eventType, payload } = msg.body;
      const eventId = msg.id; // Queues stable message ID

      const already = await env.DB.prepare(
        'SELECT 1 FROM processed_events WHERE id = ?'
      )
        .bind(eventId)
        .first();

      if (already) {
        msg.ack();
        continue;
      }

      // Domain handler per event type.
      if (eventType === 'PostCreated') {
        await handlePostCreated(env, payload);
      }

      await env.DB.prepare(
        `INSERT OR IGNORE INTO processed_events (id, processed_at)
         VALUES (?, unixepoch())`
      )
        .bind(eventId)
        .run();

      msg.ack();
    }
  },
} satisfies ExportedHandler<Env>;
```

## Retention and Archival

Keep the outbox table small. Prune rows older than 48 hours once delivered. A nightly Scheduled
Worker handles the sweep without blocking the hot path.

```typescript
export default {
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await env.DB.prepare(
      `DELETE FROM outbox
       WHERE delivered = 1
         AND created_at < unixepoch() - 172800`
    ).run();
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- Sending to the Queue inside the D1 transaction callback — the send is async and occurs after
  the batch resolves, making it invisible to the transaction scope.
- Using a TTL column to auto-expire undelivered rows — this silently drops events that never
  reached the relay.
- Polling from the request Worker (adds latency to the write path) instead of a dedicated relay.
- Batching outbox reads without ordering by `created_at` — causes out-of-order delivery to
  consumers that care about event sequence.

## Gotchas

- D1 `batch()` is atomic within a single D1 database but does not span multiple databases or
  external systems.
- The Durable Object alarm may fire more than once for the same interval on transient failures;
  the delivery-mark update must be idempotent (`UPDATE … WHERE delivered = 0`).
- Cloudflare Queues `sendBatch` is limited to 100 messages per call and 256 KB total body size.
- If the relay crashes after `sendBatch` but before the `UPDATE`, rows will be re-sent. Queue
  consumers must be idempotent (see idempotency section above).
- For example project's anonymous-author model, avoid including identifying fields in the outbox payload;
  use opaque `authorToken` hashes resolved by the consumer from a separate lookup.

## Verification

1. Write a post via the API. Assert that `outbox` contains exactly one undelivered row.
2. Trigger `OutboxRelay.alarm()` directly using the DO test harness. Assert the row is now
   `delivered = 1` and one Queue message arrived in the test consumer.
3. Replay the same Queue message. Assert the `processed_events` guard prevents duplicate handling.
4. Kill the relay mid-batch (throw before `UPDATE`). Assert no rows are permanently skipped after
   the alarm re-fires.

## Related

- [Outbox Pattern](outbox-pattern.md)
- [Async Job Queue — Cloudflare Queues and DOs](async-job-queue-cloudflare-queues-do.md)
- [Dead-Letter Queue Architecture](dead-letter-queue-architecture.md)
- [Dual Write Problem — Queues and Workers](dual-write-problem-queues-workers.md)
- [At-Least-Once Delivery](at-least-once-delivery.md)
- [Idempotency Design](idempotency-design.md)

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/d1/
- https://developers.cloudflare.com/durable-objects/api/alarms/
- https://microservices.io/patterns/data/transactional-outbox.html
