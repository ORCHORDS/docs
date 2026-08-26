# postgresql-to-d1-migration-patterns

**Date:** 2026-08-22
**Author:** example.com
**Status:** documented

## Symptom

example project was originally prototyped on a Postgres database (Neon or
Supabase). Migrating the schema and data to Cloudflare D1 (SQLite
under the hood) surfaces type incompatibilities, missing PostgreSQL
features, and data export/import challenges. Naively copying the
`.sql` dump fails immediately because D1 does not understand
PostgreSQL DDL syntax.

## Context

D1 is SQLite 3.44+. PostgreSQL and SQLite share SQL surface area but
differ significantly in type systems, sequence handling, JSON support,
constraint syntax, and procedural features. Migration requires:

1. Schema translation (DDL rewrite).
2. Data export from Postgres and import into D1.
3. Code changes in Worker routes that relied on Postgres-specific
   query features.

This document covers the example project-relevant patterns. The stack uses
raw SQL via the D1 Workers API (no ORM).

## Data Type Translation Reference

| PostgreSQL type         | D1 / SQLite equivalent        | Notes                              |
|-------------------------|-------------------------------|------------------------------------|
| `SERIAL` / `BIGSERIAL`  | `INTEGER PRIMARY KEY`         | SQLite auto-increments implicitly  |
| `UUID`                  | `TEXT`                        | Store as lowercase UUID string     |
| `TEXT`                  | `TEXT`                        | Direct mapping                     |
| `VARCHAR(n)`            | `TEXT`                        | SQLite ignores length limits       |
| `INTEGER` / `INT4`      | `INTEGER`                     | Direct mapping                     |
| `BIGINT` / `INT8`       | `INTEGER`                     | SQLite INTEGER is 64-bit           |
| `BOOLEAN`               | `INTEGER` (0/1)               | No native BOOL type in SQLite      |
| `TIMESTAMP`             | `INTEGER` (Unix ms) or `TEXT` | Epoch integers are fastest         |
| `TIMESTAMPTZ`           | `INTEGER` (Unix ms UTC)       | Store UTC, convert in app          |
| `NUMERIC` / `DECIMAL`   | `REAL` or `TEXT`              | Use TEXT for money (no rounding)   |
| `JSONB`                 | `TEXT` (JSON string)          | Use `json_extract()` to query      |
| `JSON`                  | `TEXT`                        | Same as JSONB in D1                |
| `ARRAY`                 | `TEXT` (JSON array string)    | No native array type               |
| `BYTEA`                 | `BLOB`                        | Direct mapping for binary data     |
| `ENUM`                  | `TEXT` + CHECK constraint     | Emulate with CHECK                 |
| `INET` / `CIDR`         | `TEXT`                        | Store as string, parse in app      |

## Schema Translation Examples

### Sequences → INTEGER PRIMARY KEY

```sql
-- PostgreSQL
CREATE TABLE posts (
  id         BIGSERIAL PRIMARY KEY,
  body       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- D1 / SQLite equivalent
CREATE TABLE posts (
  id         INTEGER PRIMARY KEY,   -- autoincrement implicit
  body       TEXT NOT NULL,
  created_at INTEGER NOT NULL       -- Unix ms, set in Worker code
);
```

For example project, UUIDs are preferred over auto-increment integers because
they are safer for anonymous platforms (no sequential enumeration).
Use `TEXT PRIMARY KEY` and generate UUIDs in the Worker:

```typescript
import { randomUUID } from 'crypto'; // available in Workers
const postId = randomUUID();
```

### Boolean Columns

```sql
-- PostgreSQL
CREATE TABLE communities (
  id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name     TEXT NOT NULL,
  nsfw     BOOLEAN NOT NULL DEFAULT FALSE
);

-- D1 / SQLite
CREATE TABLE communities (
  id       TEXT PRIMARY KEY,
  name     TEXT NOT NULL,
  nsfw     INTEGER NOT NULL DEFAULT 0  -- 0=false, 1=true
    CHECK (nsfw IN (0, 1))
);
```

In Worker TypeScript, cast explicitly:
```typescript
const isNsfw = Boolean(row.nsfw);   // 0 → false, 1 → true
const bindVal = isNsfw ? 1 : 0;     // true → 1, false → 0
```

### JSONB → TEXT with json_extract()

```sql
-- PostgreSQL
CREATE TABLE posts (
  metadata JSONB
);
-- Querying:
SELECT metadata->>'source' FROM posts WHERE metadata->>'source' = 'mobile';

-- D1 / SQLite
CREATE TABLE posts (
  metadata TEXT   -- JSON string stored as TEXT
);
-- Querying with SQLite JSON functions:
SELECT json_extract(metadata, '$.source') AS source
FROM posts
WHERE json_extract(metadata, '$.source') = 'mobile';
```

D1 supports the full SQLite JSON1 extension: `json_extract`,
`json_set`, `json_insert`, `json_remove`, `json_each`, `json_type`.

### ENUM → TEXT + CHECK Constraint

```sql
-- PostgreSQL
CREATE TYPE vote_direction AS ENUM ('up', 'down');
CREATE TABLE votes (
  direction vote_direction NOT NULL
);

-- D1 / SQLite
CREATE TABLE votes (
  direction TEXT NOT NULL
    CHECK (direction IN ('up', 'down'))
);
```

### Timestamps

