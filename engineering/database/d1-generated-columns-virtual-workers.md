# D1 Generated Columns (Virtual and Stored) in Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need a column whose value is always derived from other columns — a normalized search key, a computed price, a rounded timestamp bucket, or an extracted JSON field — without writing application-layer logic to keep it in sync. Every INSERT or UPDATE must automatically produce the correct derived value. You want to index the derived value for fast lookups.

## Context

SQLite 3.31+ (available in Cloudflare D1) supports **generated columns** declared with `GENERATED ALWAYS AS (expr)`. Two storage modes exist:

- **VIRTUAL** (default): the expression is evaluated at query time; no storage used.
- **STORED**: the expression is evaluated at write time and persisted on disk; indexable and useful for expensive expressions.

Generated columns cannot be written directly by INSERT/UPDATE — the database always computes them. D1 workers benefit from generated columns because they eliminate a class of consistency bugs where application code diverges from the database schema.

---

## 1. Basic VIRTUAL Generated Column

```sql
CREATE TABLE products (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  price_cents INTEGER NOT NULL,
  tax_rate    REAL NOT NULL DEFAULT 0.2,
  -- Computed at query time, never stored
  price_with_tax_cents INTEGER GENERATED ALWAYS AS
    (CAST(price_cents * (1.0 + tax_rate) AS INTEGER)) VIRTUAL
);
```

```typescript
// workers/src/handlers/products.ts
interface Product {
  id: string;
  name: string;
  price_cents: number;
  tax_rate: number;
  price_with_tax_cents: number; // auto-computed by DB
}

export async function getProduct(db: D1Database, id: string): Promise<Product | null> {
  return db
    .prepare(`SELECT id, name, price_cents, tax_rate, price_with_tax_cents
              FROM products WHERE id = ?`)
    .bind(id)
    .first<Product>();
}

export async function createProduct(
  db: D1Database,
  id: string,
  name: string,
  priceCents: number,
  taxRate: number,
): Promise<void> {
  // Do NOT include price_with_tax_cents in INSERT — it is generated
  await db
    .prepare(`INSERT INTO products (id, name, price_cents, tax_rate) VALUES (?, ?, ?, ?)`)
    .bind(id, name, priceCents, taxRate)
    .run();
}
```

---

## 2. STORED Generated Column for Indexing

Use STORED when you need to index the generated value. VIRTUAL columns cannot be directly indexed in SQLite.

```sql
CREATE TABLE users (
  id         TEXT PRIMARY KEY,
  email      TEXT NOT NULL UNIQUE,
  -- Lowercase normalized email for case-insensitive lookup
  email_lower TEXT GENERATED ALWAYS AS (lower(email)) STORED,
  created_at INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE INDEX idx_users_email_lower ON users (email_lower);
```

```typescript
// workers/src/handlers/users.ts
export async function findUserByEmail(
  db: D1Database,
  rawEmail: string,
): Promise<{ id: string; email: string } | null> {
  // Query uses the index on email_lower — case-insensitive but fast
  return db
    .prepare(`SELECT id, email FROM users WHERE email_lower = lower(?)`)
    .bind(rawEmail)
    .first<{ id: string; email: string }>();
}
```

---

## 3. JSON Field Extraction via Generated Column

Extract a frequently queried field from a JSON column into a generated column so it can be indexed and queried without `json_extract` in the WHERE clause.

```sql
CREATE TABLE events (
  id         TEXT PRIMARY KEY,
  payload    TEXT NOT NULL,           -- raw JSON
  -- Extracted fields — STORED so they can be indexed
  event_type TEXT GENERATED ALWAYS AS (json_extract(payload, '$.type')) STORED,
  tenant_id  TEXT GENERATED ALWAYS AS (json_extract(payload, '$.tenantId')) STORED,
  occurred_at INTEGER GENERATED ALWAYS AS (
    CAST(json_extract(payload, '$.occurredAt') AS INTEGER)
  ) STORED
);

CREATE INDEX idx_events_tenant_type_time
  ON events (tenant_id, event_type, occurred_at);
```

```typescript
// workers/src/handlers/events.ts
export async function insertEvent(
  db: D1Database,
  payload: Record<string, unknown>,
): Promise<void> {
  // Only insert raw JSON — generated columns populate automatically
  await db
    .prepare(`INSERT INTO events (id, payload) VALUES (?, ?)`)
    .bind(crypto.randomUUID(), JSON.stringify(payload))
    .run();
}

export async function queryEvents(
  db: D1Database,
  tenantId: string,
  eventType: string,
  since: number,
): Promise<{ id: string; occurred_at: number }[]> {
  const { results } = await db
    .prepare(
      `SELECT id, occurred_at FROM events
       WHERE tenant_id = ? AND event_type = ? AND occurred_at > ?
       ORDER BY occurred_at DESC LIMIT 100`
    )
    .bind(tenantId, eventType, since)
    .all<{ id: string; occurred_at: number }>();
  return results;
}
```

---

## 4. Timestamp Bucketing for Time-Series Aggregations

Generated columns simplify time-bucket GROUP BY queries by pre-computing the bucket at write time.

