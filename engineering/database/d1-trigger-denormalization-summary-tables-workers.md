# D1 Trigger-Based Denormalization: Maintaining Summary Tables in Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Read-heavy endpoints repeatedly aggregate the same rows (e.g. comment counts, total spend per user, inventory levels) and the aggregation queries become a bottleneck. You want instant reads from pre-computed summary columns or tables, kept consistent by the database rather than by application code.

## Context
Cloudflare D1 runs SQLite under the hood, which supports `AFTER INSERT / UPDATE / DELETE` triggers natively. Because D1 Workers bindings execute SQL inside the same SQLite process, triggers fire synchronously within every `db.prepare().run()` or `db.batch()` call — there is no separate trigger worker to maintain. The trade-off is write amplification: every mutation that touches a source row also touches the summary row inside the same transaction, increasing write latency slightly while collapsing N+1 read aggregations to a single indexed lookup.

---

## Schema Design — Source and Summary Tables

Keep summary tables narrow: one row per aggregate key, with only the columns you actually read.

```sql
-- source table
CREATE TABLE orders (
  id        INTEGER PRIMARY KEY,
  user_id   INTEGER NOT NULL REFERENCES users(id),
  status    TEXT    NOT NULL DEFAULT 'pending',   -- pending | shipped | cancelled
  amount    REAL    NOT NULL CHECK(amount >= 0),
  created_at TEXT   NOT NULL DEFAULT (datetime('now'))
);

-- denormalized summary — one row per user
CREATE TABLE user_order_summary (
  user_id        INTEGER PRIMARY KEY REFERENCES users(id),
  total_orders   INTEGER NOT NULL DEFAULT 0,
  total_spent    REAL    NOT NULL DEFAULT 0,
  shipped_count  INTEGER NOT NULL DEFAULT 0,
  last_order_at  TEXT
);
```

Seed the summary table from existing data before adding triggers so the two stay in sync from day one:

```sql
INSERT INTO user_order_summary (user_id, total_orders, total_spent, shipped_count, last_order_at)
SELECT
  user_id,
  COUNT(*)                                        AS total_orders,
  COALESCE(SUM(amount), 0)                        AS total_spent,
  COUNT(*) FILTER (WHERE status = 'shipped')      AS shipped_count,
  MAX(created_at)                                 AS last_order_at
FROM orders
GROUP BY user_id;
```

---

## Triggers — Insert, Update, Delete

SQLite triggers use `NEW` and `OLD` row references. D1 supports all three DML events.

```sql
-- INSERT: increment totals
CREATE TRIGGER trg_orders_after_insert
AFTER INSERT ON orders
BEGIN
  INSERT INTO user_order_summary (user_id, total_orders, total_spent, shipped_count, last_order_at)
  VALUES (
    NEW.user_id,
    1,
    NEW.amount,
    CASE WHEN NEW.status = 'shipped' THEN 1 ELSE 0 END,
    NEW.created_at
  )
  ON CONFLICT(user_id) DO UPDATE SET
    total_orders  = total_orders  + 1,
    total_spent   = total_spent   + NEW.amount,
    shipped_count = shipped_count + (CASE WHEN NEW.status = 'shipped' THEN 1 ELSE 0 END),
    last_order_at = MAX(last_order_at, NEW.created_at);
END;

-- DELETE: decrement totals
CREATE TRIGGER trg_orders_after_delete
AFTER DELETE ON orders
BEGIN
  UPDATE user_order_summary
  SET
    total_orders  = total_orders  - 1,
    total_spent   = total_spent   - OLD.amount,
    shipped_count = shipped_count - (CASE WHEN OLD.status = 'shipped' THEN 1 ELSE 0 END)
  WHERE user_id = OLD.user_id;
END;

-- UPDATE: apply the delta
CREATE TRIGGER trg_orders_after_update
AFTER UPDATE ON orders
BEGIN
  UPDATE user_order_summary
  SET
    total_spent   = total_spent   + (NEW.amount - OLD.amount),
    shipped_count = shipped_count
                    + (CASE WHEN NEW.status = 'shipped' THEN 1 ELSE 0 END)
                    - (CASE WHEN OLD.status = 'shipped' THEN 1 ELSE 0 END)
  WHERE user_id = NEW.user_id;
END;
```

---

## Applying Triggers via Wrangler Migration

Triggers must be created as part of a migration, not inline at Worker startup. Add a file under `migrations/`:

