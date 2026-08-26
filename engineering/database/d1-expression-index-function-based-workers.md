# D1 Expression Index (Function-Based Index) Optimization in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare D1 query filters or sorts on a transformed column value — `lower(email)`, `substr(slug, 1, 8)`, `json_extract(payload, '$.type')`, or a date truncation — but the existing column-level index is not used because the WHERE clause applies a function. The query degrades to a full table scan at edge latency.

## Context

SQLite supports **expression indexes** (also called function-based indexes): indexes defined on an arbitrary expression rather than a raw column. When the query planner sees a `WHERE` or `ORDER BY` clause whose expression exactly matches the indexed expression (textually), it uses the expression index instead of scanning. D1 exposes full SQLite DDL, so expression indexes are created with standard `CREATE INDEX ON table (expr)` syntax. This eliminates the need for redundant STORED generated columns in many cases and avoids storing the derived value twice.

---

## 1. Case-Insensitive Email Lookup

Without an expression index, `WHERE lower(email) = lower(?)` scans every row and applies `lower()` to each one.

```sql
CREATE TABLE accounts (
  id    TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name  TEXT NOT NULL
);

-- Expression index on lower(email)
CREATE UNIQUE INDEX idx_accounts_email_ci
  ON accounts (lower(email));
```

```typescript
// workers/src/handlers/accounts.ts
export async function findAccountByEmail(
  db: D1Database,
  rawEmail: string,
): Promise<{ id: string; name: string } | null> {
  // The expression lower(?) must match the index expression lower(email) exactly
  return db
    .prepare(
      `SELECT id, name FROM accounts WHERE lower(email) = lower(?)`
    )
    .bind(rawEmail)
    .first<{ id: string; name: string }>();
}

export async function createAccount(
  db: D1Database,
  id: string,
  email: string,
  name: string,
): Promise<void> {
  await db
    .prepare(`INSERT INTO accounts (id, email, name) VALUES (?, ?, ?)`)
    .bind(id, email, name)
    .run();
}
```

---

## 2. JSON Field Expression Index

Avoid a full scan on `json_extract` by indexing the extracted path directly.

```sql
CREATE TABLE events (
  id      TEXT PRIMARY KEY,
  payload TEXT NOT NULL  -- JSON blob
);

-- Index the $.type field without a generated column
CREATE INDEX idx_events_type
  ON events (json_extract(payload, '$.type'));

CREATE INDEX idx_events_tenant_type
  ON events (
    json_extract(payload, '$.tenantId'),
    json_extract(payload, '$.type'),
    json_extract(payload, '$.occurredAt')
  );
```

```typescript
// workers/src/handlers/events.ts
export async function queryEventsByTenantAndType(
  db: D1Database,
  tenantId: string,
  eventType: string,
  since: number,
): Promise<{ id: string; payload: string }[]> {
  const { results } = await db
    .prepare(
      `SELECT id, payload FROM events
       WHERE json_extract(payload, '$.tenantId') = ?
         AND json_extract(payload, '$.type') = ?
         AND json_extract(payload, '$.occurredAt') > ?
       ORDER BY json_extract(payload, '$.occurredAt') DESC
       LIMIT 100`
    )
    .bind(tenantId, eventType, since)
    .all<{ id: string; payload: string }>();
  return results;
}
```

---

## 3. Slug Prefix Expression Index

Index a substring for prefix matching without storing a separate column.

```sql
CREATE TABLE articles (
  id         TEXT PRIMARY KEY,
  slug       TEXT NOT NULL,
  title      TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

-- Index first 12 characters of slug for prefix lookups
CREATE INDEX idx_articles_slug_prefix
  ON articles (substr(slug, 1, 12));
```

```typescript
export async function findBySlugPrefix(
  db: D1Database,
  prefix: string,
): Promise<{ id: string; slug: string; title: string }[]> {
  const { results } = await db
    .prepare(
      `SELECT id, slug, title FROM articles
       WHERE substr(slug, 1, 12) = substr(?, 1, 12)
         AND slug LIKE ?`
    )
    .bind(prefix, `${prefix}%`)
    .all<{ id: string; slug: string; title: string }>();
  return results;
}
```

The expression index prunes candidates; the `LIKE` then filters within the small result set.

---

## 4. Date Truncation for Time-Series Bucketing

Index a derived hour bucket for GROUP BY queries without an extra column.

```sql
CREATE TABLE page_views (
  id         TEXT PRIMARY KEY,
  path       TEXT NOT NULL,
  ts         INTEGER NOT NULL  -- Unix seconds
);

-- Hour bucket expression index
CREATE INDEX idx_page_views_path_hour
  ON page_views (path, ts - (ts % 3600));
```

```typescript
export async function getHourlyPageViews(
  db: D1Database,
  path: string,
  since: number,
): Promise<{ hour: number; views: number }[]> {
  const { results } = await db
    .prepare(
      `SELECT ts - (ts % 3600) AS hour, COUNT(*) AS views
       FROM page_views
       WHERE path = ? AND ts - (ts % 3600) >= ?
       GROUP BY ts - (ts % 3600)
       ORDER BY hour`
    )
    .bind(path, since)
    .all<{ hour: number; views: number }>();
  return results;
}
```

