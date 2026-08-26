# PostgreSQL JSONB — Indexing, Querying, and Performance Patterns

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your application stores user preferences as JSONB in PostgreSQL. At
10,000 rows, queries are instant. At 500,000 rows, `SELECT * FROM
users WHERE data->>'plan' = 'premium'` takes 3 seconds. You create a
GIN index expecting it to fix the problem, but the query is still
slow because GIN indexes do not support the `->>` operator. Meanwhile,
a different query using the containment operator (`@>`) is fast
because it does use the GIN index, but your team does not understand
why one works and the other does not.

## Context

PostgreSQL's JSONB type provides schema-flexible document storage
inside a relational database, with binary storage that supports
indexing and efficient querying. When properly indexed, JSONB queries
can approach the speed of queries on regular columns, but misuse leads
to 1,000x performance degradation at scale. The key principle: start
with normalized columns, reach for JSONB only when schema flexibility
genuinely demands it, and always index deliberately.

## GIN index operator classes

```sql
-- Default: jsonb_ops — supports @>, ?, ?|, ?&, @?, @@
CREATE INDEX idx_data ON orders USING GIN (data);

-- Alternative: jsonb_path_ops — fewer operators but smaller + faster
-- Supports only @> and jsonpath operators
CREATE INDEX idx_data ON orders USING GIN (data jsonb_path_ops);
```

```
jsonb_ops vs jsonb_path_ops:
  jsonb_ops:       Supports @>, ?, ?|, ?&, @?, @@
                   Larger index, broader operator coverage
  jsonb_path_ops:  Supports only @> and jsonpath
                   Smaller index, better search specificity
                   Use when containment (@>) is your primary pattern
```

## Query patterns

```sql
-- Containment operator (@>) — USES GIN index
SELECT * FROM orders WHERE data @> '{"status": "shipped"}';
SELECT * FROM orders
  WHERE data @> '{"customer": {"tier": "premium"}}';

-- Key existence (?) — USES GIN index (jsonb_ops only)
SELECT * FROM orders WHERE data ? 'priority';

-- Equality on extracted value (->>)  — does NOT use GIN index
-- Requires a B-tree expression index instead
SELECT * FROM orders WHERE data->>'status' = 'shipped';

-- Jsonpath queries (PostgreSQL 12+) — USES GIN index
SELECT * FROM orders
  WHERE data @? '$.items[*] ? (@.price > 100)';

-- Array containment within JSONB
SELECT * FROM orders
  WHERE data->'tags' @> '"urgent"'::jsonb;
```

## Expression indexes for specific keys

```sql
-- B-tree index on a single extracted value
CREATE INDEX idx_status ON orders ((data->>'status'));
-- Now this query is fast:
SELECT * FROM orders WHERE data->>'status' = 'shipped';

-- Partial index (saves space when key is sparse)
CREATE INDEX idx_priority ON orders USING GIN (data jsonb_path_ops)
  WHERE data ? 'priority';

-- Composite expression index
CREATE INDEX idx_user_status ON orders (
  (data->>'user_id'),
  (data->>'status')
);

-- Functional index for case-insensitive search
CREATE INDEX idx_name_lower ON users (lower(data->>'name'));
```

## When to use JSONB vs normalized columns

```
Use normalized columns when:
  → Field is queried constantly (WHERE, JOIN, ORDER BY)
  → Field participates in constraints or uniqueness
  → Field is part of core business logic
  → Field is updated frequently (JSONB rewrites entire document)

Use JSONB when:
  → Schema varies per row (user preferences, plugin config)
  → Data is document-shaped with document-level access
  → Semi-structured data that changes shape frequently
  → Storing third-party API responses for later processing

Hybrid approach (recommended):
  CREATE TABLE orders (
    id          UUID PRIMARY KEY,
    user_id     UUID NOT NULL,         -- normalized: queried constantly
    status      TEXT NOT NULL,         -- normalized: filtered/indexed
    created_at  TIMESTAMPTZ NOT NULL,  -- normalized: sorted/ranged
    metadata    JSONB DEFAULT '{}'     -- flexible: varies per order
  );
```

## Anti-patterns

- **GIN index expecting ->> speedup** — the most common mistake.
  GIN indexes support `@>`, `?`, `?|`, `?&` operators, NOT `->>`.
  For `->>` queries, create a B-tree expression index.
- **Storing frequently-filtered fields in JSONB** — if you regularly
  filter on `user_id`, `status`, or `created_at`, those must be real
  columns with proper B-tree indexes. JSONB forfeits all planner
  optimizations for these access patterns.
- **GIN-indexing everything** — do not create a full GIN index if
  you only query a few keys. Expression indexes and partial indexes
  are smaller and more predictable.
- **Ignoring update cost** — changing one nested value in JSONB
  rewrites the entire document. For frequently updated fields,
  normalized columns are significantly cheaper.

## Gotchas

- **JSONB vs JSON** — always use JSONB, not JSON. JSONB stores data
  in decomposed binary format (faster queries, indexable). JSON
  stores raw text (preserves whitespace, key order, duplicates) and
  cannot be indexed. There is almost no reason to use JSON.
- **NULL vs missing key vs JSON null** — `data->>'key'` returns SQL
  NULL both when the key is missing AND when the value is JSON null.
  Use `data ? 'key'` to distinguish missing from null.
- **Large JSONB documents** — PostgreSQL stores values over ~2KB in
  TOAST (out-of-line storage). Accessing any field requires
  decompressing the entire TOAST value. Keep JSONB documents under
  a few KB for best performance.
- **JSONB in WHERE without index** — unindexed JSONB queries do a
  sequential scan, decompressing and parsing every row. At 500K+
  rows this becomes painfully slow. Always verify your query plan
  with `EXPLAIN ANALYZE`.

## Verification

- GIN indexes use the correct operator class for query patterns.
- Expression indexes exist for `->>` equality queries.
- Frequently filtered fields are normalized columns, not in JSONB.
- Query plans show index scans (verified with EXPLAIN ANALYZE).
- JSONB documents stay under a few KB each.
- Hybrid schema separates stable fields from flexible JSONB.

## Related

- `documentation/docs/policies/database/postgresql-query-optimization.md`
- `documentation/docs/policies/database/postgresql-row-level-security-multi-tenant.md`
- `documentation/docs/policies/database/zero-downtime-schema-migrations.md`

## Source URLs (verified 2026-08-16)

- How to Query and Index JSONB Efficiently in PostgreSQL — https://oneuptime.com/blog/post/2026-01-26-jsonb-querying-indexing-postgresql/view
- Indexing JSONB in Postgres — Crunchy Data — https://www.crunchydata.com/blog/indexing-jsonb-in-postgres
- PostgreSQL JSONB vs Columns: When Flexibility Becomes a Performance Problem — https://sqlpad.io/tutorial/postgresql-jsonb-vs-columns-performance-guide/
- 7 Postgres JSONB Query Patterns That Scale — https://medium.com/@Nexumo_/7-postgres-jsonb-query-patterns-that-scale-79141d4f8784
