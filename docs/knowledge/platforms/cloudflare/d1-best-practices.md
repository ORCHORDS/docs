# d1-best-practices

**Issue:** D1 best practices — schema, queries, ops
**Date:** 2026-08-09
**Status:** documented

## Symptom
Your D1 DB is slow. Queries time out. The dashboard
shows high latency. You don't know where to start.

## Root cause
**D1 has specific patterns.** Follow them.

**Source:** D1 docs.

## The "schema" pattern

For the schema:
- **Normalize:** At first; denormalize for performance
- **Tenant ID:** In every table (for multi-tenant)
- **Audit columns:** `created_at`, `updated_at`
- **UUID PKs:** For global uniqueness

```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  email TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

The schema is well-designed.

## The "index" pattern

For indexes:
- **PK:** Auto-indexed
- **FK columns:** Index
- **Query columns:** Index
- **Composite:** (col1, col2)

```sql
CREATE INDEX idx_users_tenant_email ON users(tenant_id, email);
```

The index is right.

## The "query" pattern

For queries:
- **SELECT only what you need:** Avoid `SELECT *`
- **Use parameters:** Avoid SQL injection
- **Index hits:** Use EXPLAIN to verify
- **Batch:** Use INSERT with multiple values

```ts
// ❌ Bad
const users = await env.DB!.prepare(`SELECT * FROM users`).all();

// ✅ Good
const users = await env.DB!.prepare(
  `SELECT id, email, display_name FROM users WHERE tenant_id = ? LIMIT ?`
).bind(tenantId, 20).all();
```

The query is efficient.

## The "prepared statements" pattern

For prepared statements, prepare once:
```ts
// In a service
private getUserStmt = this.db.prepare(`SELECT * FROM users WHERE id = ?`);

async getUser(id: string) {
  return this.getUserStmt.bind(id).first();
}
```

The statement is prepared once.

## The "batch" pattern

For batch, use `IN`:
```ts
// ❌ Bad: N round-trips
for (const id of ids) {
  await env.DB!.prepare(`SELECT * FROM users WHERE id = ?`).bind(id).first();
}

// ✅ Good: 1 round-trip
const placeholders = ids.map(() => '?').join(',');
const users = await env.DB!.prepare(
  `SELECT * FROM users WHERE id IN (${placeholders})`
).bind(...ids).all();
```

The batch is in one query.

## The "transaction" pattern

For transactions, use `db.batch()`:
```ts
// db.batch() is BROKEN in Pages Functions bundler
// Use db.exec() for DDL, db.prepare().run() for DML

// For multiple DML:
await env.DB!.prepare(`UPDATE users SET status = 'active' WHERE id = ?`).bind('u_1').run();
await env.DB!.prepare(`UPDATE tenants SET active_users = active_users + 1 WHERE id = ?`).bind('t_1').run();
```

The transaction is multiple statements.

**Source:** D1 batch bundler bug:
https://github.com/example-org/example-repo

## The "Time Travel" pattern

For accidental deletes:
- **Time Travel:** 30 days
- **Bookmarks:** Named points
- **Restore:** To a bookmark

```bash
npx wrangler d1 time-travel my-db --bookmark="pre-migration"
```

The DB is restored.

## The "D1 metrics" pattern

For D1 metrics:
- **Query count:** Per minute
- **Query latency:** p50, p95, p99
- **Rows read:** Per query
- **Rows written:** Per query
- **DB size:** Total

The metrics are in the CF dashboard.

## The "D1 limits" pattern

For D1 limits:
- **DB size:** 10GB (paid), 500MB (free)
- **Rows per query:** 1M
- **Query duration:** 30s
- **Concurrent queries:** Limited

The limits are checked.

## The "D1 + Workers" pattern

For D1 binding:
```toml
[[d1_databases]]
binding = "DB"
database_name = "my-db"
database_id = "..."
```

The binding is in `wrangler.toml`.

## The "D1 + R2" pattern

For D1 + R2:
- **D1:** Structured data
- **R2:** Files, blobs
- **Link:** Store the R2 key in D1

```ts
// D1
const file = await env.DB!.prepare(`SELECT * FROM files WHERE id = ?`).bind(id).first();

// R2
const object = await env.R2!.get(file.r2Key);
```

The data is split.

## The "D1 observability" pattern

For observability:
- **Query count:** Per endpoint
- **Query latency:** Per query
- **Rows read:** Per query

```ts
const start = Date.now();
const result = await env.DB!.prepare(query).bind(...).all();
metrics.histogram('d1.duration_ms', Date.now() - start, { query: queryName });
```

The queries are monitored.

## The "D1 anti-pattern" anti-patterns

### 1. SELECT *
- **Issue:** Reads all columns
- **Fix:** Select only what's needed

### 2. No index
- **Issue:** Full table scan
- **Fix:** Add index

### 3. db.batch() in Pages Functions
- **Issue:** esbuild strips `sql` field
- **Fix:** Use db.exec() for DDL, db.prepare().run() for DML

### 4. Long-running query
- **Issue:** Worker timeout
- **Fix:** Optimize or use queue

### 5. No Time Travel bookmark
- **Issue:** Can't restore
- **Fix:** Bookmark before risky changes

## Verification
- **Test:** EXPLAIN shows index usage
- **Test:** Queries are fast (< 100ms)
- **Test:** Backups work
- **Live:** D1 metrics monitored
- **Audit:** Quarterly review

## Gotchas
- **The "SELECT *" anti-pattern.** Select only what's
  needed.
- **The "no index" anti-pattern.** Add an index.
- **The "db.batch()" anti-pattern.** Use exec/prepare.

## Related
- `cloudflare/d1-batch-bundler-bug.md`
- `cloudflare/d1-migration-best-practices.md`
- `cloudflare/d1-pragma-tuning.md`
- `cloudflare/d1-time-travel.md`
- D1 docs: https://developers.cloudflare.com/d1/
