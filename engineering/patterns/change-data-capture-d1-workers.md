# Change Data Capture with D1 and Cloudflare Workers

2026-08-24 / example.com / production

---

## Symptom / Use-case

You need to propagate every row-level change (insert, update, delete) that happens in a D1 database to downstream systems—search indexes, analytics pipelines, caches, or audit logs—without modifying every application code path that writes to D1.

Without a native CDC mechanism, teams resort to:
- Polling tables on a cron trigger (misses intermediate states, high read load).
- Adding `queue.send()` calls next to every `db.run()` (error-prone, easy to forget).
- Building a full event-sourcing model (high complexity, not always warranted).

The CDC pattern on D1 uses a `changes` ledger table as the source of truth, a cron-triggered Worker that reads the ledger and fans out to downstream systems, and an optional Durable Object as a watermark tracker.

---

## Context

D1 does not expose a binary replication log (binlog) the way Postgres does, so CDC must be implemented at the application layer. The approach here relies on two primitives:

1. **A `changes` table** written to transactionally alongside every mutating operation.
2. **A watermark** stored in a Durable Object or KV that tracks the last `change_id` successfully processed by each downstream consumer.
3. **A cron Worker** that reads unbatched changes above the watermark, fans them out, and advances the watermark only after all downstream writes succeed.

Because D1 supports multi-statement transactions via batched prepared statements, writing to the `changes` table and the business table in the same batch is atomic.

---

## Code sections

### 1. D1 schema – business table plus changes ledger

```sql
-- migrations/0001_initial.sql

CREATE TABLE IF NOT EXISTS products (
  id          TEXT PRIMARY KEY,
  tenant_id   TEXT NOT NULL,
  name        TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  deleted_at  TEXT,
  updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_tenant ON products (tenant_id);

CREATE TABLE IF NOT EXISTS changes (
  change_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name  TEXT    NOT NULL,
  operation   TEXT    NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
  row_key     TEXT    NOT NULL,
  before_json TEXT,
  after_json  TEXT,
  occurred_at TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_changes_change_id ON changes (change_id);
```

### 2. Repository helper – atomic write + CDC entry

```typescript
// lib/products-repo.ts

interface Product {
  id: string;
  tenantId: string;
  name: string;
  priceCents: number;
  deletedAt: string | null;
  updatedAt: string;
}

export async function upsertProduct(
  db: D1Database,
  product: Omit<Product, 'updatedAt' | 'deletedAt'> & { updatedAt?: string }
): Promise<void> {
  const now = new Date().toISOString();
  const prevResult = await db.prepare('SELECT * FROM products WHERE id = ?').bind(product.id).first<Record<string, unknown>>();
  const beforeJson = prevResult ? JSON.stringify(prevResult) : null;
  const afterJson = JSON.stringify({ ...product, updatedAt: now, deletedAt: null });
  const op = prevResult ? 'UPDATE' : 'INSERT';

  await db.batch([
    db.prepare(
      `INSERT INTO products (id, tenant_id, name, price_cents, deleted_at, updated_at)
       VALUES (?, ?, ?, ?, NULL, ?)
       ON CONFLICT (id) DO UPDATE SET name = excluded.name, price_cents = excluded.price_cents, updated_at = excluded.updated_at`
    ).bind(product.id, product.tenantId, product.name, product.priceCents, now),
    db.prepare(
      `INSERT INTO changes (table_name, operation, row_key, before_json, after_json, occurred_at)
       VALUES ('products', ?, ?, ?, ?, ?)`
    ).bind(op, product.id, beforeJson, afterJson, now),
  ]);
}

export async function softDeleteProduct(db: D1Database, id: string): Promise<void> {
  const now = new Date().toISOString();
  const prevResult = await db.prepare('SELECT * FROM products WHERE id = ?').bind(id).first<Record<string, unknown>>();
  if (!prevResult) return;
  const beforeJson = JSON.stringify(prevResult);
  await db.batch([
    db.prepare(`UPDATE products SET deleted_at = ?, updated_at = ? WHERE id = ?`).bind(now, now, id),
    db.prepare(
      `INSERT INTO changes (table_name, operation, row_key, before_json, after_json, occurred_at)
       VALUES ('products', 'DELETE', ?, ?, NULL, ?)`
    ).bind(id, beforeJson, now),
  ]);
}
```

### 3. Watermark tracker – Durable Object

```typescript
// durable-objects/cdc-watermark/src/CdcWatermark.ts

export class CdcWatermark implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) { this.state = state; }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const consumer = url.searchParams.get('consumer') ?? 'default';

    if (request.method === 'GET') {
      const mark = (await this.state.storage.get<number>(`wm:${consumer}`)) ?? 0;
      return Response.json({ consumer, watermark: mark });
    }

    if (request.method === 'POST') {
      const { watermark } = await request.json<{ watermark: number }>();
      await this.state.storage.put(`wm:${consumer}`, watermark);
      return Response.json({ consumer, watermark });
    }

    return new Response('Method Not Allowed', { status: 405 });
  }
}
```

### 4. CDC relay Worker – cron-triggered fan-out

