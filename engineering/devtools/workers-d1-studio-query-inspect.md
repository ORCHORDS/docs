# Using D1 Studio for Query Inspection

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A D1 query behaves differently in production than in local SQLite, or you need to run ad-hoc diagnostic SQL without deploying code changes. D1 Studio in the Cloudflare dashboard provides a browser-based SQL editor connected directly to the remote D1 database — no credentials to manage, results exportable to CSV, and query plans readable alongside `wrangler d1 execute` output.

## Context

- Cloudflare D1 (remote, production or staging)
- Cloudflare dashboard access with at least **D1 Edit** permissions
- Wrangler 3.x for CLI cross-reference
- TypeScript Workers querying D1 via `env.DB`

---

## Step 1 — Opening D1 Studio

1. Log in to [dash.cloudflare.com](https://dash.cloudflare.com).
2. Navigate to **Workers & Pages** → **D1**.
3. Select your database.
4. Click the **Studio** tab.

The Studio editor opens with a connection to the live remote D1 instance. Any SQL executed here runs against production data — use `BEGIN TRANSACTION` / `ROLLBACK` to test destructive queries safely.

---

## Step 2 — Running Ad-hoc SQL in Studio

```sql
-- Inspect table schema
PRAGMA table_info(users);

-- Count rows per status
SELECT status, COUNT(*) AS total
FROM orders
GROUP BY status
ORDER BY total DESC;

-- Find slow queries: rows with no index support
SELECT *
FROM events
WHERE metadata ->> '$.source' = 'webhook'
  AND created_at > datetime('now', '-7 days')
LIMIT 100;

-- Safe destructive test with explicit rollback
BEGIN TRANSACTION;
UPDATE users SET status = 'inactive' WHERE last_login < datetime('now', '-365 days');
SELECT COUNT(*) AS would_affect FROM users WHERE status = 'inactive';
ROLLBACK;
-- Nothing is committed
```

Studio shows column headers, row counts, and execution time in milliseconds per query.

---

## Step 3 — Exporting Results

After running a query in Studio:

1. Click **Export** (top-right of the results pane).
2. Choose **CSV** or **JSON**.
3. The file downloads directly to your browser.

For large result sets, page the query in Studio:

```sql
-- Page 1
SELECT id, email, created_at FROM users ORDER BY id LIMIT 1000 OFFSET 0;

-- Page 2
SELECT id, email, created_at FROM users ORDER BY id LIMIT 1000 OFFSET 1000;
```

D1 Studio has a 10,000-row display cap per query; for full exports use `wrangler d1 export` (Step 5).

---

## Step 4 — Comparing With wrangler d1 execute Output

Validate that Studio and CLI return consistent results — useful to catch caching or replication lag issues:

```bash
# Run the same query via CLI against remote
wrangler d1 execute my-db --remote \
  --command "SELECT status, COUNT(*) AS total FROM orders GROUP BY status ORDER BY total DESC"

# Run with JSON output for diffing
wrangler d1 execute my-db --remote \
  --command "SELECT id, email FROM users LIMIT 10 ORDER BY id" \
  --json | jq '.result[0].results'
```

Compare the row counts and values against the Studio export. Discrepancies indicate either:
- A query was committed in Studio that the CLI hasn't reflected yet (rare; D1 is eventually consistent within ~1 s).
- A binding mismatch (wrong `database_id` in `wrangler.toml`).

---

## Step 5 — Full Database Export via CLI

```bash
# Export entire remote database as SQL dump
wrangler d1 export my-db --remote --output backup-$(date +%Y%m%d).sql

# Export only the schema (no data)
wrangler d1 export my-db --remote --no-data --output schema.sql

# Export a specific table
wrangler d1 export my-db --remote \
  --table users \
  --output users-export-$(date +%Y%m%d).sql
```

---

## Step 6 — Query Plan Analysis

D1 uses SQLite's query planner. Use `EXPLAIN QUERY PLAN` to verify index usage:

```sql
-- In Studio or via CLI
EXPLAIN QUERY PLAN
SELECT u.id, u.name, o.total
FROM users u
JOIN orders o ON o.user_id = u.id
WHERE u.status = 'active'
  AND o.created_at > datetime('now', '-30 days');
```

Expected output when indexes exist:

```
id  parent  notused  detail
0   0       0        SCAN orders USING INDEX idx_orders_created_at
1   0       0        SEARCH users USING INDEX sqlite_autoindex_users_1 (id=?)
```

Red flag — `SCAN` without `USING INDEX` on a large table:

```sql
-- Add missing index
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_orders_user_created ON orders(user_id, created_at);
```

```bash
# Apply index migration remotely
wrangler d1 execute my-db --remote --command \
  "CREATE INDEX IF NOT EXISTS idx_users_status ON users(status)"
```

---

## Step 7 — Correlating Studio Queries With Worker Code

```typescript
// src/lib/db.ts — parameterised queries used in production
import type { D1Database } from "@cloudflare/workers-types";

export interface Order {
  id: number;
  user_id: number;
  total: number;
  status: string;
  created_at: string;
}

export async function getRecentOrders(
  db: D1Database,
  userId: number,
  days = 30
): Promise<Order[]> {
  const { results } = await db
    .prepare(
      `SELECT id, user_id, total, status, created_at
       FROM orders
       WHERE user_id = ?1
         AND created_at > datetime('now', ?2)
       ORDER BY created_at DESC
       LIMIT 200`
    )
    .bind(userId, `-${days} days`)
    .all<Order>();

  return results;
}

export async function countOrdersByStatus(
  db: D1Database
): Promise<Array<{ status: string; total: number }>> {
  const { results } = await db
    .prepare(
      `SELECT status, COUNT(*) AS total
       FROM orders
       GROUP BY status
       ORDER BY total DESC`
    )
    .all<{ status: string; total: number }>();

  return results;
}
```

To validate the same query in Studio, copy the SQL with literal values:

```sql
-- Studio equivalent of getRecentOrders(db, 42, 30)
SELECT id, user_id, total, status, created_at
FROM orders
WHERE user_id = 42
  AND created_at > datetime('now', '-30 days')
ORDER BY created_at DESC
LIMIT 200;
```

---

## Step 8 — Monitoring D1 Metrics

Alongside Studio, the **Metrics** tab on the D1 database page shows:

- **Read units / Write units** consumed over time
- **Query count** by hour
- **Error rate**

Cross-reference spikes with specific queries by correlating timestamps from `wrangler tail`:

```bash
# Tail the Worker that uses D1 and print D1 timing
wrangler tail my-worker --format json | jq '
  select(.logs != null) |
  .logs[] |
  select(.message[0] | type == "string" and test("d1"; "i"))
'
```

---

## Anti-patterns

- Running `UPDATE` or `DELETE` in Studio without a `WHERE` clause on production data — always add `LIMIT` and preview with `SELECT` first.
- Using Studio as a primary migration tool — use `wrangler d1 migrations apply` for reproducible, version-controlled schema changes.
- Ignoring `EXPLAIN QUERY PLAN` output showing full-table scans on tables with > 10,000 rows.
- Exporting sensitive PII via Studio CSV without reviewing your data handling obligations first.
- Leaving Studio open on a shared screen — it has live write access to the remote database.

## Gotchas

- D1 Studio does not support multi-statement transactions that span multiple executions in the text box; each "Run" is atomic.
- `PRAGMA` statements (e.g., `PRAGMA foreign_keys = ON`) apply only to the current Studio session and are not persisted.
- D1 Studio is not available for databases in non-default regions until the region routing feature is GA.
- The 10,000-row Studio display cap may silently truncate `SELECT *` on large tables — always add explicit `LIMIT`.
- `wrangler d1 execute --remote` and Studio share the same underlying D1 API; they should always return the same data.

---

## Verification

```bash
# Confirm remote D1 is reachable and returns expected row count
wrangler d1 execute my-db --remote \
  --command "SELECT COUNT(*) AS n FROM users" \
  --json | jq '.result[0].results[0].n'

# Cross-check against a known Studio query result
# (compare the number printed above with the Studio COUNT output)

# Verify index is in place
wrangler d1 execute my-db --remote \
  --command "SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY name" \
  --json | jq '[.result[0].results[] | {name, table: .tbl_name}]'
```

---

## Related

- `documentation/categories/devtools/wrangler-pages-functions-local-dev-d1.md`
- `documentation/categories/devtools/workers-source-map-upload-wrangler-debug.md`

## Sources

- https://developers.cloudflare.com/d1/platform/console/
- https://developers.cloudflare.com/d1/reference/query-the-database/
- https://developers.cloudflare.com/workers/wrangler/commands/#d1
- https://www.sqlite.org/eqp.html
- https://developers.cloudflare.com/d1/observability/metrics-analytics/
