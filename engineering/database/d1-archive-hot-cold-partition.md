# Hot/Cold Data Partitioning in D1 with a Workers Cron

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

An `orders` table accumulates rows indefinitely. Queries on recent orders slow down as the table grows past several million rows, even with indexes. Orders older than one year are rarely queried but must be retained for compliance. You need to move old rows to a separate archive table without downtime, and route queries to the right table transparently.

## Context

D1 has a 10 GB per-database size limit (as of 2026). Keeping all historical rows in one table degrades query planner efficiency and increases scan cost. The hot/cold partition pattern maintains two tables — `orders` (hot, recent) and `orders_archive` (cold, historical) — and moves rows older than a threshold via a scheduled Worker. Read queries check both tables or route by age.

---

## Schema

```sql
-- Hot table: recent orders only
CREATE TABLE IF NOT EXISTS orders (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER NOT NULL,
  amount      REAL    NOT NULL,
  status      TEXT    NOT NULL DEFAULT 'pending',
  created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
  archived    INTEGER NOT NULL DEFAULT 0    -- soft flag, 0=active 1=pending archive
);

CREATE INDEX IF NOT EXISTS idx_orders_created  ON orders(created_at);
CREATE INDEX IF NOT EXISTS idx_orders_user     ON orders(user_id, created_at);

-- Cold table: identical schema, add archived_at timestamp
CREATE TABLE IF NOT EXISTS orders_archive (
  id          INTEGER PRIMARY KEY,          -- preserve original PK
  user_id     INTEGER NOT NULL,
  amount      REAL    NOT NULL,
  status      TEXT    NOT NULL,
  created_at  TEXT    NOT NULL,
  archived_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_archive_created ON orders_archive(created_at);
CREATE INDEX IF NOT EXISTS idx_archive_user    ON orders_archive(user_id);
```

---

## Archive Worker (Cron)

The archive job runs in batches to stay within D1's per-request row limits and the Worker's CPU budget.

```typescript
// src/archive.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface ArchiveResult {
  moved:      number;
  batchCount: number;
  durationMs: number;
}

const BATCH_SIZE       = 500;    // rows per iteration
const RETENTION_MONTHS = 12;     // archive rows older than this

/**
 * Move old orders from `orders` → `orders_archive` in BATCH_SIZE chunks.
 * Uses INSERT … SELECT + DELETE inside db.batch() for atomicity per chunk.
 */
export async function archiveOldOrders(
  db: D1Database,
  retentionMonths = RETENTION_MONTHS,
  batchSize = BATCH_SIZE
): Promise<ArchiveResult> {
  const t0 = Date.now();
  let moved = 0;
  let batchCount = 0;

  while (true) {
    // Step 1: Identify a batch of IDs to move
    const { results: candidates } = await db
      .prepare(
        `SELECT id FROM orders
         WHERE created_at < date('now', ? || ' months')
           AND archived = 0
         ORDER BY created_at
         LIMIT ?`
      )
      .bind(`-${retentionMonths}`, batchSize)
      .all<{ id: number }>();

    if (candidates.length === 0) break;

    const ids = candidates.map((r) => r.id);
    const placeholders = ids.map(() => '?').join(',');

    // Step 2: Atomic copy + delete
    await db.batch([
      // Copy to archive
      db.prepare(
        `INSERT OR IGNORE INTO orders_archive
           (id, user_id, amount, status, created_at, archived_at)
         SELECT id, user_id, amount, status, created_at, datetime('now')
         FROM orders
         WHERE id IN (${placeholders})`
      ).bind(...ids),

      // Delete from hot table
      db.prepare(
        `DELETE FROM orders WHERE id IN (${placeholders})`
      ).bind(...ids),
    ]);

    moved += candidates.length;
    batchCount++;

    // Avoid CPU timeout on large datasets: yield between batches
    if (candidates.length === batchSize) {
      await new Promise<void>((r) => setTimeout(r, 0));
    } else {
      break; // last partial batch, done
    }
  }

  return { moved, batchCount, durationMs: Date.now() - t0 };
}
```

---

## Query Routing

Most queries know whether they need recent or historical data. For queries that span both:

```typescript
// src/query.ts
import type { D1Database } from '@cloudflare/workers-types';

export interface Order {
  id:         number;
  user_id:    number;
  amount:     number;
  status:     string;
  created_at: string;
}

/** Recent orders for a user — hot table only. Fast. */
export async function getRecentOrders(
  db: D1Database,
  userId: number,
  limit = 50
): Promise<Order[]> {
  const { results } = await db
    .prepare(
      `SELECT id, user_id, amount, status, created_at
       FROM orders
       WHERE user_id = ?
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .bind(userId, limit)
    .all<Order>();
  return results;
}

/** Full order history — union hot + cold, sorted by date. Slower. */
export async function getAllOrders(
  db: D1Database,
  userId: number,
  limit = 200
): Promise<Order[]> {
  const { results } = await db
    .prepare(
      `SELECT id, user_id, amount, status, created_at FROM orders
         WHERE user_id = ?
       UNION ALL
       SELECT id, user_id, amount, status, created_at FROM orders_archive
         WHERE user_id = ?
       ORDER BY created_at DESC
       LIMIT ?`
    )
    .bind(userId, userId, limit)
    .all<Order>();
  return results;
}

