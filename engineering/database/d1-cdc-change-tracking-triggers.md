# D1 Change Data Capture with SQLite Triggers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need an audit trail or downstream event feed from your D1 database without
instrumenting every write path in application code. Downstream consumers — a webhook
fanout Worker, a search index sync job, an analytics pipeline — need to react to
row-level inserts, updates, and deletes reliably and in the order they occurred.

## Context

Cloudflare D1 runs managed SQLite. SQLite does not ship binlog-style CDC (no WAL
streaming, no logical replication slots). The idiomatic alternative is a
**changelog table populated by triggers** — an append-only log that records every
mutation with its before/after state. A separate Consumer Worker polls or drains this
log, fans out events, then marks them consumed.

This is a self-contained, infrastructure-free CDC pattern that runs entirely within a
single D1 database and one or two Workers.

---

## Changelog Table Schema

```sql
-- migrations/0010_changelog.sql

CREATE TABLE changelog (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name  TEXT    NOT NULL,
  operation   TEXT    NOT NULL CHECK (operation IN ('INSERT','UPDATE','DELETE')),
  row_pk      TEXT    NOT NULL,   -- JSON-encoded primary key {"id":"..."}
  old_data    TEXT,               -- JSON snapshot before change (NULL for INSERT)
  new_data    TEXT,               -- JSON snapshot after change  (NULL for DELETE)
  changed_at  INTEGER NOT NULL DEFAULT (unixepoch()),
  consumed_at INTEGER             -- NULL = pending, set by consumer
);

-- Consumer index: fetch pending entries in FIFO order
CREATE INDEX idx_changelog_pending ON changelog(consumed_at, id)
  WHERE consumed_at IS NULL;
```

---

## Trigger Definitions

```sql
-- migrations/0011_product_cdc_triggers.sql

-- INSERT trigger
CREATE TRIGGER trg_products_cdc_insert
AFTER INSERT ON products
BEGIN
  INSERT INTO changelog (table_name, operation, row_pk, new_data)
  VALUES (
    'products',
    'INSERT',
    json_object('id', NEW.id),
    json_object(
      'id',          NEW.id,
      'name',        NEW.name,
      'price_cents', NEW.price_cents,
      'tenant_id',   NEW.tenant_id,
      'created_at',  NEW.created_at
    )
  );
END;

-- UPDATE trigger (captures both before and after)
CREATE TRIGGER trg_products_cdc_update
AFTER UPDATE ON products
BEGIN
  INSERT INTO changelog (table_name, operation, row_pk, old_data, new_data)
  VALUES (
    'products',
    'UPDATE',
    json_object('id', NEW.id),
    json_object(
      'id',          OLD.id,
      'name',        OLD.name,
      'price_cents', OLD.price_cents,
      'updated_at',  OLD.updated_at
    ),
    json_object(
      'id',          NEW.id,
      'name',        NEW.name,
      'price_cents', NEW.price_cents,
      'updated_at',  NEW.updated_at
    )
  );
END;

-- DELETE trigger (captures final state before row is gone)
CREATE TRIGGER trg_products_cdc_delete
AFTER DELETE ON products
BEGIN
  INSERT INTO changelog (table_name, operation, row_pk, old_data)
  VALUES (
    'products',
    'DELETE',
    json_object('id', OLD.id),
    json_object(
      'id',          OLD.id,
      'name',        OLD.name,
      'price_cents', OLD.price_cents,
      'tenant_id',   OLD.tenant_id
    )
  );
END;
```

---

## Consumer Worker (Polling + Fanout)

```typescript
// src/workers/cdc-consumer-worker.ts
import { D1Database } from '@cloudflare/workers-types';

interface ChangelogEntry {
  id: number;
  table_name: string;
  operation: 'INSERT' | 'UPDATE' | 'DELETE';
  row_pk: string;
  old_data: string | null;
  new_data: string | null;
  changed_at: number;
}

interface Env {
  DB: D1Database;
  WEBHOOK_SECRET: string;
}

const BATCH_SIZE = 50;
const WEBHOOK_URL = 'https://internal.example.com/cdc-events';

export default {
  // Cron trigger: runs every minute ("* * * * *" in wrangler.toml)
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(drainChangelog(env));
  },
};

async function drainChangelog(env: Env): Promise<void> {
  while (true) {
    const batch = await env.DB
      .prepare(
        `SELECT id, table_name, operation, row_pk, old_data, new_data, changed_at
         FROM   changelog
         WHERE  consumed_at IS NULL
         ORDER  BY id
         LIMIT  ?`,
      )
      .bind(BATCH_SIZE)
      .all<ChangelogEntry>();

    if (batch.results.length === 0) break;

    // Fan out to downstream (webhook, queue, etc.)
    await fanOut(batch.results, env.WEBHOOK_SECRET);

    // Mark consumed in a single UPDATE
    const ids = batch.results.map((r) => r.id);
    const placeholders = ids.map(() => '?').join(', ');
    await env.DB
      .prepare(
        `UPDATE changelog SET consumed_at = unixepoch()
         WHERE id IN (${placeholders})`,
      )
      .bind(...ids)
      .run();

    if (batch.results.length < BATCH_SIZE) break;
  }
}

async function fanOut(events: ChangelogEntry[], secret: string): Promise<void> {
  const payload = events.map((e) => ({
    id: e.id,
    table: e.table_name,
    op: e.operation,
    pk: JSON.parse(e.row_pk),
    before: e.old_data ? JSON.parse(e.old_data) : null,
    after: e.new_data ? JSON.parse(e.new_data) : null,
    ts: e.changed_at,
  }));

  const resp = await fetch(WEBHOOK_URL, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-cdc-secret': secret,
    },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    throw new Error(`CDC fanout failed: ${resp.status} ${await resp.text()}`);
  }
}
```