```sql
-- migrations/0005_order_summary_triggers.sql
CREATE TABLE IF NOT EXISTS user_order_summary (
  user_id        INTEGER PRIMARY KEY REFERENCES users(id),
  total_orders   INTEGER NOT NULL DEFAULT 0,
  total_spent    REAL    NOT NULL DEFAULT 0,
  shipped_count  INTEGER NOT NULL DEFAULT 0,
  last_order_at  TEXT
);

-- backfill
INSERT OR REPLACE INTO user_order_summary
SELECT user_id, COUNT(*), COALESCE(SUM(amount),0),
       COUNT(*) FILTER (WHERE status='shipped'), MAX(created_at)
FROM orders GROUP BY user_id;

-- triggers (same bodies as above)
CREATE TRIGGER IF NOT EXISTS trg_orders_after_insert ...;
CREATE TRIGGER IF NOT EXISTS trg_orders_after_delete ...;
CREATE TRIGGER IF NOT EXISTS trg_orders_after_update ...;
```

Run with:

```bash
npx wrangler d1 migrations apply MY_DB --remote
```

---

## Reading Summaries in a Worker

Once triggers are in place, reads never touch the `orders` table for aggregates:

```typescript
import type { Env } from './types';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const userId = Number(url.searchParams.get('user_id'));
    if (!userId) return new Response('missing user_id', { status: 400 });

    const row = await env.DB.prepare(
      `SELECT total_orders, total_spent, shipped_count, last_order_at
         FROM user_order_summary
        WHERE user_id = ?`
    )
      .bind(userId)
      .first<{
        total_orders: number;
        total_spent: number;
        shipped_count: number;
        last_order_at: string | null;
      }>();

    if (!row) return new Response('not found', { status: 404 });
    return Response.json(row);
  },
};
```

Single primary-key lookup — no GROUP BY, no table scan.

---

## Conditional Denormalization: Only Expensive Aggregates

Not every column warrants a trigger. Keep trigger bodies cheap — avoid correlated subqueries inside trigger bodies because they execute once per mutated row:

```sql
-- AVOID inside a trigger body:
UPDATE user_order_summary
SET total_spent = (SELECT SUM(amount) FROM orders WHERE user_id = NEW.user_id)
WHERE user_id = NEW.user_id;
-- ^ full scan of orders on every insert

-- PREFER: delta arithmetic (shown above), which is O(1)
SET total_spent = total_spent + NEW.amount
```

---

## Anti-patterns

- **Recomputing from scratch inside triggers** — subquery aggregations inside trigger bodies serialize with every write and defeat the purpose.
- **Maintaining summaries in application code** — any non-transactional update path (a failed Worker, a direct Wrangler query, another service) will silently desync the summary.
- **Summary tables without a NOT NULL DEFAULT 0 on counters** — NULL arithmetic (`NULL + 1 = NULL`) silently corrupts totals.
- **Skipping the backfill migration** — adding triggers after existing data means the summary starts wrong.

---

## Gotchas

- **Trigger visibility in D1 Studio** — D1's web console does not surface triggers in the schema view. Use `SELECT name, sql FROM sqlite_master WHERE type='trigger'` to inspect them.
- **`MAX(last_order_at, NEW.created_at)` SQLite semantics** — `MAX()` on text values sorts lexicographically, which is correct for ISO-8601 dates but wrong for locale-formatted dates. Always store dates as `TEXT` in `YYYY-MM-DDTHH:MM:SSZ` format.
- **Cascaded deletes** — if `users` has `ON DELETE CASCADE` referencing `orders`, the cascade itself fires the `AFTER DELETE` trigger on each deleted order row. Confirm this doesn't orphan `user_order_summary` rows; add a trigger or `ON DELETE CASCADE` on that table too.
- **Trigger names are global** — D1 shares a single SQLite namespace; trigger names collide across all tables. Prefix with the table name (`trg_orders_*`).

---

## Verification

```sql
-- 1. Insert a test order and verify the summary increments
INSERT INTO orders (user_id, status, amount, created_at)
VALUES (42, 'shipped', 99.99, datetime('now'));

SELECT * FROM user_order_summary WHERE user_id = 42;
-- expected: total_orders=1, total_spent=99.99, shipped_count=1

-- 2. Cross-check against a live aggregate
SELECT
  s.total_orders,  COUNT(o.id)        AS live_count,
  s.total_spent,   SUM(o.amount)      AS live_sum
FROM user_order_summary s
JOIN orders o ON o.user_id = s.user_id
WHERE s.user_id = 42
GROUP BY s.user_id;
-- total_orders should equal live_count; total_spent should equal live_sum

-- 3. List all triggers on the database
SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'trigger';
```

---

## Related

- `d1-triggers-computed-columns.md`
- `d1-cdc-change-tracking-triggers.md`
- `d1-upsert-conflict-resolution-workers.md`
- `d1-batch-operations-performance.md`
- `d1-materialized-view-simulation-cron.md`

## Sources

- https://developers.cloudflare.com/d1/
- https://www.sqlite.org/lang_createtrigger.html
- https://www.sqlite.org/lang_conflict.html
- https://developers.cloudflare.com/d1/reference/migrations/