/** Look up a single order — check hot first, fall back to archive. */
export async function findOrder(
  db: D1Database,
  orderId: number
): Promise<Order | null> {
  const hot = await db
    .prepare('SELECT id, user_id, amount, status, created_at FROM orders WHERE id = ?')
    .bind(orderId)
    .first<Order>();
  if (hot) return hot;

  return db
    .prepare('SELECT id, user_id, amount, status, created_at FROM orders_archive WHERE id = ?')
    .bind(orderId)
    .first<Order>();
}
```

---

## Worker Setup

```typescript
// src/worker.ts
import { archiveOldOrders } from './archive';
import { getRecentOrders, getAllOrders, findOrder } from './query';

export interface Env { DB: D1Database; }

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url    = new URL(req.url);
    const userId = Number(url.searchParams.get('userId'));

    if (url.pathname === '/orders/recent') {
      return Response.json(await getRecentOrders(env.DB, userId));
    }
    if (url.pathname === '/orders/all') {
      return Response.json(await getAllOrders(env.DB, userId));
    }
    if (url.pathname.startsWith('/orders/')) {
      const id  = Number(url.pathname.split('/')[2]);
      const row = await findOrder(env.DB, id);
      return row
        ? Response.json(row)
        : new Response('Not found', { status: 404 });
    }

    return new Response('Not found', { status: 404 });
  },

  // Runs nightly at 02:00 UTC
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    const result = await archiveOldOrders(env.DB);
    console.log('[archive-cron]', result);
  },
};
```

```toml
# wrangler.toml
[[d1_databases]]
binding = "DB"
database_name = "my-app-db"
database_id   = "<YOUR_DB_ID>"

[triggers]
crons = ["0 2 * * *"]   # 02:00 UTC daily
```

---

## Monitoring Archive Health

```sql
-- Check hot table size over time
SELECT
  date(created_at) AS day,
  COUNT(*)          AS count
FROM orders
GROUP BY day
ORDER BY day DESC
LIMIT 30;

-- Check archive growth
SELECT
  date(archived_at) AS archived_day,
  COUNT(*)           AS rows_moved
FROM orders_archive
GROUP BY archived_day
ORDER BY archived_day DESC
LIMIT 30;

-- Total rows in each partition
SELECT 'hot'     AS partition, COUNT(*) AS rows FROM orders
UNION ALL
SELECT 'archive' AS partition, COUNT(*) AS rows FROM orders_archive;
```

---

## Anti-patterns

- **Moving all rows in one query** — `DELETE FROM orders WHERE created_at < ...` without a `LIMIT` can hit D1's per-statement row limit (currently ~100 k) and time out.
- **Reading archive on every request** — the `UNION ALL` query is slow; only use it for explicit "full history" endpoints, not the hot path.
- **No `INSERT OR IGNORE`** — if the cron crashes mid-batch after INSERT but before DELETE, a retry will attempt duplicate inserts. `INSERT OR IGNORE` makes the copy idempotent.
- **Archiving rows that are still being updated** — check `status = 'completed'` or similar before archiving open records.

---

## Gotchas

- D1 `db.batch()` is transactional: if the DELETE fails after a successful INSERT, the whole batch rolls back, leaving rows in the hot table. Safe.
- `IN (?, ?, ...)` placeholders must be constructed dynamically. D1 does not support array bindings. Generate the placeholder string before calling `.prepare()`.
- Workers Cron Triggers have a maximum wall-clock time of 30 seconds. If the archive job processes millions of rows nightly, use `waitUntil` with smaller batches across multiple cron fires or implement a Durable Object-based loop.

---

## Verification

```bash
# Seed 5 orders: 3 recent, 2 older than 1 year
wrangler d1 execute MY_DB --command "
  INSERT INTO orders (user_id, amount, status, created_at) VALUES
    (1, 10.00, 'completed', datetime('now')),
    (1, 20.00, 'completed', datetime('now', '-6 months')),
    (1, 30.00, 'completed', datetime('now', '-13 months')),
    (1, 40.00, 'completed', datetime('now', '-14 months')),
    (2, 50.00, 'completed', datetime('now'));
"

# Trigger archive manually
curl -X POST https://my-worker.example.com/__scheduled
# (or invoke via wrangler dev --test-scheduled)

# Confirm 2 rows moved to archive
wrangler d1 execute MY_DB --command "
  SELECT 'hot' AS p, COUNT(*) FROM orders
  UNION ALL
  SELECT 'archive', COUNT(*) FROM orders_archive;
"
# hot     3
# archive 2
```

---

## Related

- `d1-materialized-view-refresh-workers.md` — cron-based data transformation
- `d1-optimistic-locking-version-column.md` — safe concurrent deletes with version check
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/

## Sources

- Data partitioning patterns: https://learn.microsoft.com/en-us/azure/architecture/patterns/sharding
- D1 batch transactions: https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
