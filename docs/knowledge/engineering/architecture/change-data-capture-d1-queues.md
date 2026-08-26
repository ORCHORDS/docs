# Change Data Capture with D1 and Cloudflare Queues

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case
Multiple downstream consumers need to react to row-level mutations in a D1 database (inserts, updates, deletes) without coupling every write path to every consumer. A CDC pipeline decouples producers from consumers and enables search index rebuilds, cache invalidation, and audit logs to evolve independently.

## Context
D1 does not expose native change streams or triggers. The pattern is implemented at the application layer: every write goes through a repository wrapper that appends a change event to Cloudflare Queues in the same atomic batch as the D1 write. Consumers are separate Workers subscribed to the queue. Because D1 transactions are local to a single Worker invocation, the outbox sub-pattern keeps the event enqueue inside the same logical write so partial failures do not produce phantom events.

## Write-Side — Repository Wrapper

The repository wraps D1 statements and emits change events in the same unit of work.

```typescript
// src/repositories/order-repository.ts
import type { D1Database, Queue } from '@cloudflare/workers-types';

export interface OrderRow {
  id: string;
  customer_id: string;
  status: string;
  total_cents: number;
  updated_at: number;
}

export interface ChangeEvent<T> {
  table: string;
  op: 'INSERT' | 'UPDATE' | 'DELETE';
  payload: T;
  ts: number;
}

export class OrderRepository {
  constructor(
    private readonly db: D1Database,
    private readonly changeQueue: Queue<ChangeEvent<OrderRow>>
  ) {}

  async upsertOrder(order: OrderRow): Promise<void> {
    // 1. Write to D1
    await this.db
      .prepare(
        `INSERT INTO orders (id, customer_id, status, total_cents, updated_at)
         VALUES (?, ?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET
           status = excluded.status,
           total_cents = excluded.total_cents,
           updated_at = excluded.updated_at`
      )
      .bind(
        order.id,
        order.customer_id,
        order.status,
        order.total_cents,
        order.updated_at
      )
      .run();

    // 2. Emit CDC event — best-effort enqueue after a confirmed D1 write
    await this.changeQueue.send({
      table: 'orders',
      op: 'INSERT',
      payload: order,
      ts: Date.now(),
    });
  }

  async deleteOrder(id: string): Promise<void> {
    const existing = await this.db
      .prepare('SELECT * FROM orders WHERE id = ?')
      .bind(id)
      .first<OrderRow>();

    if (!existing) return;

    await this.db.prepare('DELETE FROM orders WHERE id = ?').bind(id).run();

    await this.changeQueue.send({
      table: 'orders',
      op: 'DELETE',
      payload: existing,
      ts: Date.now(),
    });
  }
}
```

## Queue Consumer — Fan-Out to Multiple Handlers

The consumer Worker receives batches of change events and routes each to registered handlers.

```typescript
// src/workers/cdc-consumer.ts
import type { Queue, MessageBatch } from '@cloudflare/workers-types';
import type { ChangeEvent, OrderRow } from '../repositories/order-repository';

interface Env {
  SEARCH_INDEX: KVNamespace;
  AUDIT_LOG: D1Database;
}

type Handler = (event: ChangeEvent<OrderRow>, env: Env) => Promise<void>;

const HANDLERS: Record<string, Handler[]> = {
  orders: [rebuildSearchIndex, writeAuditLog],
};

async function rebuildSearchIndex(
  event: ChangeEvent<OrderRow>,
  env: Env
): Promise<void> {
  const key = `order:${event.payload.id}`;
  if (event.op === 'DELETE') {
    await env.SEARCH_INDEX.delete(key);
  } else {
    await env.SEARCH_INDEX.put(key, JSON.stringify(event.payload), {
      expirationTtl: 86400 * 7,
    });
  }
}

async function writeAuditLog(
  event: ChangeEvent<OrderRow>,
  env: Env
): Promise<void> {
  await env.AUDIT_LOG.prepare(
    `INSERT INTO audit_log (table_name, op, row_id, snapshot, created_at)
     VALUES (?, ?, ?, ?, ?)`
  )
    .bind(
      event.table,
      event.op,
      event.payload.id,
      JSON.stringify(event.payload),
      event.ts
    )
    .run();
}

export default {
  async queue(
    batch: MessageBatch<ChangeEvent<OrderRow>>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const event = msg.body;
      const handlers = HANDLERS[event.table] ?? [];

      try {
        await Promise.all(handlers.map((h) => h(event, env)));
        msg.ack();
      } catch (err) {
        // Returning without ack causes the queue to redeliver
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};
```

## Snapshot Consistency — Polling Fallback

For tables that are not yet instrumented with CDC, a periodic Durable Object alarm polls for rows changed since the last watermark.

```typescript
// src/durable-objects/snapshot-poller.ts
export class SnapshotPoller implements DurableObject {
  private storage: DurableObjectStorage;
  private env: { DB: D1Database; CHANGE_QUEUE: Queue };

  constructor(state: DurableObjectState, env: typeof this.env) {
    this.storage = state.storage;
    this.env = env;
    state.blockConcurrencyWhile(async () => {
      if (!(await this.storage.get('watermark'))) {
        await this.storage.put('watermark', 0);
        await this.storage.setAlarm(Date.now() + 60_000);
      }
    });
  }

  async alarm(): Promise<void> {
    const watermark = (await this.storage.get<number>('watermark')) ?? 0;
    const rows = await this.env.DB.prepare(
      'SELECT * FROM orders WHERE updated_at > ? ORDER BY updated_at LIMIT 500'
    )
      .bind(watermark)
      .all<{ id: string; updated_at: number }>();

    if (rows.results.length > 0) {
      const messages = rows.results.map((r) => ({
        body: { table: 'orders', op: 'UPDATE' as const, payload: r, ts: Date.now() },
      }));
      await this.env.CHANGE_QUEUE.sendBatch(messages);
      const maxWatermark = Math.max(...rows.results.map((r) => r.updated_at));
      await this.storage.put('watermark', maxWatermark);
    }

    await this.storage.setAlarm(Date.now() + 60_000);
  }

  async fetch(_req: Request): Promise<Response> {
    return Response.json({ watermark: await this.storage.get('watermark') });
  }
}
```

## Anti-patterns
- Enqueuing the change event *before* the D1 write commits — produces phantom events when the write subsequently fails
- Using a single queue for all tables without message-type routing — consumers must deserialize every message to filter irrelevant tables
- Ignoring `msg.retry()` on handler failure — events are silently dropped after exhausting the delivery window
- Polling with `SELECT *` and no watermark — full-table scans degrade D1 on large tables

## Gotchas
- Cloudflare Queues deliver at-least-once; downstream handlers must be idempotent using the row's primary key + `updated_at` as a deduplication key
- D1 is strongly consistent within a single region but CDC consumers may observe lag of several hundred milliseconds when reading from Queues
- The `sendBatch` limit is 256 messages per call; chunk large polling results accordingly
- Audit log writes in the consumer Worker also touch D1 — take care not to trigger another CDC cycle

## Verification
```bash
# 1. Insert an order via the API
curl -X POST https://api.example.workers.dev/orders \
  -H 'content-type: application/json' \
  -d '{"id":"ord-001","customer_id":"cust-42","status":"pending","total_cents":4999}'

# 2. Check the search index KV entry was created
wrangler kv key get --namespace-id=<NS_ID> "order:ord-001"

# 3. Check the audit log in D1
wrangler d1 execute <DB_NAME> --command \
  "SELECT * FROM audit_log WHERE row_id = 'ord-001' ORDER BY created_at DESC LIMIT 5"
```

## Related
- [Outbox Pattern](outbox-pattern.md)
- [Event Sourcing with D1 Append-Only Store](event-sourcing-d1-append-only-store.md)
- [Temporal Decoupling with Cloudflare Queues](temporal-decoupling-cloudflare-queues.md)
- [Durable Object Alarm API Scheduled Retry](durable-object-alarm-api-scheduled-retry.md)

## Sources
- Debezium CDC concepts: https://debezium.io/documentation/reference/stable/connectors/
- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
- D1 query API: https://developers.cloudflare.com/d1/worker-api/