---

## Changelog Retention and Cleanup

```typescript
// src/workers/cdc-cleanup.ts — run daily via a separate cron trigger
export async function pruneChangelog(db: D1Database, retainDays = 7): Promise<number> {
  const cutoff = Math.floor(Date.now() / 1000) - retainDays * 86400;
  const result = await db
    .prepare(
      `DELETE FROM changelog
       WHERE consumed_at IS NOT NULL
         AND consumed_at < ?`,
    )
    .bind(cutoff)
    .run();

  return result.changes ?? 0;
}
```

---

## Anti-patterns

- **Polling changelog from user-facing request handlers**: CDC drain is a background job.
  Polling inside a `fetch` handler adds latency to every user request and races with the
  consumer Worker.
- **Using triggers to call external APIs directly**: SQLite triggers execute synchronously
  within the transaction. Any I/O inside a trigger would block the write and is not supported
  by D1. Triggers must only write to local tables.
- **Storing full row snapshots for wide tables (100+ columns)**: The JSON snapshot can grow
  large and bloat the changelog table. Capture only the columns relevant to downstream
  consumers; use `json_object('id', NEW.id, 'price', NEW.price_cents)` selectively.
- **Deleting changelog rows before confirming downstream receipt**: Mark `consumed_at` only
  after the fanout succeeds. If the Worker crashes between fanout and mark, it replays the
  event — idempotency at the consumer is required.

## Gotchas

- `AUTOINCREMENT` on `changelog.id` guarantees monotonically increasing IDs (no reuse after
  delete), which is critical for `ORDER BY id` polling. Without `AUTOINCREMENT`, SQLite may
  reuse IDs from deleted rows.
- D1 does not expose WAL file offsets or LSN equivalents. The changelog `id` sequence is the
  only reliable ordering guarantee across concurrent writes.
- Triggers fire per-row, not per-statement. A bulk INSERT of 500 rows creates 500 changelog
  rows atomically within the same transaction. This is correct behavior but sizes the
  changelog quickly.
- The partial index `WHERE consumed_at IS NULL` is only used when the query's `WHERE` clause
  matches exactly. Ensure the consumer query uses `WHERE consumed_at IS NULL`.

## Verification

```sql
-- Confirm all three triggers exist for the products table
SELECT name, operation, sql
FROM   sqlite_master
WHERE  type = 'trigger' AND tbl_name = 'products'
ORDER  BY name;

-- Check pending (unconsumed) backlog depth
SELECT COUNT(*) AS pending,
       MIN(changed_at) AS oldest_pending_ts,
       datetime(MIN(changed_at), 'unixepoch') AS oldest_pending_date
FROM   changelog
WHERE  consumed_at IS NULL;

-- Verify operation breakdown in the last hour
SELECT operation, COUNT(*) AS count
FROM   changelog
WHERE  changed_at > unixepoch() - 3600
GROUP  BY operation;
```

## Related

- `database-change-data-capture.md` — generic CDC patterns and Debezium comparison
- `d1-triggers-computed-columns.md` — using D1 triggers for denormalized columns
- `d1-audit-event-log.md` — structured audit log without trigger-based CDC
- `d1-dead-letter-queue-retry-workers.md` — retry handling for failed fanout events
- `debezium-cdc-patterns.md` — Postgres CDC via WAL for comparison

## Sources

- SQLite CREATE TRIGGER: https://www.sqlite.org/lang_createtrigger.html
- SQLite JSON functions: https://www.sqlite.org/json1.html
- Cloudflare D1 Workers API: https://developers.cloudflare.com/d1/worker-api/
- Cloudflare Cron Triggers: https://developers.cloudflare.com/workers/configuration/cron-triggers/