```sql
-- PostgreSQL
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()

-- D1 / SQLite (Unix milliseconds — recommended for example project)
created_at INTEGER NOT NULL
-- Set in Worker: Date.now()

-- D1 / SQLite (ISO string — readable but slower to sort/compare)
created_at TEXT NOT NULL
-- Set in Worker: new Date().toISOString()
```

Unix millisecond integers are preferred: smaller storage, faster
ORDER BY/range queries, no timezone ambiguity, trivial JS conversion.

## Data Export from PostgreSQL

```bash
# Export as INSERT statements compatible with SQLite:
pg_dump \
  --data-only \
  --column-inserts \
  --no-owner \
  --no-acl \
  -t posts \
  -t communities \
  -t votes \
  example project_postgres_db \
  > example project_data.sql

# The dump includes PostgreSQL-specific casts and sequences.
# Strip them before importing:
sed -i \
  -e "s/true/1/g" \
  -e "s/false/0/g" \
  -e "/^SET /d" \
  -e "/^SELECT pg_catalog/d" \
  example project_data.sql
```

For large datasets, export as CSV and use a Node script to generate
D1-compatible `INSERT` batches via `wrangler d1 execute`:

```typescript
// scripts/import-posts.ts
import { parse } from 'csv-parse/sync';
import { readFileSync } from 'fs';
import { execSync } from 'child_process';

const rows = parse(readFileSync('posts.csv'), { columns: true });
const BATCH = 50;

for (let i = 0; i < rows.length; i += BATCH) {
  const chunk = rows.slice(i, i + BATCH);
  const sql = chunk.map((r: any) =>
    `INSERT INTO posts (id, body, community_id, score, created_at) `
    + `VALUES ('${r.id}', '${r.body.replace(/'/g, "''")}', `
    + `'${r.community_id}', ${r.score}, ${r.created_at});`
  ).join('\n');

  execSync(
    `wrangler d1 execute example project-prod --command "${sql}" --remote`
  );
}
```

For production-scale imports, use `wrangler d1 execute --file`:

```bash
wrangler d1 execute example project-prod --file ./example project_data.sql --remote
```

## Unsupported PostgreSQL Features in D1

| Feature                     | D1 Support | Workaround                           |
|-----------------------------|------------|--------------------------------------|
| `RETURNING *`               | Yes (D1)   | Fully supported                      |
| `ON CONFLICT DO UPDATE`     | Yes        | Fully supported (upsert)             |
| `WITH RECURSIVE`            | Yes        | Fully supported                      |
| `LATERAL JOIN`              | No         | Rewrite as subquery or correlated    |
| Row-level security (RLS)    | No         | Enforce in Worker middleware         |
| Stored procedures/functions | No         | Move logic into Worker code          |
| `pg_notify` / LISTEN        | No         | Use Cloudflare Queues or Durable Obj |
| Full-text search (tsvector) | Partial    | Use SQLite FTS5 extension in D1      |
| `NOW()` / `CURRENT_TIMESTAMP` | Yes      | Works in D1 / SQLite                 |
| Triggers                    | No         | Implement in Worker middleware       |
| `GENERATED ALWAYS AS`       | Yes (3.31+)| Supported in D1                      |

## Anti-Patterns

- Using `REAL` for monetary amounts—floating-point rounding errors
  corrupt financial data. Use `INTEGER` (store cents) or `TEXT`.
- Storing PostgreSQL UUID with hyphens in a BLOB column rather than
  TEXT—SQLite has no UUID type; TEXT is correct and portable.
- Attempting `ALTER TABLE posts ADD COLUMN metadata JSONB`—JSONB does
  not exist in SQLite; use `TEXT`. The column will be created but
  the type affinity will be wrong.
- Using PostgreSQL's `ILIKE` for case-insensitive search—SQLite uses
  `LIKE` which is case-insensitive for ASCII by default, or
  `LOWER(col) LIKE LOWER(?)` for full Unicode coverage.

## Gotchas

- SQLite `INTEGER` is dynamically typed but stores up to 64-bit
  signed integers; Postgres `BIGINT` maps cleanly. JavaScript `Number`
  is only safe to 2^53—use `BigInt` in Workers for IDs > 9 quadrillion.
- Postgres sequences start at 1 and skip on rollback. SQLite
  `INTEGER PRIMARY KEY` increments from `max(id)+1`. After importing
  data, the next auto-increment is correct automatically.
- `json_extract` in SQLite returns `NULL` for missing keys, not an
  error—handle nulls in Worker code.
- D1 enforces `TEXT` type affinity loosely; inserting an integer
  into a `TEXT` column stores it as integer internally. Explicitly
  cast in app code to avoid type surprises.

## Verification

```bash
# Compare row counts between Postgres and D1 after import:
psql $DATABASE_URL -c "SELECT COUNT(*) FROM posts;"
wrangler d1 execute example project-prod \
  --command "SELECT COUNT(*) AS cnt FROM posts;" --remote

# Spot-check a row:
wrangler d1 execute example project-prod \
  --command "SELECT * FROM posts LIMIT 3;" --remote

# Verify boolean migration (nsfw should be 0 or 1, not 't'/'f'):
wrangler d1 execute example project-prod \
  --command "SELECT DISTINCT nsfw FROM communities;" --remote
```

## Related

- `database/d1-migrations-wrangler-ci-cd.md`
- `database/d1-foreign-keys-referential-integrity.md`
- `database/json-columns-patterns.md`
- `database/mysql-vs-postgres-differences.md`

## Sources

- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://www.sqlite.org/datatype3.html
- https://www.sqlite.org/json1.html
- https://www.postgresql.org/docs/current/app-pgdump.html