---

## 5. Multi-Column Expression Index for Tenant Isolation

Combine a tenant prefix extraction with a type field for efficient tenant-scoped queries.

```sql
CREATE TABLE messages (
  id        TEXT PRIMARY KEY,
  queue_key TEXT NOT NULL,  -- format: "{tenantId}:{queueName}"
  body      TEXT NOT NULL,
  status    TEXT NOT NULL DEFAULT 'pending',
  enqueued_at INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Index on extracted tenant + status + enqueued_at
CREATE INDEX idx_messages_tenant_status
  ON messages (
    substr(queue_key, 1, instr(queue_key, ':') - 1),
    status,
    enqueued_at
  );
```

```typescript
export async function dequeueMessages(
  db: D1Database,
  tenantId: string,
  limit = 10,
): Promise<{ id: string; body: string }[]> {
  const { results } = await db
    .prepare(
      `SELECT id, body FROM messages
       WHERE substr(queue_key, 1, instr(queue_key, ':') - 1) = ?
         AND status = 'pending'
       ORDER BY enqueued_at ASC
       LIMIT ?`
    )
    .bind(tenantId, limit)
    .all<{ id: string; body: string }>();
  return results;
}
```

---

## 6. Verifying Expression Index Usage in CI

```typescript
// scripts/verify-expression-indexes.ts
interface PlanRow { detail: string }

const checks: Array<{ label: string; sql: string; bindings: unknown[] }> = [
  {
    label: 'case-insensitive email',
    sql: `SELECT id FROM accounts WHERE lower(email) = lower(?)`,
    bindings: ['test@example.com'],
  },
  {
    label: 'json event type',
    sql: `SELECT id FROM events WHERE json_extract(payload, '$.type') = ?`,
    bindings: ['order.created'],
  },
];

export async function verifyExpressionIndexes(db: D1Database): Promise<void> {
  for (const { label, sql, bindings } of checks) {
    const { results } = await db
      .prepare(`EXPLAIN QUERY PLAN ${sql}`)
      .bind(...bindings)
      .all<PlanRow>();

    const usesIndex = results.some(
      r => r.detail.includes('INDEX') && !r.detail.includes('SCAN TABLE'),
    );
    if (!usesIndex) {
      throw new Error(`Expression index not used for: ${label}\nPlan: ${results.map(r => r.detail).join(' | ')}`);
    }
  }
}
```

---

## Anti-patterns

- **Mismatched expression text.** The WHERE clause expression must be textually identical to the index expression. `lower(email)` indexed but `LOWER(email)` in the query will NOT use the index in some SQLite versions — use consistent casing.
- **Wrapping the indexed expression.** `WHERE trim(lower(email)) = ?` does not match `lower(email)` — the outer function defeats the index match.
- **Non-deterministic expressions in indexes.** `random()`, `datetime('now')`, and functions with external side effects cannot be indexed. SQLite will reject the DDL.
- **Using expression indexes instead of generated columns for SELECT.** Expression indexes accelerate filtering but the SELECT result still fetches from the table. If the SELECT also needs the derived value, a STORED generated column is cleaner.
- **Forgetting to re-create expression indexes after schema changes.** Renaming a column that an expression index references silently breaks it (the index remains but covers the old expression).

---

## Gotchas

- SQLite requires the expression in the WHERE clause to be **syntactically identical** to the one in the index — spacing and parenthesization differences can prevent matching. Test with `EXPLAIN QUERY PLAN`.
- Expression indexes on `json_extract` paths use the raw SQLite JSON module — they do not understand JSON Schema or nested arrays beyond direct path access.
- `CREATE INDEX` on an expression triggers a full table scan to populate the index; on large D1 tables this can time out in a Worker context. Run index creation in a migration, not inside a hot path.
- D1 does not yet support descending expression indexes (`CREATE INDEX ... ON t (expr DESC)`). Ascending is the only option.
- `ANALYZE` updates statistics for expression indexes just like column indexes; run it after bulk inserts to help the query planner choose expression indexes over table scans.

---

## Verification

```sql
-- Confirm expression index is picked up
EXPLAIN QUERY PLAN
SELECT id FROM accounts WHERE lower(email) = lower('test@example.com');
-- Expected: SEARCH accounts USING INDEX idx_accounts_email_ci

-- Confirm JSON expression index
EXPLAIN QUERY PLAN
SELECT id FROM events WHERE json_extract(payload, '$.type') = 'order.created';
-- Expected: SEARCH events USING INDEX idx_events_type
```

---

## Related

- `d1-json-column-patterns.md`
- `d1-json-columns-partial-indexes.md`
- `d1-generated-columns-virtual-workers.md`
- `d1-covering-index-composite-key-workers.md`
- `d1-sqlite-query-optimization.md`
- `d1-analyze-query-planner-workers.md`

---

## Sources

- https://www.sqlite.org/expridx.html
- https://www.sqlite.org/optoverview.html
- https://developers.cloudflare.com/d1/reference/database-commands/
- https://www.sqlite.org/json1.html