```typescript
// workers/cdc-relay/src/index.ts

interface ChangeRow {
  change_id: number;
  table_name: string;
  operation: 'INSERT' | 'UPDATE' | 'DELETE';
  row_key: string;
  before_json: string | null;
  after_json: string | null;
  occurred_at: string;
}

interface Env {
  DB: D1Database;
  CDC_WATERMARK: DurableObjectNamespace;
  SEARCH_INDEX_WORKER: Fetcher;
  ANALYTICS_QUEUE: Queue<ChangeRow>;
}

const CONSUMER_ID = 'cdc-relay-v1';
const BATCH_SIZE = 100;

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(relay(env));
  },
};

async function relay(env: Env): Promise<void> {
  const wmStub = env.CDC_WATERMARK.get(env.CDC_WATERMARK.idFromName(CONSUMER_ID));
  const wmResp = await wmStub.fetch(`https://internal/?consumer=${CONSUMER_ID}`);
  const { watermark: currentMark } = await wmResp.json<{ watermark: number }>();

  const result = await env.DB.prepare(
    `SELECT * FROM changes WHERE change_id > ? ORDER BY change_id LIMIT ?`
  ).bind(currentMark, BATCH_SIZE).all<ChangeRow>();

  if (result.results.length === 0) { console.log('CDC relay: no new changes'); return; }

  let highWatermark = currentMark;
  for (const change of result.results) {
    try {
      await fanOut(change, env);
      highWatermark = change.change_id;
    } catch (err) {
      console.error('CDC relay: fan-out failed', { changeId: change.change_id, err });
      break; // stop here – do not advance watermark past the failed change
    }
  }

  await wmStub.fetch(`https://internal/?consumer=${CONSUMER_ID}`, {
    method: 'POST',
    body: JSON.stringify({ watermark: highWatermark }),
  });

  console.log(`CDC relay: processed up to change_id ${highWatermark}`);
}

async function fanOut(change: ChangeRow, env: Env): Promise<void> {
  const promises: Promise<unknown>[] = [];
  if (change.table_name === 'products') {
    promises.push(env.SEARCH_INDEX_WORKER.fetch('https://internal/index', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(change),
    }));
    promises.push(env.ANALYTICS_QUEUE.send(change));
  }
  await Promise.all(promises);
}
```

### 5. wrangler.toml – CDC relay cron and bindings

```toml
name = "cdc-relay"
main = "src/index.ts"
compatibility_date = "2025-09-01"

[triggers]
crons = ["* * * * *"]

[[durable_objects.bindings]]
name = "CDC_WATERMARK"
class_name = "CdcWatermark"
script_name = "cdc-watermark"

[[services]]
binding = "SEARCH_INDEX_WORKER"
service = "search-indexer"

[[queues.producers]]
queue = "analytics-events"
binding = "ANALYTICS_QUEUE"

[[d1_databases]]
binding = "DB"
database_name = "products-db"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

### 6. Pruning old changes – maintenance cron

```typescript
async function pruneChanges(db: D1Database, retentionDays = 7): Promise<void> {
  const cutoff = new Date(Date.now() - retentionDays * 86_400_000).toISOString();
  const result = await db.prepare(`DELETE FROM changes WHERE occurred_at < ?`).bind(cutoff).run();
  console.log(`CDC prune: deleted ${result.meta.changes} rows older than ${cutoff}`);
}
```

---

## Anti-patterns

- **Writing to the `changes` table outside a batch.** If the business insert succeeds but the changes insert fails, the ledger drifts. Always use `db.batch()`.
- **Advancing the watermark before confirming downstream success.** If a fan-out call fails mid-batch and you already advanced the watermark, those changes are silently skipped forever.
- **Using timestamps as watermarks.** Clock skew means two changes at "the same" millisecond can arrive out of order. Use the AUTOINCREMENT `change_id`.
- **Never pruning the `changes` table.** The ledger grows without bound. Add a retention cron from day one.
- **Reading unbounded change batches.** Without `LIMIT`, a large backlog can exhaust the D1 query size limit. Always paginate.

---

## Gotchas

- **D1 is eventually consistent across read replicas.** The cron Worker may read from a replica that has not yet seen the latest write.
- **Cron triggers are best-effort on Cloudflare.** Under rare platform conditions a cron can fire late or be skipped.
- **D1 `AUTOINCREMENT` gaps.** SQLite's `AUTOINCREMENT` guarantees monotonically increasing IDs but may have gaps after rollbacks.
- **Large `before_json` / `after_json` payloads.** Store a projection rather than the full row if rows are large.

---

## Verification

```bash
# 1. Upsert a product
curl -s -X PUT https://my-api.example.com/products/prod-1 \
  -H "Content-Type: application/json" \
  -d '{"tenantId":"t1","name":"Widget","priceCents":999}'

# 2. Confirm change was written
wrangler d1 execute products-db \
  --command "SELECT change_id, operation, row_key, occurred_at FROM changes ORDER BY change_id DESC LIMIT 5;"

# 3. Check watermark advanced
curl -s "https://cdc-watermark.example.com/?consumer=cdc-relay-v1"
```

---

## Related

- `outbox-pattern-d1-reliable-publishing.md`
- `watermark-durable-objects-event-ordering.md`
- `event-carried-state-transfer-workers-queues.md`
- `fan-out-queues-workers.md`

---

## Sources

- Cloudflare D1 – Batch Statements – https://developers.cloudflare.com/d1/platform/client-api/#batch-statements
- Cloudflare Workers Cron Triggers – https://developers.cloudflare.com/workers/configuration/cron-triggers/
- Martin Kleppmann – *Designing Data-Intensive Applications*, Chapter 11
