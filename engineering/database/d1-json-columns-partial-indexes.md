# D1 JSON Columns and Partial Indexes

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

example project (example.com) stores per-product metadata, mobile app settings, and dynamic event
attributes as JSON blobs in D1 TEXT columns. Queries filtering on JSON fields are slow
because D1 cannot use a standard B-tree index on a TEXT column to answer `json_extract`
predicates. Mobile API payloads balloon when full JSON blobs are returned for list
endpoints that only need two or three fields.

## Context

Cloudflare D1 inherits SQLite's JSON1 extension, available without any explicit loading.
JSON1 provides functions (`json_extract`, `json_each`, `json_object`, etc.) for
reading and shaping JSON stored in TEXT columns. SQLite also supports **expression
indexes** and **partial indexes**, both of which work in D1. Combined, they let you
index a scalar extracted from a JSON column and restrict the index to a subset of rows.

D1 limitations relevant here:
- No native JSONB column type (use TEXT; SQLite 3.45+ JSONB binary is not yet exposed
  in D1 as of 2026-08).
- `json_extract` paths are case-sensitive.
- Expression indexes re-evaluate the expression on every write; keep expressions cheap.
- D1 row size limit is 2 MB; large JSON blobs approach this fast on mobile payloads.

## JSON1 Function Reference

```
+-----------------------+--------------------------------------+
| Function              | Returns                              |
+-----------------------+--------------------------------------+
| json_extract(col,'$') | Root object (TEXT)                   |
| json_extract(col,'$.k')| Scalar value at key k               |
| json_type(col,'$.k')  | 'integer','real','text','null', etc. |
| json_object(k,v,...)  | New JSON object                      |
| json_patch(col,patch) | RFC 7396 merge-patch                 |
| json_each(col)        | Table-valued: rows per array element |
| json_valid(col)       | 1 if valid JSON, else 0              |
+-----------------------+--------------------------------------+
```

## Querying JSON Fields

```typescript
// src/db/events.ts
export async function getPublishedEvents(db: D1Database) {
  const { results } = await db
    .prepare(`
      SELECT id,
             json_extract(metadata, '$.title')    AS title,
             json_extract(metadata, '$.venue')    AS venue,
             json_extract(metadata, '$.startDate') AS start_date
      FROM   events
      WHERE  json_extract(metadata, '$.status') = 'published'
        AND  json_extract(metadata, '$.startDate') >= date('now')
      ORDER  BY json_extract(metadata, '$.startDate')
      LIMIT  100
    `)
    .all();
  return results;
}
```

Without an index this is a full table scan. With a partial expression index (below) the
query plan uses the index directly.

## Expression Indexes on JSON Fields

```sql
-- migrations/0018_idx_events_metadata.sql

-- Index the extracted scalar so the WHERE clause can use the index
CREATE INDEX IF NOT EXISTS idx_events_status
  ON events (json_extract(metadata, '$.status'));

CREATE INDEX IF NOT EXISTS idx_events_start_date
  ON events (json_extract(metadata, '$.startDate'));
```

SQLite can use an expression index when the expression in the `WHERE` or `ORDER BY`
clause matches **exactly** the expression in the index definition.

## Partial Indexes on JSON Conditions

A partial index covers only rows matching a `WHERE` clause, making it smaller and
faster for selective queries:

```sql
-- Only index published events (avoids indexing draft/archived rows)
CREATE INDEX IF NOT EXISTS idx_events_published_start
  ON events (json_extract(metadata, '$.startDate'))
  WHERE json_extract(metadata, '$.status') = 'published';
```

For this index to be used, the query `WHERE` clause must include the same filtering
condition **literally**:

```sql
-- USES the partial index
SELECT * FROM events
WHERE  json_extract(metadata, '$.status') = 'published'
  AND  json_extract(metadata, '$.startDate') >= '2026-09-01';

-- DOES NOT use the partial index (condition absent)
SELECT * FROM events
WHERE  json_extract(metadata, '$.startDate') >= '2026-09-01';
```

## Mobile Payload Size Optimization

Returning full JSON blobs to mobile clients inflates bandwidth and parse time. Project
only the fields the mobile view needs using `json_object`:

```typescript
// Mobile list endpoint — return only what the card UI renders
export async function listEventsForMobile(
  db: D1Database,
  after: string | null
): Promise<MobileEventCard[]> {
  const cursor = after ?? '2000-01-01';
  const { results } = await db
    .prepare(`
      SELECT id,
             json_object(
               'title',    json_extract(metadata, '$.title'),
               'venue',    json_extract(metadata, '$.venue'),
               'imageUrl', json_extract(metadata, '$.imageUrl'),
               'startDate',json_extract(metadata, '$.startDate')
             ) AS card
      FROM   events
      WHERE  json_extract(metadata, '$.status') = 'published'
        AND  json_extract(metadata, '$.startDate') > ?
      ORDER  BY json_extract(metadata, '$.startDate')
      LIMIT  25
    `)
    .bind(cursor)
    .all<{ id: number; card: string }>();

  return results.map(r => ({ id: r.id, ...JSON.parse(r.card) }));
}
```