```sql
CREATE TABLE metrics (
  id         TEXT PRIMARY KEY,
  metric     TEXT NOT NULL,
  value      REAL NOT NULL,
  ts         INTEGER NOT NULL,
  -- Bucket to hour boundary (seconds)
  hour_bucket INTEGER GENERATED ALWAYS AS (ts - (ts % 3600)) STORED,
  day_bucket  INTEGER GENERATED ALWAYS AS (ts - (ts % 86400)) STORED
);

CREATE INDEX idx_metrics_metric_hour ON metrics (metric, hour_bucket);
```

```typescript
export async function getHourlyAggregates(
  db: D1Database,
  metric: string,
  since: number,
): Promise<{ hour_bucket: number; avg_value: number; count: number }[]> {
  const { results } = await db
    .prepare(
      `SELECT hour_bucket, AVG(value) AS avg_value, COUNT(*) AS count
       FROM metrics
       WHERE metric = ? AND hour_bucket >= ?
       GROUP BY hour_bucket
       ORDER BY hour_bucket`
    )
    .bind(metric, since)
    .all<{ hour_bucket: number; avg_value: number; count: number }>();
  return results;
}
```

---

## 5. TypeScript Type Safety with Generated Columns

Generated columns must never appear in INSERT/UPDATE type helpers. Use mapped types to exclude them.

```typescript
// workers/src/types/db.ts
interface UserRow {
  id: string;
  email: string;
  email_lower: string; // STORED generated — exists in SELECT results
  created_at: number;
}

// Omit generated columns from the insert shape
type UserInsert = Omit<UserRow, 'email_lower' | 'created_at'>;

async function insertUser(db: D1Database, data: UserInsert): Promise<void> {
  const cols = Object.keys(data) as (keyof UserInsert)[];
  const placeholders = cols.map(() => '?').join(', ');
  const values = cols.map(c => data[c]);

  await db
    .prepare(`INSERT INTO users (${cols.join(', ')}) VALUES (${placeholders})`)
    .bind(...values)
    .run();
}
```

---

## 6. Migration Pattern for Adding Generated Columns

D1 migrations can add generated columns to existing tables with `ALTER TABLE ... ADD COLUMN`.

```sql
-- migrations/0012_add_email_lower.sql
ALTER TABLE users
  ADD COLUMN email_lower TEXT
    GENERATED ALWAYS AS (lower(email)) STORED;

-- Backfill index for existing rows (SQLite recomputes STORED on ALTER)
CREATE INDEX IF NOT EXISTS idx_users_email_lower ON users (email_lower);
```

```typescript
// scripts/verify-generated-column.ts
export async function verifyEmailLower(db: D1Database): Promise<void> {
  const row = await db
    .prepare(`SELECT email, email_lower FROM users LIMIT 1`)
    .first<{ email: string; email_lower: string }>();

  if (row && row.email_lower !== row.email.toLowerCase()) {
    throw new Error(`Generated column mismatch: ${row.email} → ${row.email_lower}`);
  }
}
```

---

## Anti-patterns

- **Writing to a generated column.** Any `INSERT` or `UPDATE` that includes a generated column will error with `cannot INSERT into generated column`. Always exclude generated columns from write operations.
- **Using VIRTUAL when you need an index.** SQLite does not allow indexes on VIRTUAL generated columns. Declare the column as STORED if it must be indexed.
- **Complex non-deterministic expressions.** Generated column expressions must be deterministic. `random()`, `datetime('now')`, and user-defined functions with side effects are not allowed.
- **Assuming ALTER TABLE recalculates VIRTUAL columns for existing rows.** VIRTUAL columns recalculate on each SELECT; STORED columns are recalculated when `ALTER TABLE ... ADD COLUMN` runs.
- **Not typing INSERT helpers.** Without explicit `Omit<Row, 'generatedCol'>` types, developers will accidentally attempt to write generated columns and get runtime errors.

---

## Gotchas

- SQLite validates that generated column expressions reference only columns in the same row — no subqueries, no aggregate functions.
- `json_extract` in a STORED generated column is evaluated at insert/update time. If the JSON is malformed, the insert fails.
- Generated columns cannot have DEFAULT values or be declared NOT NULL at the column level if the expression can return NULL.
- `ALTER TABLE ... ADD COLUMN` for a STORED generated column triggers a full table rewrite in SQLite — this can be slow on large D1 tables.
- In D1, `EXPLAIN QUERY PLAN` treats STORED generated columns like regular columns; they appear in index scans normally.

---

## Verification

```sql
-- Confirm generated column is populated without explicit insertion
INSERT INTO users (id, email) VALUES ('u1', 'TEST@Example.com');
SELECT email, email_lower FROM users WHERE id = 'u1';
-- Expected: email='TEST@Example.com', email_lower='test@example.com'

-- Confirm index on generated column is used
EXPLAIN QUERY PLAN
SELECT id FROM users WHERE email_lower = 'test@example.com';
-- Expected: USING INDEX idx_users_email_lower
```

---

## Related

- `generated-columns.md`
- `d1-triggers-computed-columns.md`
- `d1-json-column-patterns.md`
- `d1-json-columns-partial-indexes.md`
- `d1-sqlite-query-optimization.md`
- `d1-migrations-wrangler-ci-cd.md`

---

## Sources

- https://www.sqlite.org/gencol.html
- https://developers.cloudflare.com/d1/reference/database-commands/
- https://www.sqlite.org/lang_altertable.html
- https://sqlite.org/json1.html