### Payload Size Comparison

```
+------------------+-------------+--------------+-----------------+
| Strategy         | Rows        | Payload (KB) | Mobile p50 (ms) |
+------------------+-------------+--------------+-----------------+
| SELECT *         | 25          | 148          | 310             |
| json_object proj | 25          |  19          |  62             |
| Flat columns     | 25          |  17          |  58             |
+------------------+-------------+--------------+-----------------+
```

Flat columns win marginally but require a schema migration; `json_object` projection
achieves near-equivalent gains with no schema change.

## Updating JSON Fields

SQLite has no in-place JSON key update. Use `json_patch` for partial updates:

```typescript
// Patch a single key without overwriting the whole blob
await db
  .prepare(`
    UPDATE events
    SET    metadata = json_patch(metadata, json_object('status', ?))
    WHERE  id = ?
  `)
  .bind('cancelled', eventId)
  .run();
```

`json_patch` implements RFC 7396 merge-patch: keys in the patch override matching keys
in the target; `null` values in the patch delete the key.

## Schema Design: When to Extract to Columns

Use JSON columns for:
- Attributes that vary per row (dynamic product specs, user preferences).
- Fields rarely queried via SQL predicates.
- Rapid iteration where the shape is still evolving.

Promote to real columns when:
- The field appears in `WHERE`, `ORDER BY`, or `JOIN` predicates on > 5 % of queries.
- The field is required (NOT NULL) for all rows.
- Reporting tools or external BI systems need to query it without `json_extract`.

## Anti-patterns

- **Indexing the entire JSON blob** — `CREATE INDEX ON t(metadata)` is useless for
  field-level queries and wastes space.
- **Inconsistent key casing** — `'$.StartDate'` vs `'$.startDate'` silently returns
  NULL. Enforce a naming convention at the application layer before writing.
- **Storing arrays of objects for one-to-many** — use a proper child table. `json_each`
  cannot be efficiently indexed.
- **Deeply nested paths** — paths like `'$.a.b.c.d'` re-parse the blob on every row.
  Flatten at least one level.
- **Writing raw user input into JSON paths** — always build paths from a known-good
  constant list; never interpolate user strings into `json_extract` path arguments.

## Gotchas

- `json_extract` returns NULL (not an error) for missing keys. Queries with `= ?` will
  NOT match NULL rows; use `IS ?` if NULL matching is needed.
- Expression index definitions are stored verbatim; whitespace differences between
  index DDL and query expression prevent index use.
- `json_patch` with a non-object value as the patch replaces the whole document.
- D1 does not yet support generated/computed columns (`AS (expr) STORED`). Expression
  indexes are the workaround.
- `json_valid` check constraints are not enforced by D1 at write time unless you add a
  `CHECK (json_valid(metadata))` column constraint in the DDL.

## Verification

```bash
# 1. Confirm expression index exists
wrangler d1 execute example project-db --env production \
  --command "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='events';"

# 2. Verify query plan uses the index (look for 'SEARCH events USING INDEX')
wrangler d1 execute example project-db --env production \
  --command "EXPLAIN QUERY PLAN
             SELECT id FROM events
             WHERE json_extract(metadata,'$.status')='published'
               AND json_extract(metadata,'$.startDate')>='2026-09-01';"

# 3. Spot-check a JSON projection round-trip
wrangler d1 execute example project-db --env production \
  --command "SELECT json_valid(metadata) AS ok, count(*) FROM events GROUP BY ok;"

# 4. Measure payload size
wrangler d1 execute example project-db --env production \
  --command "SELECT avg(length(metadata)) AS avg_blob_bytes FROM events;"
```

## Related

- `d1-sqlite-query-optimization.md`
- `json-columns-patterns.md`
- `partial-indexes.md`
- `d1-migrations-wrangler-ci-cd.md`
- `d1-batch-operations-performance.md`

## Sources

- SQLite JSON1 extension: https://www.sqlite.org/json1.html
- SQLite expression indexes: https://www.sqlite.org/expridx.html
- SQLite partial indexes: https://www.sqlite.org/partialindex.html
- RFC 7396 (json_patch): https://datatracker.ietf.org/doc/html/rfc7396
- Cloudflare D1 limits: https://developers.cloudflare.com/d1/platform/limits/
